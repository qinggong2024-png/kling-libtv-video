import uuid
from pathlib import Path

from libtv_agent.adapters.kling_official_cli import (
    KlingCliError,
    KlingOfficialCliAdapter,
)
from libtv_agent.adapters.libtv import LibTVAdapter, LibTVError
from libtv_agent.adapters.object_store import ObjectStore
from libtv_agent.config import Settings
from libtv_agent.domain.enums import (
    AttemptStatus,
    ChargeStatus,
    DownloadStatus,
    ValidationStatus,
    VariantKind,
)
from libtv_agent.domain.models import (
    AuditEvent,
    DownloadArtifact,
    GenerationAttempt,
    GenerationVariant,
    ParentTask,
    PointsReservation,
)
from libtv_agent.services.media import download_with_retries, technical_validate
from libtv_agent.services.points import settle_points
from libtv_agent.services.state_machine import aggregate_parent_phase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class RemoteRestoreInProgressError(ValueError):
    """Raised when the normal result download is still running."""


async def restore_remote_output(
    session: AsyncSession,
    adapter: LibTVAdapter,
    object_store: ObjectStore,
    settings: Settings,
    task: ParentTask,
    kind: VariantKind,
    actor_id: uuid.UUID,
    kling_adapter: KlingOfficialCliAdapter | None = None,
) -> DownloadArtifact:
    variant = await session.scalar(
        select(GenerationVariant).where(
            GenerationVariant.parent_task_id == task.id,
            GenerationVariant.variant_type == kind,
        )
    )
    if variant is None:
        raise ValueError("variant was not found")
    if variant.download_status == DownloadStatus.DOWNLOADING:
        raise RemoteRestoreInProgressError("the result download is already in progress")
    attempt = await session.scalar(
        select(GenerationAttempt)
        .where(
            GenerationAttempt.variant_id == variant.id,
            GenerationAttempt.status == AttemptStatus.SUCCEEDED,
        )
        .order_by(GenerationAttempt.created_at.desc())
        .limit(1)
    )
    if attempt is None:
        raise ValueError("variant has no successful remote generation")
    latest_revision = (
        await session.scalar(
            select(DownloadArtifact.revision)
            .where(DownloadArtifact.attempt_id == attempt.id)
            .order_by(DownloadArtifact.revision.desc())
            .limit(1)
        )
        or 0
    )
    if attempt.provider != "libtv":
        if kling_adapter is None or not attempt.task_id:
            raise KlingCliError("KLING_REMOTE_STATUS_UNKNOWN", "Kling remote task is unavailable")
        kling_result = await kling_adapter.query(attempt.task_id)
        if kling_result.status not in {"succeeded", "partial"} or not kling_result.outputs:
            raise KlingCliError(
                "KLING_OUTPUT_URL_MISSING", "Kling remote output is no longer available"
            )
        output_url = kling_result.outputs[0].url
        download_adapter: object = kling_adapter
    else:
        result = await adapter.query_node_result(
            project_uuid=attempt.project_uuid or "", node_key=attempt.video_node_key or ""
        )
        if result.status != "SUCCEEDED" or not result.payload.get("videoUrl"):
            raise LibTVError("REMOTE_RESULT_EXPIRED", "remote output is no longer available")
        output_url = str(result.payload["videoUrl"])
        download_adapter = adapter
    destination = (
        settings.runner_root
        / "restores"
        / str(task.id)
        / f"restore-{kind.value.lower()}-v{latest_revision + 1}.mp4"
    )
    await download_with_retries(download_adapter, url=output_url, destination=destination)
    validation = await technical_validate(Path(destination))
    if not validation.passed:
        raise ValueError("restored video failed technical validation")
    output_key = (
        f"users/{task.user_id}/outputs/{task.id}/"
        f"restore-{kind.value.lower()}-v{latest_revision + 1}.mp4"
    )
    object_key = await object_store.put_file(
        destination,
        output_key,
        "video/mp4",
    )
    artifact = DownloadArtifact(
        attempt_id=attempt.id,
        status=DownloadStatus.READY,
        object_key=object_key,
        sha256=validation.sha256,
        size_bytes=validation.size_bytes,
        duration_seconds=validation.duration_seconds,
        width=validation.width,
        height=validation.height,
        has_audio=validation.has_audio,
        source_type="REMOTE_RESTORE",
        revision=latest_revision + 1,
    )
    session.add(artifact)
    session.add(
        AuditEvent(
            actor_id=actor_id,
            action="REMOTE_RESTORE",
            entity_type="generation_attempt",
            entity_id=str(attempt.id),
            reason=f"download artifact revision {latest_revision + 1}",
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[str(artifact.id)],
        )
    )
    variant.download_status = DownloadStatus.READY
    variant.validation_status = ValidationStatus.PASSED
    variants = list(
        await session.scalars(
            select(GenerationVariant).where(GenerationVariant.parent_task_id == task.id)
        )
    )
    task.phase = aggregate_parent_phase(variants)
    task.phase_reason_code = None
    task.state_version += 1
    reservation = await session.scalar(
        select(PointsReservation).where(PointsReservation.attempt_id == attempt.id)
    )
    if reservation:
        await settle_points(
            session,
            reservation,
            actual_points=(
                int(attempt.credits_consumed or reservation.estimated_points)
                if attempt.charge_status == ChargeStatus.CHARGED
                else None
            ),
            charge_status=attempt.charge_status,
        )
    await session.commit()
    return artifact
