from __future__ import annotations

from pathlib import Path
from typing import Any

from libtv_agent.adapters.kling_official_cli import KlingCliError
from libtv_agent.adapters.object_store import ObjectStore
from libtv_agent.adapters.video_provider import (
    VideoElementReference,
    VideoGenerationRequest,
    VideoProviderAdapter,
)
from libtv_agent.config import Settings
from libtv_agent.domain.contracts import sha256_json
from libtv_agent.domain.enums import AttemptStatus, ParentTaskPhase
from libtv_agent.domain.models import GenerationAttempt, ParentTask
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _asset_suffix(filename: str, object_key: str | None = None) -> str:
    # Upload preprocessing stores normalized JPEG bytes under normalized.jpg,
    # while original_filename intentionally retains the user's source name.
    # Prefer the stored object's suffix so a WebP upload is not localized as
    # JPEG bytes behind a misleading .webp extension.
    for candidate in (object_key, filename):
        suffix = Path(candidate or "").suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png"}:
            return suffix
    return ".jpg"


def _resolve_multi_shot(config: dict[str, Any], settings: Settings) -> bool:
    multi_shot = config.get("multiShot")
    if isinstance(multi_shot, bool):
        return multi_shot
    smart_storyboard = config.get("smartStoryboard")
    if isinstance(smart_storyboard, bool):
        return smart_storyboard
    return settings.kling_api_multi_shot


def _resolve_element_references(config: dict[str, Any]) -> tuple[VideoElementReference, ...]:
    value = config.get("elementIds")
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise KlingCliError("KLING_INVALID_INPUT", "elementIds must be an array")
    element_ids = tuple(str(item).strip() for item in value)
    if any(not element_id for element_id in element_ids):
        raise KlingCliError("KLING_INVALID_INPUT", "elementIds cannot contain empty values")
    if len(element_ids) != len(set(element_ids)):
        raise KlingCliError("KLING_INVALID_INPUT", "elementIds must be unique")
    return tuple(
        VideoElementReference(element_id=element_id, content_id=f"element_{index}")
        for index, element_id in enumerate(element_ids, start=1)
    )


async def prepare_kling_task(
    session: AsyncSession,
    adapter: VideoProviderAdapter,
    object_store: ObjectStore,
    task: ParentTask,
    settings: Settings,
) -> list[GenerationAttempt]:
    availability = await adapter.check_availability()
    if not availability.available:
        raise KlingCliError(
            availability.status,
            availability.reason or "Kling provider is unavailable",
        )
    storyboard_assets = sorted(
        (asset for asset in task.assets if asset.used_for_generation and asset.role != "PRODUCT"),
        key=lambda item: item.order_no,
    )
    product_reference_assets = sorted(
        (
            asset
            for asset in task.assets
            if asset.used_for_generation and asset.role == "PRODUCT"
        ),
        key=lambda item: item.order_no,
    )
    if not storyboard_assets:
        raise KlingCliError("KLING_INVALID_INPUT", "At least one storyboard image is required")
    storyboard_paths: list[Path] = []
    for index, asset in enumerate(storyboard_assets, start=1):
        if not asset.object_key:
            raise KlingCliError(
                "KLING_INVALID_INPUT", f"Storyboard asset {asset.id} has no source object"
            )
        storyboard_paths.append(
            await object_store.localize(
                asset.object_key,
                settings.runner_root
                / "kling"
                / "inputs"
                / str(task.id)
                / f"storyboard-{index}{_asset_suffix(asset.original_filename, asset.object_key)}",
            )
        )
    product_reference_paths: list[Path] = []
    for index, asset in enumerate(product_reference_assets, start=1):
        if not asset.object_key:
            raise KlingCliError(
                "KLING_INVALID_INPUT", f"Product reference asset {asset.id} has no source object"
            )
        product_reference_paths.append(
            await object_store.localize(
                asset.object_key,
                settings.runner_root
                / "kling"
                / "inputs"
                / str(task.id)
                / (
                    f"product-reference-{index}"
                    f"{_asset_suffix(asset.original_filename, asset.object_key)}"
                ),
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
    provider_name = adapter.get_provider_name()
    for variant in sorted(
        task.variants,
        key=lambda item: item.variant_index or (1 if item.variant_type.value == "STABLE" else 2),
    ):
        duration = int(
            variant.generation_config_json.get("duration")
            or variant.generation_config_json.get("durationSeconds")
            or settings.active_kling_duration
        )
        aspect_ratio = str(
            variant.generation_config_json.get("aspectRatio") or settings.active_kling_aspect_ratio
        )
        multi_shot = _resolve_multi_shot(variant.generation_config_json, settings)
        element_references = _resolve_element_references(variant.generation_config_json)
        request = VideoGenerationRequest(
            prompt=variant.prompt_text,
            model=settings.active_kling_model,
            image_paths=tuple(storyboard_paths),
            duration=duration,
            aspect_ratio=aspect_ratio,
            product_reference_paths=tuple(product_reference_paths),
            fallback_mode=settings.kling_storyboard_fallback_mode,
            task_trace_id=task.id.hex,
            resolution=settings.kling_api_resolution,
            audio=settings.kling_api_audio,
            multi_shot=multi_shot,
            external_task_id=f"{task.id.hex}-{variant.id.hex}-{variant.revision}",
            callback_url=settings.kling_api_callback_url,
            element_references=element_references,
        )
        model = await adapter.validate_request(request)
        intent_hash = sha256_json(
            {
                "userId": str(task.user_id),
                "parentTaskId": str(task.id),
                "childTaskType": variant.variant_key or variant.variant_type.value,
                "variantIndex": variant.variant_index,
                "provider": provider_name,
                "model": model,
                "inputAssetHash": sha256_json(
                    {
                        "storyboards": [asset.sha256 for asset in storyboard_assets],
                        "productReferences": [asset.sha256 for asset in product_reference_assets],
                    }
                ),
                "promptHash": variant.prompt_hash,
                "duration": duration,
                "aspectRatio": aspect_ratio,
                "resolution": settings.kling_api_resolution,
                "audio": settings.kling_api_audio,
                "multiShot": multi_shot,
                "elementIds": [item.element_id for item in element_references],
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
                provider=provider_name,
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
            "duration": duration,
            "aspectRatio": aspect_ratio,
            "resolution": settings.kling_api_resolution,
            "audio": settings.kling_api_audio,
            "multiShot": multi_shot,
            "elementIds": [item.element_id for item in element_references],
            "elementReferenceCount": len(element_references),
            "providerBackend": settings.kling_provider_backend,
            "providerName": provider_name,
            "storyboardFallbackMode": settings.kling_storyboard_fallback_mode,
            "storyboardImageCount": len(storyboard_assets),
            "productReferenceImageCount": len(product_reference_assets),
            "imageRolePolicy": "storyboard_ordered_subject_front_back_side_detail",
        }
        attempts.append(attempt)
    task.phase = ParentTaskPhase.QUEUED
    task.state_version += 1
    await session.commit()
    return attempts
