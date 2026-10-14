"""Fresh qualification and ownership checks at video admission and execution."""
from __future__ import annotations

import uuid
from collections.abc import Iterable

from libtv_agent.creative.media_qualification import is_offline_synthetic_output
from libtv_agent.domain.enums import QualityDecisionStatus
from libtv_agent.domain.models import (
    Asset,
    GenerationVariant,
    ImageGenerationBatch,
    ImageGenerationItem,
    ImageGenerationOutput,
    ParentTask,
)
from libtv_agent.services.creative_production_context import (
    source_lineage,
    validate_bound_package,
)
from libtv_agent.services.runtime_control import RuntimeControlBlockedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class VideoInputBlockedError(RuntimeControlBlockedError):
    pass


async def validate_video_sources(
    session: AsyncSession, owner_id: uuid.UUID, inputs: Iterable,
) -> list[dict]:
    lineage = []
    for asset in inputs:
        output_id = asset.source_image_output_id
        if output_id is None:
            continue  # Original user uploads retain their existing admission contract.
        row = (await session.execute(
            select(ImageGenerationOutput, ImageGenerationItem, ImageGenerationBatch)
            .join(ImageGenerationItem, ImageGenerationItem.id == ImageGenerationOutput.item_id)
            .join(ImageGenerationBatch, ImageGenerationBatch.id == ImageGenerationItem.batch_id)
            .where(ImageGenerationOutput.id == output_id, ImageGenerationBatch.user_id == owner_id)
            .with_for_update(of=ImageGenerationOutput)
            .execution_options(populate_existing=True)
        )).first()
        if row is None:
            raise VideoInputBlockedError(
                "SOURCE_IMAGE_NOT_FOUND", "source image does not belong to the task owner",
            )
        output, item, batch = row
        if is_offline_synthetic_output(output, item=item, batch=batch):
            raise VideoInputBlockedError(
                "SOURCE_IMAGE_OFFLINE_SYNTHETIC", "synthetic image cannot enter video generation",
            )
        if output.qualification_status != QualityDecisionStatus.QUALIFIED:
            raise VideoInputBlockedError(
                "SOURCE_IMAGE_NOT_QUALIFIED", f"source image {output.id} is not QUALIFIED",
            )
        if not output.object_key or not output.sha256:
            raise VideoInputBlockedError(
                "SOURCE_IMAGE_UNAVAILABLE", "qualified source has no durable media",
            )
        source = source_lineage(output, item, batch)
        if source.get("creativePackage"):
            await validate_bound_package(session, owner_id, source["creativePackage"])
        lineage.append({
            **source, "inputId": str(asset.id),
            "order": asset.order_no if isinstance(asset, Asset) else None,
        })
    return lineage


async def validate_task_video_sources(session: AsyncSession, task: ParentTask) -> list[dict]:
    assets = await session.scalars(
        select(Asset).where(
            Asset.parent_task_id == task.id,
            Asset.used_for_generation.is_(True),
        ).order_by(Asset.order_no)
    )
    lineage = await validate_video_sources(session, task.user_id, assets)
    current_hashes = {
        source["sourceImageOutputId"]: source["sourceImageHash"] for source in lineage
    }
    variants = await session.scalars(
        select(GenerationVariant).where(GenerationVariant.parent_task_id == task.id)
        .execution_options(populate_existing=True)
    )
    for variant in variants:
        for source in (variant.generation_config_json or {}).get("sourceLineage", []):
            if current_hashes.get(source["sourceImageOutputId"]) != source["sourceImageHash"]:
                raise VideoInputBlockedError(
                    "SOURCE_IMAGE_CHANGED", "video source image lineage no longer matches",
                )
        context = (variant.generation_config_json or {}).get("creativePackage")
        if context:
            await validate_bound_package(session, task.user_id, context)
    return lineage
