import uuid

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.models import (
    DownloadArtifact,
    GenerationAttempt,
    GenerationVariant,
    ParentTask,
)
from sqlalchemy import select

router = APIRouter(prefix="/downloads", tags=["downloads"])


async def _owned_artifact(
    artifact_id: uuid.UUID, actor: Actor, session: Session
) -> tuple[DownloadArtifact, GenerationVariant, ParentTask]:
    row = await session.execute(
        select(DownloadArtifact, GenerationVariant, ParentTask)
        .join(GenerationAttempt, GenerationAttempt.id == DownloadArtifact.attempt_id)
        .join(GenerationVariant, GenerationVariant.id == GenerationAttempt.variant_id)
        .join(ParentTask, ParentTask.id == GenerationVariant.parent_task_id)
        .where(DownloadArtifact.id == artifact_id, ParentTask.user_id == actor.id)
    )
    result = row.first()
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "download artifact was not found")
    return result


@router.get("/{artifact_id}/url")
async def signed_download_url(
    artifact_id: uuid.UUID, actor: Actor, session: Session, request: Request
) -> dict[str, object]:
    artifact, _, _ = await _owned_artifact(artifact_id, actor, session)
    if not artifact.object_key:
        raise HTTPException(status.HTTP_410_GONE, "server copy has expired; use remote restore")
    expires_seconds = 300
    signed = await request.app.state.object_store.presign_get(
        artifact.object_key, expires_seconds=expires_seconds
    )
    return {
        "url": signed or f"/api/v1/downloads/{artifact.id}",
        "expiresInSeconds": expires_seconds,
        "directObjectStore": signed is not None,
    }


@router.get("/{artifact_id}")
async def download_artifact(
    artifact_id: uuid.UUID, actor: Actor, session: Session, request: Request
) -> FileResponse:
    artifact, variant, task = await _owned_artifact(artifact_id, actor, session)
    if not artifact.object_key:
        raise HTTPException(status.HTTP_410_GONE, "server copy has expired; use remote restore")
    try:
        local = await request.app.state.object_store.localize(
            artifact.object_key,
            request.app.state.settings.artifact_root / "cache" / "downloads" / f"{artifact.id}.mp4",
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status.HTTP_410_GONE, "server copy has expired; use remote restore"
        ) from exc
    return FileResponse(
        local,
        media_type="video/mp4",
        filename=f"{task.title}-{variant.variant_type.value.lower()}.mp4",
    )
