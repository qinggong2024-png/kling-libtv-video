from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from libtv_agent.adapters.kling_official_cli import KlingCliError
from libtv_agent.adapters.object_store import ObjectStore
from libtv_agent.adapters.video_provider import VideoProviderAdapter
from libtv_agent.config import Settings
from libtv_agent.domain.contracts import ordered_assets_hash, sha256_json
from libtv_agent.domain.enums import AttemptStatus, CommandStatus, ParentTaskPhase, VariantKind
from libtv_agent.domain.models import (
    Asset,
    AuditEvent,
    GenerationCommand,
    GenerationVariant,
    OutboxEvent,
    ParentTask,
    StagedUpload,
)
from libtv_agent.domain.schemas import VideoTaskCreate
from libtv_agent.services.generation_safety import write_preview_file
from libtv_agent.services.kling_preparation import prepare_kling_task
from libtv_agent.services.material_validator import MaterialDescriptor, validate_materials
from libtv_agent.services.points import PointsLimitExceededError, reserve_points
from libtv_agent.services.prompt_compiler import PromptCompileInput, compile_video_plan
from libtv_agent.services.runtime_control import (
    RuntimeControlBlockedError,
    ensure_provider_submission_allowed,
)
from libtv_agent.services.tasks import get_task
from libtv_agent.templates.site_style_profiles import get_site_style_profile
from libtv_agent.templates.video_templates import get_video_template
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class FixedVideoTaskValidationError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _validation_snapshot(result: Any) -> dict[str, Any]:
    return {
        "valid": result.valid,
        "errors": [asdict(issue) for issue in result.errors],
        "warnings": [asdict(issue) for issue in result.warnings],
        "visionCheckRequired": result.vision_check_required,
    }


async def _mark_action_required(
    session: AsyncSession,
    task: ParentTask,
    *,
    actor_id: uuid.UUID,
    code: str,
    message: str,
) -> ParentTask:
    from_phase = task.phase
    task.phase = ParentTaskPhase.ACTION_REQUIRED
    task.phase_reason_code = code
    task.state_version += 1
    session.add(
        AuditEvent(
            actor_id=actor_id,
            action="FIXED_VIDEO_PREFLIGHT_BLOCKED",
            entity_type="parent_task",
            entity_id=str(task.id),
            from_state=from_phase.value,
            to_state=ParentTaskPhase.ACTION_REQUIRED.value,
            reason=message,
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[],
        )
    )
    await session.commit()
    return await get_task(session, task.user_id, task.id)


async def create_fixed_video_task(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    payload: VideoTaskCreate,
    settings: Settings,
    kling_adapter: VideoProviderAdapter,
    object_store: ObjectStore,
) -> ParentTask:
    if not payload.paid_submission_consent:
        raise FixedVideoTaskValidationError(
            "PAID_SUBMISSION_CONSENT_REQUIRED",
            "点击开始生成前必须明确同意提交付费可灵生成任务",
        )

    try:
        template = get_video_template(payload.template_id, require_active=True)
    except ValueError as exc:
        raise FixedVideoTaskValidationError("VIDEO_TEMPLATE_NOT_ACTIVE", str(exc)) from exc
    try:
        site_profile = get_site_style_profile(payload.site_profile_id, require_active=True)
    except ValueError as exc:
        raise FixedVideoTaskValidationError("SITE_PROFILE_NOT_ACTIVE", str(exc)) from exc

    ordered_inputs = sorted(payload.storyboards, key=lambda item: item.order)
    upload_ids = [item.upload_id for item in ordered_inputs]
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
        raise FixedVideoTaskValidationError(
            "STORYBOARD_UPLOAD_UNAVAILABLE",
            "一个或多个分镜图已失效、已被使用或不属于当前用户",
        )

    descriptors = [
        MaterialDescriptor(
            id=str(upload.id),
            order=item.order,
            original_name=upload.original_filename,
            mime_type=upload.mime_type,
            size_bytes=upload.size_bytes,
            sha256=upload.sha256,
            width=upload.width,
            height=upload.height,
        )
        for item in ordered_inputs
        for upload in (by_id[item.upload_id],)
    ]
    validation = validate_materials(
        descriptors,
        template=template,
        variant_count=payload.result_count,
        action_intensity=payload.action_intensity,
        camera_tempo=payload.camera_tempo,
        cut_mode=payload.cut_mode,
        requested_action_ids=site_profile.preferred_actions,
        max_file_bytes=settings.max_input_image_bytes,
    )
    validation_json = _validation_snapshot(validation)
    if not validation.valid:
        raise FixedVideoTaskValidationError(
            "MATERIAL_VALIDATION_FAILED",
            "分镜素材未通过固定模板校验",
            details=validation_json,
        )

    plans = [
        compile_video_plan(
            PromptCompileInput(
                template=template,
                storyboard_count=len(ordered_inputs),
                action_intensity=payload.action_intensity,
                camera_tempo=payload.camera_tempo,
                cut_mode=payload.cut_mode,
                variant_index=index,
                site_profile=site_profile,
                action_context=validation.action_context,
            )
        )
        for index in range(1, payload.result_count + 1)
    ]
    plan_json = {
        "compiler": "fixed-template-v1",
        "variants": [asdict(plan) for plan in plans],
    }
    task_id = uuid.uuid4()
    consent_at = datetime.now(UTC)
    settings_json = {
        "generationProvider": "kling",
        "resultCount": payload.result_count,
        "actionIntensity": payload.action_intensity,
        "cameraTempo": payload.camera_tempo,
        "cutMode": payload.cut_mode,
        "durationSeconds": template.duration_seconds,
        "aspectRatio": template.ratio,
        "sound": template.sound,
        "subtitles": template.subtitles,
        "smartStoryboard": template.smart_storyboard,
    }
    asset_hash = ordered_assets_hash(
        [
            {"id": str(item.upload_id), "order": item.order, "sha256": by_id[item.upload_id].sha256}
            for item in ordered_inputs
        ]
    )
    task = ParentTask(
        id=task_id,
        user_id=user_id,
        client_task_id=payload.client_task_id,
        title=payload.title,
        asset_count=len(ordered_inputs),
        phase=ParentTaskPhase.PREPARING,
        phase_reason_code=None,
        workflow_kind="FIXED_TEMPLATE",
        template_id=template.id,
        template_version=template.version,
        site_profile_id=site_profile.id,
        site_profile_version=site_profile.version,
        settings_json=settings_json,
        compiled_plan_json=plan_json,
        material_validation_json=validation_json,
        paid_submission_consent_at=consent_at,
        source_upload_duration_seconds=payload.source_upload_duration_seconds,
        user_requirement_raw="",
        user_requirement_normalized="",
    )
    task.assets = []
    for item in ordered_inputs:
        upload = by_id[item.upload_id]
        task.assets.append(
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
                used_for_analysis=False,
                used_for_generation=True,
            )
        )
        upload.claimed_task_id = task_id
    task.variants = [
        GenerationVariant(
            variant_type=VariantKind.STABLE,
            revision=index,
            variant_index=index,
            variant_key=f"result-{index}",
            variant_seed_json=plan.variant_seed,
            prompt_text=plan.master_prompt,
            prompt_hash=sha256_json(plan.master_prompt),
            prompt_template_version=template.version,
            generation_config_json={**settings_json, "variantIndex": index},
            generation_config_hash=sha256_json({**settings_json, "variantIndex": index}),
            ordered_storyboard_assets_hash=asset_hash,
            confirmed_at=consent_at,
        )
        for index, plan in enumerate(plans, start=1)
    ]
    session.add(task)
    session.add(
        AuditEvent(
            actor_id=user_id,
            action="CREATE_FIXED_VIDEO_TASK",
            entity_type="parent_task",
            entity_id=str(task.id),
            from_state=None,
            to_state=ParentTaskPhase.PREPARING.value,
            reason="explicit paid Kling submission consent recorded",
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[],
        )
    )
    await session.commit()
    task = await get_task(session, user_id, task.id)

    try:
        await ensure_provider_submission_allowed(
            session,
            settings,
            "kling",
            user_id=user_id,
        )
        attempts = await prepare_kling_task(
            session,
            kling_adapter,
            object_store,
            task,
            settings,
        )
    except (RuntimeControlBlockedError, KlingCliError) as exc:
        return await _mark_action_required(
            session,
            task,
            actor_id=user_id,
            code=exc.code,
            message=str(exc),
        )

    previews: list[dict[str, Any]] = []
    try:
        for attempt in attempts:
            variant = next(item for item in task.variants if item.id == attempt.variant_id)
            preview = {
                "paidBoundary": "kling image_to_video",
                "provider": attempt.provider,
                "model": attempt.provider_model,
                "variantIndex": variant.variant_index,
                "promptHash": variant.prompt_hash,
                "estimatedGenerationCount": 1,
                "costRisk": "Executing this command consumes Kling credits.",
            }
            previews.append(preview)
            await reserve_points(
                session,
                user_id=user_id,
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
                        "provider": "kling",
                        "intentHash": attempt.intent_hash,
                        "variantIndex": variant.variant_index,
                        "createdAt": consent_at.isoformat(),
                        "paidBoundaryPreview": preview,
                    },
                )
            )
    except PointsLimitExceededError as exc:
        await session.rollback()
        task = await get_task(session, user_id, task.id)
        return await _mark_action_required(
            session,
            task,
            actor_id=user_id,
            code="POINTS_LIMIT_EXCEEDED",
            message=str(exc),
        )

    preview_path = settings.runner_root / "previews" / f"{task.id}.json"
    write_preview_file(
        preview_path,
        {
            "taskId": str(task.id),
            "workflowKind": "FIXED_TEMPLATE",
            "paidGenerationBoundary": "kling image_to_video",
            "commands": previews,
        },
    )
    task.phase = ParentTaskPhase.QUEUED
    task.phase_reason_code = None
    task.state_version += 1
    session.add_all(
        [
            AuditEvent(
                actor_id=user_id,
                action="QUEUE_FIXED_VIDEO_TASK",
                entity_type="parent_task",
                entity_id=str(task.id),
                from_state=ParentTaskPhase.PREPARING.value,
                to_state=ParentTaskPhase.QUEUED.value,
                reason="deterministic plans passed Kling preflight and were explicitly submitted",
                correlation_id=str(uuid.uuid4()),
                evidence_refs_json=[str(preview_path)],
            ),
            OutboxEvent(
                aggregate_type="parent_task",
                aggregate_id=str(task.id),
                event_type="GENERATION_COMMANDS_READY",
                payload_json={"taskId": str(task.id), "workflowKind": "FIXED_TEMPLATE"},
            ),
        ]
    )
    await session.commit()
    return await get_task(session, user_id, task.id)
