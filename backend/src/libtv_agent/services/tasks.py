import uuid
from copy import deepcopy
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from libtv_agent.domain.contracts import ordered_assets_hash, sha256_json
from libtv_agent.domain.enums import ParentTaskPhase
from libtv_agent.domain.models import (
    Asset,
    AuditEvent,
    DownloadArtifact,
    GenerationAttempt,
    GenerationFeedback,
    GenerationVariant,
    MaterializationSaga,
    ParentTask,
    StagedUpload,
    UserDailyPointsSummary,
)
from libtv_agent.domain.schemas import (
    ActionCapabilities,
    AssetRead,
    PointsQuotaRead,
    TaskCreate,
    TaskRead,
    TaskReuseRequest,
    TaskStageTimingRead,
    TaskTimingRead,
    VariantRead,
)
from libtv_agent.services.analysis_lifecycle import is_retryable_analysis_failure
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class TaskNotFoundError(RuntimeError):
    pass


async def list_tasks(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = 100,
    cursor_updated_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
) -> list[ParentTask]:
    statement = select(ParentTask).where(ParentTask.user_id == user_id)
    if cursor_updated_at is not None and cursor_id is not None:
        updated_at_column = ParentTask.updated_at
        updated_at_cursor: object = cursor_updated_at
        if session.get_bind().dialect.name == "sqlite":
            updated_at_column = func.datetime(ParentTask.updated_at)
            updated_at_cursor = func.datetime(cursor_updated_at.isoformat(sep=" "))
        statement = statement.where(
            or_(
                updated_at_column < updated_at_cursor,
                ((updated_at_column == updated_at_cursor) & (ParentTask.id < cursor_id)),
            )
        )
    result = await session.scalars(
        statement.options(selectinload(ParentTask.variants), selectinload(ParentTask.assets))
        .order_by(ParentTask.updated_at.desc(), ParentTask.id.desc())
        .limit(limit)
    )
    return list(result.unique())


async def get_task(session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> ParentTask:
    task = await session.scalar(
        select(ParentTask)
        .where(ParentTask.id == task_id, ParentTask.user_id == user_id)
        .options(selectinload(ParentTask.variants), selectinload(ParentTask.assets))
    )
    if task is None:
        raise TaskNotFoundError("task was not found")
    return task


async def create_task(session: AsyncSession, user_id: uuid.UUID, payload: TaskCreate) -> ParentTask:
    upload_ids = [item.upload_id for item in [*payload.storyboards, *payload.product_images]]
    uploads = list(
        await session.scalars(
            select(StagedUpload).where(
                StagedUpload.id.in_(upload_ids),
                StagedUpload.user_id == user_id,
                StagedUpload.claimed_task_id.is_(None),
            )
        )
    )
    by_id = {upload.id: upload for upload in uploads}
    if set(by_id) != set(upload_ids):
        raise ValueError("one or more uploads are unavailable or belong to another user")
    hashes = [by_id[item.upload_id].sha256 for item in payload.storyboards]
    if len(set(hashes)) != len(hashes):
        raise ValueError("duplicate storyboard images must be removed before task creation")
    task_id = uuid.uuid4()
    task = ParentTask(
        id=task_id,
        user_id=user_id,
        client_task_id=payload.client_task_id,
        title=payload.title,
        asset_count=len(upload_ids),
        user_requirement_raw=payload.user_requirement,
        user_requirement_normalized=" ".join(payload.user_requirement.split()),
        phase=ParentTaskPhase.DRAFT,
        source_upload_duration_seconds=payload.source_upload_duration_seconds,
    )
    assets: list[Asset] = []
    for item in sorted(payload.storyboards, key=lambda value: value.order):
        upload = by_id[item.upload_id]
        assets.append(
            Asset(
                parent_task_id=task_id,
                order_no=item.order,
                required=item.required,
                original_filename=upload.original_filename,
                sha256=upload.sha256,
                mime_type=upload.mime_type,
                size_bytes=upload.size_bytes,
                width=upload.width,
                height=upload.height,
                object_key=upload.object_key,
                thumbnail_key=upload.thumbnail_key,
                source_image_output_id=upload.source_image_output_id,
            )
        )
        upload.claimed_task_id = task_id
    for item in sorted(payload.product_images, key=lambda value: value.order):
        upload = by_id[item.upload_id]
        assets.append(
            Asset(
                parent_task_id=task_id,
                source_type="PRODUCT_REFERENCE",
                role="PRODUCT",
                order_no=100 + item.order,
                required=False,
                original_filename=upload.original_filename,
                sha256=upload.sha256,
                mime_type=upload.mime_type,
                size_bytes=upload.size_bytes,
                width=upload.width,
                height=upload.height,
                object_key=upload.object_key,
                thumbnail_key=upload.thumbnail_key,
                source_image_output_id=upload.source_image_output_id,
                used_for_analysis=True,
                used_for_generation=payload.generation_provider == "kling",
            )
        )
        upload.claimed_task_id = task_id
    task.assets = assets
    preference_snapshot = {
        "analysisModel": payload.analysis_model,
        "generationProvider": payload.generation_provider,
    }
    task.variants = [
        GenerationVariant(variant_type=kind, generation_config_json=preference_snapshot)
        for kind in payload.variants
    ]
    session.add(task)
    await session.commit()
    return await get_task(session, user_id, task.id)


def _replace_asset_ids(value: object, asset_ids: dict[str, str]) -> object:
    if isinstance(value, dict):
        return {key: _replace_asset_ids(item, asset_ids) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_asset_ids(item, asset_ids) for item in value]
    if isinstance(value, str):
        return asset_ids.get(value, value)
    return value


async def reuse_task(
    session: AsyncSession,
    user_id: uuid.UUID,
    source: ParentTask,
    payload: TaskReuseRequest,
) -> ParentTask:
    if source.phase not in {
        ParentTaskPhase.DELIVERABLE,
        ParentTaskPhase.PARTIALLY_DELIVERABLE,
    }:
        raise ValueError("only completed tasks can be reused")
    if source.state_version != payload.expected_source_state_version:
        raise ValueError("source task changed before it could be reused")

    source_variants = {variant.variant_type: variant for variant in source.variants}
    missing = [kind.value for kind in payload.variants if kind not in source_variants]
    if missing:
        raise ValueError(f"source task does not contain requested variants: {', '.join(missing)}")
    for kind in payload.variants:
        variant = source_variants[kind]
        if not variant.prompt_text.strip():
            raise ValueError(f"source {kind.value} prompt is unavailable")
        if not variant.generation_config_json or variant.schema_snapshot_id is None:
            raise ValueError(f"source {kind.value} generation snapshot is unavailable")

    task_id = uuid.uuid4()
    asset_id_map: dict[str, str] = {}
    cloned_assets: list[Asset] = []
    for source_asset in sorted(source.assets, key=lambda item: item.order_no):
        cloned_id = uuid.uuid4()
        asset_id_map[str(source_asset.id)] = str(cloned_id)
        cloned_assets.append(
            Asset(
                id=cloned_id,
                parent_task_id=task_id,
                source_type=source_asset.source_type,
                role=source_asset.role,
                order_no=source_asset.order_no,
                required=source_asset.required,
                version=source_asset.version,
                original_filename=source_asset.original_filename,
                sha256=source_asset.sha256,
                mime_type=source_asset.mime_type,
                width=source_asset.width,
                height=source_asset.height,
                object_key=source_asset.object_key or source_asset.thumbnail_key,
                thumbnail_key=source_asset.thumbnail_key,
                source_image_output_id=source_asset.source_image_output_id,
                used_for_analysis=source_asset.used_for_analysis,
                used_for_generation=source_asset.used_for_generation,
            )
        )

    rewritten_analysis = _replace_asset_ids(deepcopy(source.analysis_result_json), asset_id_map)
    generation_assets = [asset for asset in cloned_assets if asset.used_for_generation]
    storyboard_hash = ordered_assets_hash(
        {
            "assetId": str(asset.id),
            "sha256": asset.sha256,
            "order": asset.order_no,
        }
        for asset in generation_assets
    )
    task = ParentTask(
        id=task_id,
        user_id=user_id,
        client_task_id=payload.client_task_id,
        title=payload.title,
        asset_count=len(cloned_assets),
        user_requirement_raw=source.user_requirement_raw,
        user_requirement_normalized=source.user_requirement_normalized,
        phase=ParentTaskPhase.AWAITING_CONFIRMATION,
        consistency_level=source.consistency_level,
        analysis_result_json=rewritten_analysis,
        analysis_result_hash=sha256_json(rewritten_analysis),
    )
    task.assets = cloned_assets
    task.variants = [
        GenerationVariant(
            variant_type=kind,
            prompt_text=source_variants[kind].prompt_text,
            prompt_hash=sha256_json(source_variants[kind].prompt_text),
            prompt_template_version=source_variants[kind].prompt_template_version,
            generation_config_json=deepcopy(source_variants[kind].generation_config_json),
            generation_config_hash=source_variants[kind].generation_config_hash,
            ordered_storyboard_assets_hash=storyboard_hash,
            schema_snapshot_id=source_variants[kind].schema_snapshot_id,
        )
        for kind in payload.variants
    ]
    session.add(task)
    session.add(
        AuditEvent(
            actor_id=user_id,
            action="REUSE_COMPLETED_TASK",
            entity_type="parent_task",
            entity_id=str(task.id),
            from_state=source.phase.value,
            to_state=ParentTaskPhase.AWAITING_CONFIRMATION.value,
            reason=f"reused from task {source.id}",
            correlation_id=uuid.uuid4().hex,
            evidence_refs_json=[
                str(source.id),
                *[kind.value for kind in payload.variants],
            ],
        )
    )
    await session.commit()
    return await get_task(session, user_id, task.id)


async def tasks_to_read(
    session: AsyncSession, tasks: list[ParentTask], daily_limit: int
) -> list[TaskRead]:
    if not tasks:
        return []
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    user_ids = {task.user_id for task in tasks}
    summaries = list(
        await session.scalars(
            select(UserDailyPointsSummary).where(
                UserDailyPointsSummary.user_id.in_(user_ids),
                UserDailyPointsSummary.business_date == day,
            )
        )
    )
    summaries_by_user = {summary.user_id: summary for summary in summaries}
    variant_ids = [variant.id for task in tasks for variant in task.variants]
    feedback_by_variant: dict[uuid.UUID, GenerationFeedback] = {}
    if variant_ids:
        feedback = list(
            await session.scalars(
                select(GenerationFeedback).where(GenerationFeedback.variant_id.in_(variant_ids))
            )
        )
        feedback_by_variant = {item.variant_id: item for item in feedback}
    attempts_by_variant: dict[uuid.UUID, GenerationAttempt] = {}
    if variant_ids:
        ranked_attempts = (
            select(
                GenerationAttempt.id.label("attempt_id"),
                func.row_number()
                .over(
                    partition_by=GenerationAttempt.variant_id,
                    order_by=GenerationAttempt.created_at.desc(),
                )
                .label("rank"),
            )
            .where(GenerationAttempt.variant_id.in_(variant_ids))
            .subquery()
        )
        attempts = list(
            await session.scalars(
                select(GenerationAttempt)
                .join(ranked_attempts, ranked_attempts.c.attempt_id == GenerationAttempt.id)
                .where(ranked_attempts.c.rank == 1)
            )
        )
        attempts_by_variant = {attempt.variant_id: attempt for attempt in attempts}
    attempt_ids = [attempt.id for attempt in attempts_by_variant.values()]
    artifacts_by_attempt: dict[uuid.UUID, DownloadArtifact] = {}
    if attempt_ids:
        ranked_artifacts = (
            select(
                DownloadArtifact.id.label("artifact_id"),
                func.row_number()
                .over(
                    partition_by=DownloadArtifact.attempt_id,
                    order_by=DownloadArtifact.revision.desc(),
                )
                .label("rank"),
            )
            .where(DownloadArtifact.attempt_id.in_(attempt_ids))
            .subquery()
        )
        artifacts = list(
            await session.scalars(
                select(DownloadArtifact)
                .join(
                    ranked_artifacts,
                    ranked_artifacts.c.artifact_id == DownloadArtifact.id,
                )
                .where(ranked_artifacts.c.rank == 1)
            )
        )
        artifacts_by_attempt = {artifact.attempt_id: artifact for artifact in artifacts}
    task_ids = [task.id for task in tasks]
    sagas = list(
        await session.scalars(
            select(MaterializationSaga).where(MaterializationSaga.parent_task_id.in_(task_ids))
        )
    )
    sagas_by_task = {saga.parent_task_id: saga for saga in sagas}
    return [
        _build_task_read(
            task,
            daily_limit,
            summaries_by_user.get(task.user_id),
            attempts_by_variant,
            artifacts_by_attempt,
            feedback_by_variant,
            sagas_by_task.get(task.id),
        )
        for task in tasks
    ]


async def task_to_read(session: AsyncSession, task: ParentTask, daily_limit: int) -> TaskRead:
    return (await tasks_to_read(session, [task], daily_limit))[0]


def _build_task_read(
    task: ParentTask,
    daily_limit: int,
    summary: UserDailyPointsSummary | None,
    attempts_by_variant: dict[uuid.UUID, GenerationAttempt],
    artifacts_by_attempt: dict[uuid.UUID, DownloadArtifact],
    feedback_by_variant: dict[uuid.UUID, GenerationFeedback],
    materialization_saga: MaterializationSaga | None,
) -> TaskRead:
    consumed = summary.consumed_points if summary else 0
    reserved = summary.reserved_points if summary else 0
    uncertain = summary.uncertain_points if summary else 0
    variant_reads: list[VariantRead] = []
    for variant in sorted(
        task.variants,
        key=lambda value: (
            value.variant_index is None,
            value.variant_index or 0,
            value.variant_type.value,
        ),
    ):
        attempt = attempts_by_variant.get(variant.id)
        artifact = artifacts_by_attempt.get(attempt.id) if attempt else None
        feedback = feedback_by_variant.get(variant.id)
        variant_reads.append(
            VariantRead(
                id=variant.id,
                kind=variant.variant_type,
                revision=variant.revision,
                prompt_text=variant.prompt_text,
                prompt_hash=variant.prompt_hash,
                generation_status=variant.generation_status,
                download_status=variant.download_status,
                validation_status=variant.validation_status,
                final_approval_status=variant.final_approval_status,
                quality_gates=dict(variant.quality_gates_json or {}),
                final_approved_by=variant.final_approved_by,
                final_approved_at=variant.final_approved_at,
                human_review_seconds=variant.human_review_seconds,
                review_notes=variant.review_notes,
                download_artifact_id=artifact.id if artifact else None,
                error_code=attempt.last_error_code if attempt else None,
                provider_error_message=attempt.error_message if attempt else None,
                provider_error_details=(attempt.provider_error_details_json if attempt else None),
                provider_error_retryable=(attempt.provider_error_retryable if attempt else None),
                provider=attempt.provider
                if attempt
                else str(variant.generation_config_json.get("generationProvider") or "libtv"),
                provider_task_id=attempt.task_id if attempt else None,
                provider_status=attempt.provider_status if attempt else None,
                execution_backend=attempt.runner_execution_backend if attempt else None,
                variant_index=variant.variant_index,
                variant_key=variant.variant_key,
                variant_seed=variant.variant_seed_json,
                feedback=feedback.value if feedback else None,
                feedback_reasons=list(feedback.reason_codes_json or []) if feedback else [],
                feedback_comment=feedback.comment if feedback else None,
            )
        )
    can_confirm = task.phase in {
        ParentTaskPhase.AWAITING_CONFIRMATION,
        ParentTaskPhase.WAITING_FOR_SEAL,
    }
    can_cancel = task.phase in {
        ParentTaskPhase.DRAFT,
        ParentTaskPhase.ANALYZING,
        ParentTaskPhase.AWAITING_CONFIRMATION,
        ParentTaskPhase.PREPARING,
        ParentTaskPhase.WAITING_FOR_SEAL,
        ParentTaskPhase.QUEUED,
    }
    can_download = any(item.download_status.value == "READY" for item in variant_reads)
    preference_snapshot = next(
        (
            variant.generation_config_json
            for variant in task.variants
            if variant.generation_config_json
        ),
        {},
    )
    return TaskRead(
        id=task.id,
        user_id=task.user_id,
        client_task_id=task.client_task_id,
        title=task.title,
        asset_count=task.asset_count,
        user_requirement=task.user_requirement_raw,
        analysis_model=str(preference_snapshot.get("analysisModel") or "gpt-5.6-luna"),
        generation_provider=str(preference_snapshot.get("generationProvider") or "libtv"),
        phase=task.phase,
        phase_reason_code=task.phase_reason_code,
        consistency_level=task.consistency_level,
        analysis_result=task.analysis_result_json,
        analysis_run_id=task.analysis_run_id,
        analysis_stage=task.analysis_stage,
        analysis_started_at=task.analysis_started_at,
        analysis_heartbeat_at=task.analysis_heartbeat_at,
        canvas_project_uuid=task.assigned_project_uuid,
        state_version=task.state_version,
        assets=[
            AssetRead(
                id=asset.id,
                order=asset.order_no,
                required=asset.required,
                original_filename=asset.original_filename,
                sha256=asset.sha256,
                width=asset.width,
                height=asset.height,
                size_bytes=asset.size_bytes,
                thumbnail_url=f"/api/v1/assets/{asset.id}/thumbnail",
                source_image_output_id=asset.source_image_output_id,
                role=asset.role,
                used_for_analysis=asset.used_for_analysis,
                used_for_generation=asset.used_for_generation,
            )
            for asset in task.assets
        ],
        variants=variant_reads,
        points_quota=PointsQuotaRead(
            daily_limit=daily_limit,
            consumed=consumed,
            reserved=reserved,
            uncertain=uncertain,
            remaining=daily_limit - consumed - reserved - uncertain,
        ),
        action_capabilities=ActionCapabilities(
            can_edit=task.phase
            in {
                ParentTaskPhase.DRAFT,
                ParentTaskPhase.AWAITING_CONFIRMATION,
            },
            can_confirm=can_confirm,
            can_cancel=can_cancel,
            can_retry_analysis=is_retryable_analysis_failure(task),
            can_regenerate=task.phase
            in {
                ParentTaskPhase.DELIVERABLE,
                ParentTaskPhase.PARTIALLY_DELIVERABLE,
                ParentTaskPhase.ACTION_REQUIRED,
            },
            can_download=can_download,
        ),
        workflow_kind=task.workflow_kind,
        template_id=task.template_id,
        template_version=task.template_version,
        site_profile_id=task.site_profile_id,
        site_profile_version=task.site_profile_version,
        settings=task.settings_json,
        compiled_plan=task.compiled_plan_json,
        material_validation=task.material_validation_json,
        paid_submission_consent_at=task.paid_submission_consent_at,
        timing=_build_task_timing(
            task,
            attempts_by_variant,
            artifacts_by_attempt,
            materialization_saga,
        ),
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _duration(start: datetime | None, end: datetime | None) -> float | None:
    normalized_start = _timestamp(start)
    normalized_end = _timestamp(end)
    if normalized_start is None or normalized_end is None:
        return None
    return round(max(0.0, (normalized_end - normalized_start).total_seconds()), 1)


def _build_task_timing(
    task: ParentTask,
    attempts_by_variant: dict[uuid.UUID, GenerationAttempt],
    artifacts_by_attempt: dict[uuid.UUID, DownloadArtifact],
    materialization_saga: MaterializationSaga | None,
) -> TaskTimingRead:
    attempts = [
        attempt
        for variant in task.variants
        if (attempt := attempts_by_variant.get(variant.id)) is not None
    ]
    artifacts = [
        artifact
        for attempt in attempts
        if (artifact := artifacts_by_attempt.get(attempt.id)) is not None
    ]
    confirmed_values = [value for variant in task.variants if (value := variant.confirmed_at)]
    confirmed_at = min(confirmed_values, default=None)
    generation_starts = [
        value
        for attempt in attempts
        if (value := attempt.submitted_at or attempt.process_started_at or attempt.created_at)
    ]
    generation_ends = [value for attempt in attempts if (value := attempt.completed_at)]
    ready_artifacts = [artifact for artifact in artifacts if artifact.status.value == "READY"]
    analysis_finished = task.analysis_heartbeat_at if task.analysis_stage != "QUEUED" else None
    analysis_duration = task.analysis_duration_seconds
    if analysis_duration <= 0 and task.phase != ParentTaskPhase.ANALYZING:
        analysis_duration = _duration(task.analysis_started_at, analysis_finished) or 0

    stages: list[TaskStageTimingRead] = [
        TaskStageTimingRead(
            key="SOURCE_UPLOAD",
            status="COMPLETED",
            duration_seconds=(
                round(task.source_upload_duration_seconds, 1)
                if task.source_upload_duration_seconds > 0
                else None
            ),
        )
    ]

    if task.phase == ParentTaskPhase.ANALYZING:
        analysis_status = "ACTIVE"
        analysis_active_started_at = task.analysis_started_at
    elif is_retryable_analysis_failure(task):
        analysis_status = "FAILED"
        analysis_active_started_at = None
        analysis_duration = (
            analysis_duration
            or _duration(task.analysis_started_at, task.analysis_heartbeat_at)
            or 0
        )
    elif task.analysis_started_at or task.analysis_result_json:
        analysis_status = "COMPLETED"
        analysis_active_started_at = None
    else:
        analysis_status = "PENDING"
        analysis_active_started_at = None
    stages.append(
        TaskStageTimingRead(
            key="ANALYSIS",
            status=analysis_status,
            duration_seconds=round(analysis_duration, 1) if analysis_duration > 0 else None,
            active_started_at=analysis_active_started_at,
            attempt_count=(
                task.analysis_attempt_count
                if task.analysis_attempt_count > 0
                else (1 if task.analysis_started_at else None)
            ),
        )
    )

    confirmation_duration = None
    if confirmed_at is not None:
        confirmation_duration = _duration(analysis_finished, confirmed_at)
        if confirmation_duration is not None:
            confirmation_duration = round(
                max(0.0, confirmation_duration - task.prompt_analysis_duration_seconds), 1
            )
        confirmation_status = "COMPLETED"
        confirmation_active_started_at = None
    elif task.phase == ParentTaskPhase.AWAITING_CONFIRMATION:
        confirmation_status = "ACTIVE"
        confirmation_active_started_at = analysis_finished
    elif is_retryable_analysis_failure(task) or task.phase in {
        ParentTaskPhase.DRAFT,
        ParentTaskPhase.ANALYZING,
    }:
        confirmation_status = "PENDING"
        confirmation_active_started_at = None
    elif task.phase == ParentTaskPhase.ACTION_REQUIRED:
        confirmation_status = "FAILED"
        confirmation_active_started_at = None
    else:
        confirmation_status = "PENDING"
        confirmation_active_started_at = None
    stages.append(
        TaskStageTimingRead(
            key="CONFIRMATION",
            status=confirmation_status,
            duration_seconds=confirmation_duration,
            active_started_at=confirmation_active_started_at,
        )
    )

    if materialization_saga is not None:
        materialization_done = bool(attempts) or materialization_saga.status.value == "VERIFIED"
        materialization_status = "COMPLETED" if materialization_done else "ACTIVE"
        materialization_duration = (
            _duration(materialization_saga.created_at, materialization_saga.updated_at)
            if materialization_done
            else None
        )
        materialization_active_started_at = (
            None if materialization_done else materialization_saga.created_at
        )
    elif task.phase == ParentTaskPhase.ACTION_REQUIRED and confirmed_at is not None:
        materialization_status = "FAILED"
        materialization_duration = None
        materialization_active_started_at = None
    else:
        materialization_status = "PENDING"
        materialization_duration = None
        materialization_active_started_at = None
    stages.append(
        TaskStageTimingRead(
            key="MATERIALIZATION",
            status=materialization_status,
            duration_seconds=materialization_duration,
            active_started_at=materialization_active_started_at,
        )
    )

    generation_started_at = min(generation_starts, default=None)
    generation_completed = bool(attempts) and len(generation_ends) == len(attempts)
    if generation_completed:
        generation_status = "COMPLETED"
        generation_duration = _duration(generation_started_at, max(generation_ends))
        generation_active_started_at = None
    elif generation_started_at is not None:
        generation_status = "ACTIVE"
        generation_duration = None
        generation_active_started_at = generation_started_at
    elif task.phase == ParentTaskPhase.ACTION_REQUIRED and materialization_saga is not None:
        generation_status = "FAILED"
        generation_duration = None
        generation_active_started_at = None
    else:
        generation_status = "PENDING"
        generation_duration = None
        generation_active_started_at = None
    stages.append(
        TaskStageTimingRead(
            key="GENERATION",
            status=generation_status,
            duration_seconds=generation_duration,
            active_started_at=generation_active_started_at,
            attempt_count=len(attempts) or None,
        )
    )

    download_started_at = min(generation_ends, default=None)
    download_is_terminal = task.phase in {
        ParentTaskPhase.DELIVERABLE,
        ParentTaskPhase.PARTIALLY_DELIVERABLE,
    }
    if (attempts and len(ready_artifacts) == len(attempts)) or (
        download_is_terminal and ready_artifacts
    ):
        download_status = "COMPLETED"
        download_duration = _duration(
            download_started_at,
            max(artifact.created_at for artifact in ready_artifacts),
        )
        download_active_started_at = None
    elif generation_completed and task.phase not in {
        ParentTaskPhase.ACTION_REQUIRED,
        ParentTaskPhase.CANCELLED,
    }:
        download_status = "ACTIVE"
        download_duration = None
        download_active_started_at = download_started_at
    elif task.phase == ParentTaskPhase.ACTION_REQUIRED and generation_completed:
        download_status = "FAILED"
        download_duration = None
        download_active_started_at = None
    else:
        download_status = "PENDING"
        download_duration = None
        download_active_started_at = None
    stages.append(
        TaskStageTimingRead(
            key="DOWNLOAD",
            status=download_status,
            duration_seconds=download_duration,
            active_started_at=download_active_started_at,
        )
    )
    return TaskTimingRead(stages=stages)
