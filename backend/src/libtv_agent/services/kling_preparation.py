from __future__ import annotations

from pathlib import Path
from typing import Any

from libtv_agent.adapters.kling_official_cli import KlingCliError, KlingOfficialCliAdapter
from libtv_agent.adapters.object_store import ObjectStore
from libtv_agent.adapters.video_provider import VideoGenerationRequest
from libtv_agent.config import Settings
from libtv_agent.domain.contracts import sha256_json
from libtv_agent.domain.enums import AttemptStatus, ParentTaskPhase
from libtv_agent.domain.models import GenerationAttempt, ParentTask
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _asset_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"


async def prepare_kling_task(
    session: AsyncSession,
    adapter: KlingOfficialCliAdapter,
    object_store: ObjectStore,
    task: ParentTask,
    settings: Settings,
) -> list[GenerationAttempt]:
    availability = await adapter.check_availability()
    if availability.status != "KLING_CLI_READY":
        raise KlingCliError(
            availability.status,
            availability.reason or "Kling CLI Provider is unavailable",
        )
    ordered_assets = sorted(
        (asset for asset in task.assets if asset.used_for_generation),
        key=lambda item: item.order_no,
    )
    if not ordered_assets:
        raise KlingCliError("KLING_INVALID_INPUT", "At least one storyboard image is required")
    localized_paths: list[Path] = []
    for asset in ordered_assets:
        if not asset.object_key:
            raise KlingCliError(
                "KLING_INVALID_INPUT", f"Storyboard asset {asset.id} has no source object"
            )
        localized_paths.append(
            await object_store.localize(
                asset.object_key,
                settings.runner_root
                / "kling"
                / "inputs"
                / str(task.id)
                / f"asset-{asset.order_no}{_asset_suffix(asset.original_filename)}",
            )
        )

    variant_ids = [variant.id for variant in task.variants]
    existing = list(
        await session.scalars(
            select(GenerationAttempt)
            .where(GenerationAttempt.variant_id.in_(variant_ids))
            .order_by(GenerationAttempt.created_at.desc())
        )
    )
    latest_by_variant: dict[Any, GenerationAttempt] = {}
    for attempt in existing:
        latest_by_variant.setdefault(attempt.variant_id, attempt)

    attempts: list[GenerationAttempt] = []
    for variant in task.variants:
        request = VideoGenerationRequest(
            prompt=variant.prompt_text,
            model=settings.kling_cli_default_model,
            image_paths=tuple(localized_paths),
            duration=settings.kling_cli_default_duration,
            aspect_ratio=settings.kling_cli_default_aspect_ratio,
            fallback_mode=settings.kling_storyboard_fallback_mode,
            task_trace_id=task.id.hex,
        )
        model = await adapter.validate_request(request)
        intent_hash = sha256_json(
            {
                "userId": str(task.user_id),
                "parentTaskId": str(task.id),
                "childTaskType": variant.variant_type.value,
                "provider": settings.kling_cli_provider_name,
                "model": model,
                "inputAssetHash": sha256_json([asset.sha256 for asset in ordered_assets]),
                "promptHash": variant.prompt_hash,
                "duration": settings.kling_cli_default_duration,
                "aspectRatio": settings.kling_cli_default_aspect_ratio,
            }
        )
        attempt = latest_by_variant.get(variant.id)
        if attempt is None or attempt.status not in {
            AttemptStatus.PREPARED,
            AttemptStatus.DISPATCH_PENDING,
            AttemptStatus.LAUNCHING,
            AttemptStatus.RUNNING,
            AttemptStatus.UNKNOWN_AFTER_SUBMIT,
            AttemptStatus.SUCCEEDED,
        }:
            attempt = GenerationAttempt(
                variant_id=variant.id,
                provider=settings.kling_cli_provider_name,
                provider_model=model,
                provider_status="queued",
                intent_hash=intent_hash,
                status=AttemptStatus.PREPARED,
            )
            session.add(attempt)
        else:
            if attempt.intent_hash != intent_hash:
                raise KlingCliError(
                    "KLING_SUBMIT_RESULT_UNKNOWN",
                    "An active Kling submission already exists for this variant",
                    submitted=True,
                    uncertain=True,
                )
        variant.generation_config_json = {
            **variant.generation_config_json,
            "generationProvider": "kling",
            "model": model,
            "modelKey": model,
            "duration": settings.kling_cli_default_duration,
            "aspectRatio": settings.kling_cli_default_aspect_ratio,
            "storyboardFallbackMode": settings.kling_storyboard_fallback_mode,
        }
        attempts.append(attempt)
    task.phase = ParentTaskPhase.QUEUED
    task.state_version += 1
    await session.commit()
    return attempts
