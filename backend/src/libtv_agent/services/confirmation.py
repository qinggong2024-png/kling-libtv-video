import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from libtv_agent.adapters.kling_official_cli import KlingCliError
from libtv_agent.adapters.libtv import LibTVAdapter, LibTVError
from libtv_agent.adapters.object_store import ObjectStore
from libtv_agent.adapters.video_provider import VideoProviderAdapter
from libtv_agent.config import Settings
from libtv_agent.domain.enums import (
    AttemptStatus,
    CommandStatus,
    ConsistencyLevel,
    ParentTaskPhase,
    VariantKind,
)
from libtv_agent.domain.models import (
    AuditEvent,
    GenerationAttempt,
    GenerationCommand,
    GenerationVariant,
    OutboxEvent,
    ParentTask,
    TaskConfirmationVersion,
    User,
)
from libtv_agent.services.generation_safety import (
    build_generation_preview,
    paid_generation_authorized,
    write_preview_file,
)
from libtv_agent.services.kling_preparation import prepare_kling_task
from libtv_agent.services.materialization import materialize_task
from libtv_agent.services.points import PointsLimitExceededError, reserve_points
from libtv_agent.services.runtime_control import (
    RuntimeControlBlockedError,
    ensure_paid_submission_allowed,
    ensure_provider_submission_allowed,
    get_runtime_config,
)
from libtv_agent.services.state_machine import cas_task_phase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


async def confirm_task(
    session: AsyncSession,
    adapter: LibTVAdapter,
    object_store: ObjectStore,
    task: ParentTask,
    actor_id: uuid.UUID,
    settings: Settings,
    *,
    kling_adapter: VideoProviderAdapter | None = None,
    accept_risk: bool,
    expected_state_version: int,
    selected_variant_kinds: list[VariantKind] | None = None,
    allow_materialization_recovery: bool = False,
    automatic: bool = False,
    on_preparing: Callable[[], None] | None = None,
) -> None:
    available_variant_kinds = {variant.variant_type for variant in task.variants}
    requested_variant_kinds = (
        set(selected_variant_kinds)
        if selected_variant_kinds is not None
        else available_variant_kinds
    )
    if not requested_variant_kinds:
        raise ValueError("at least one variant must be selected")
    if not requested_variant_kinds.issubset(available_variant_kinds):
        raise ValueError("selected variants are not available on this task")
    if (
        task.phase != ParentTaskPhase.AWAITING_CONFIRMATION
        and requested_variant_kinds != available_variant_kinds
    ):
        raise ValueError("variant selection can only change while awaiting confirmation")
    selected_variants = [
        variant for variant in task.variants if variant.variant_type in requested_variant_kinds
    ]
    preference_snapshot = next(
        (
            variant.generation_config_json
            for variant in selected_variants
            if variant.generation_config_json
        ),
        {},
    )
    provider = str(preference_snapshot.get("generationProvider") or "libtv")
    is_kling = provider == "kling"
    real_mode = not is_kling and settings.libtv_adapter_mode == "real"
    prepared_dispatch = real_mode and task.phase == ParentTaskPhase.WAITING_FOR_SEAL
    if is_kling:
        await ensure_provider_submission_allowed(
            session,
            settings,
            provider,
            user_id=task.user_id,
        )
        if kling_adapter is None:
            raise KlingCliError("KLING_CAPABILITY_FETCH_FAILED", "Kling adapter is unavailable")
    elif real_mode:
        if settings.libtv_execution_mode == "live":
            await ensure_paid_submission_allowed(session, settings, user_id=task.user_id)
        elif settings.libtv_execution_mode == "dry-run":
            raise RuntimeControlBlockedError(
                "DRY_RUN_ACTIVE",
                "dry-run does not mutate LibTV; use prepare-only for remote preparation",
            )
        elif prepared_dispatch:
            raise RuntimeControlBlockedError(
                "PREPARE_ONLY_ACTIVE", "prepared tasks require explicitly authorized live mode"
            )
    else:
        await ensure_paid_submission_allowed(session, settings, user_id=task.user_id)
    recovering = (
        allow_materialization_recovery
        and task.phase == ParentTaskPhase.ACTION_REQUIRED
        and bool(task.phase_reason_code)
        and task.phase_reason_code.startswith("MATERIALIZATION_")
    )
    if (
        task.phase != ParentTaskPhase.AWAITING_CONFIRMATION
        and not recovering
        and not prepared_dispatch
    ):
        raise ValueError("task is not awaiting confirmation")
    if task.consistency_level == ConsistencyLevel.SYSTEM_BLOCK:
        raise ValueError("SYSTEM_BLOCK tasks cannot be confirmed")
    if task.consistency_level == ConsistencyLevel.QUALITY_REVIEW and not accept_risk:
        raise ValueError("acceptRisk is required for QUALITY_REVIEW")

    if prepared_dispatch:
        if task.state_version != expected_state_version:
            raise ValueError("task state changed before prepared dispatch")
        attempts = list(
            await session.scalars(
                select(GenerationAttempt)
                .join(GenerationVariant, GenerationVariant.id == GenerationAttempt.variant_id)
                .where(
                    GenerationVariant.parent_task_id == task.id,
                    GenerationAttempt.status == AttemptStatus.PREPARED,
                )
            )
        )
        if len(attempts) != len(task.variants):
            raise RuntimeControlBlockedError(
                "PREPARED_ATTEMPT_INVALID",
                "one verified prepared attempt is required for each requested output",
            )
    else:
        expected_phase = (
            ParentTaskPhase.ACTION_REQUIRED if recovering else ParentTaskPhase.AWAITING_CONFIRMATION
        )
        await cas_task_phase(
            session,
            task.id,
            expected_phase.value,
            expected_state_version,
            ParentTaskPhase.PREPARING.value,
        )
        if requested_variant_kinds != available_variant_kinds:
            task.variants = selected_variants
        await session.commit()
        await session.refresh(task)
        if on_preparing is not None:
            on_preparing()
        if is_kling:
            attempts = await prepare_kling_task(
                session,
                kling_adapter,
                object_store,
                task,
                settings,
            )
        else:
            attempts = await materialize_task(
                session, adapter, object_store, task, settings.runner_root / "materialization"
            )

    previews: list[dict[str, object]] = []
    for attempt in attempts:
        variant = await session.get(GenerationVariant, attempt.variant_id)
        if variant is None:
            raise RuntimeControlBlockedError("VARIANT_MISSING", "prepared variant is unavailable")
        if is_kling:
            parameter_summary = {
                "provider": attempt.provider,
                "model": attempt.provider_model,
                "duration": variant.generation_config_json.get(
                    "duration", settings.active_kling_duration
                ),
                "aspectRatio": variant.generation_config_json.get(
                    "aspectRatio", settings.active_kling_aspect_ratio
                ),
                "storyboardFallbackMode": settings.kling_storyboard_fallback_mode,
                "resolution": settings.kling_api_resolution,
                "audio": settings.kling_api_audio,
                "multiShot": settings.kling_api_multi_shot,
            }
            preview: dict[str, object] = {
                "paidBoundary": (
                    "POST /omni-video/kling-3.0-omni"
                    if settings.kling_provider_backend == "api"
                    else "kling image_to_video"
                ),
                "parameterSummary": parameter_summary,
                "promptHash": variant.prompt_hash,
                "estimatedGenerationCount": 1,
                "authorized": settings.kling_enabled,
                "costRisk": "Submitting this request consumes Kling credits.",
            }
            if settings.kling_provider_backend == "api":
                preview["httpContract"] = {
                    "method": "POST",
                    "baseUrl": settings.kling_api_base_url,
                    "path": "/omni-video/kling-3.0-omni",
                    "authentication": "Bearer <redacted>",
                }
            else:
                preview["argvContract"] = [
                    settings.kling_cli_executable,
                    "image_to_video",
                    "--model",
                    attempt.provider_model or "<runtime-model>",
                    "--image",
                    "<local-storyboard>",
                    "<prompt>",
                ]
            previews.append(preview)
        else:
            previews.append(
                build_generation_preview(
                    executable=settings.libtv_executable,
                    project_uuid=attempt.project_uuid or "",
                    node_key=attempt.video_node_key or "",
                    params=variant.generation_config_json,
                    prompt_hash=variant.prompt_hash,
                    execution_mode=settings.libtv_execution_mode,
                    authorized=paid_generation_authorized(settings),
                )
            )
    preview_path = settings.runner_root / "previews" / f"{task.id}.json"
    write_preview_file(
        preview_path,
        {
            "taskId": str(task.id),
            "paidGenerationBoundary": (
                "kling image_to_video"
                if is_kling
                else "libtv node <nodeKey> --project <projectUuid> --run"
            ),
            "commands": previews,
        },
    )

    if real_mode and settings.libtv_execution_mode == "prepare-only":
        task.phase = ParentTaskPhase.WAITING_FOR_SEAL
        task.phase_reason_code = "PREPARE_ONLY_COMPLETE"
        task.state_version += 1
        session.add(
            AuditEvent(
                actor_id=actor_id,
                action="PREPARE_ONLY_TASK",
                entity_type="parent_task",
                entity_id=str(task.id),
                from_state=ParentTaskPhase.AWAITING_CONFIRMATION.value,
                to_state=ParentTaskPhase.WAITING_FOR_SEAL.value,
                reason="paid generation command saved and blocked",
                correlation_id=str(uuid.uuid4()),
                evidence_refs_json=[str(preview_path)],
            )
        )
        await session.commit()
        return
    try:
        for index, attempt in enumerate(attempts):
            await reserve_points(
                session,
                user_id=task.user_id,
                attempt_id=attempt.id,
                estimated_points=settings.generation_estimated_points,
                daily_limit=settings.daily_user_points_limit,
            )
            attempt.status = AttemptStatus.DISPATCH_PENDING
            attempt.state_version += 1
            session.add(
                GenerationCommand(
                    attempt_id=attempt.id,
                    status=CommandStatus.READY,
                    command_manifest_json={
                        "provider": provider,
                        "projectUuid": attempt.project_uuid,
                        "groupNodeKey": attempt.group_node_key,
                        "nodeKey": attempt.video_node_key,
                        "intentHash": attempt.intent_hash,
                        "createdAt": datetime.now(UTC).isoformat(),
                        "paidBoundaryPreview": previews[index],
                    },
                )
            )
    except PointsLimitExceededError:
        await session.rollback()
        task.phase = ParentTaskPhase.ACTION_REQUIRED
        task.phase_reason_code = "POINTS_LIMIT_EXCEEDED"
        task.state_version += 1
        await session.commit()
        raise

    if prepared_dispatch:
        task.phase = ParentTaskPhase.QUEUED
        task.phase_reason_code = None
        task.state_version += 1
    variants = {variant.variant_type.value: variant for variant in task.variants}
    primary_variant = variants.get("STABLE") or variants["DYNAMIC"]
    stable_variant = variants.get("STABLE", primary_variant)
    dynamic_variant = variants.get("DYNAMIC", primary_variant)
    revision = (
        await session.scalar(
            select(TaskConfirmationVersion.revision)
            .where(TaskConfirmationVersion.parent_task_id == task.id)
            .order_by(TaskConfirmationVersion.revision.desc())
            .limit(1)
        )
        or 0
    ) + 1
    session.add(
        TaskConfirmationVersion(
            parent_task_id=task.id,
            revision=revision,
            analysis_result_hash=task.analysis_result_hash or "",
            stable_prompt_hash=stable_variant.prompt_hash or "",
            dynamic_prompt_hash=dynamic_variant.prompt_hash or "",
            ordered_storyboard_assets_hash=stable_variant.ordered_storyboard_assets_hash or "",
            generation_config_hash=stable_variant.generation_config_hash or "",
            schema_snapshot_id=stable_variant.schema_snapshot_id,
            confirmed_by=actor_id,
        )
    )
    for variant in task.variants:
        variant.confirmed_at = datetime.now(UTC)
    correlation_id = str(uuid.uuid4())
    session.add_all(
        [
            AuditEvent(
                actor_id=actor_id,
                action="AUTO_CONFIRM_TASK" if automatic else "CONFIRM_TASK",
                entity_type="parent_task",
                entity_id=str(task.id),
                from_state=(
                    ParentTaskPhase.WAITING_FOR_SEAL.value
                    if prepared_dispatch
                    else ParentTaskPhase.AWAITING_CONFIRMATION.value
                ),
                to_state=ParentTaskPhase.QUEUED.value,
                reason=(
                    "automatic PASS confirmation"
                    if automatic
                    else "risk accepted"
                    if accept_risk
                    else "confirmed"
                ),
                correlation_id=correlation_id,
            ),
            OutboxEvent(
                aggregate_type="parent_task",
                aggregate_id=str(task.id),
                event_type="GENERATION_COMMANDS_READY",
                payload_json={"taskId": str(task.id)},
            ),
        ]
    )
    await session.commit()


async def auto_confirm_pass_tasks(
    session: AsyncSession,
    adapter: LibTVAdapter,
    object_store: ObjectStore,
    settings: Settings,
    *,
    kling_adapter: VideoProviderAdapter | None = None,
    limit: int,
) -> int:
    runtime = await get_runtime_config(session, settings)
    if runtime is None or "PASS" not in runtime.config_json.get("autoConfirmLevels", []):
        return 0
    if runtime.config_json.get("globalPaused", True) or runtime.config_json.get(
        "paidSubmissionsPaused", True
    ):
        return 0
    try:
        await ensure_paid_submission_allowed(session, settings)
    except RuntimeControlBlockedError:
        return 0
    query = (
        select(ParentTask)
        .where(
            ParentTask.phase == ParentTaskPhase.AWAITING_CONFIRMATION,
            ParentTask.consistency_level == ConsistencyLevel.PASS,
        )
        .options(selectinload(ParentTask.assets), selectinload(ParentTask.variants))
        .order_by(ParentTask.created_at, ParentTask.id)
        .limit(max(1, limit))
    )
    if runtime.config_json.get("promptConfirmationRequired", True):
        query = query.join(User, User.id == ParentTask.user_id).where(
            User.auto_confirm_prompts.is_(True)
        )
    tasks = list((await session.scalars(query)).unique())
    confirmed = 0
    for task in tasks:
        try:
            await confirm_task(
                session,
                adapter,
                object_store,
                task,
                task.user_id,
                settings,
                kling_adapter=kling_adapter,
                accept_risk=False,
                expected_state_version=task.state_version,
                automatic=True,
            )
        except RuntimeControlBlockedError:
            break
        except (PointsLimitExceededError, KlingCliError, LibTVError, ValueError) as exc:
            await session.rollback()
            session.add(
                AuditEvent(
                    actor_id=task.user_id,
                    action="AUTO_CONFIRM_TASK_FAILED",
                    entity_type="parent_task",
                    entity_id=str(task.id),
                    reason=getattr(exc, "code", type(exc).__name__),
                    correlation_id=str(uuid.uuid4()),
                    evidence_refs_json=[],
                )
            )
            await session.commit()
            continue
        confirmed += 1
    return confirmed
