import uuid

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from libtv_agent.api.dependencies import Actor, Session, require_review_write
from libtv_agent.domain.models import CutflowHandoff
from libtv_agent.domain.schemas import ApiModel
from libtv_agent.services.cutflow_handoff import (
    CutflowHandoffError,
    configured,
    create_cutflow_handoff,
)
from sqlalchemy import select

router = APIRouter(prefix="/cutflow-handoffs", tags=["cutflow-handoffs"])


class CutflowHandoffCreate(ApiModel):
    task_id: uuid.UUID
    variant_id: uuid.UUID


def _read(handoff: CutflowHandoff) -> dict[str, object]:
    return {
        "id": handoff.id,
        "handoffKey": handoff.handoff_key,
        "sourceArtifactId": handoff.artifact_id,
        "status": handoff.status,
        "contractVersion": handoff.contract_version,
        "cutflowBatchId": handoff.cutflow_batch_id,
        "cutflowEditorUrl": handoff.cutflow_editor_url,
        "errorCode": handoff.error_code,
        "errorMessage": handoff.error_message,
        "createdAt": handoff.created_at,
        "updatedAt": handoff.updated_at,
        "outputs": [
            {
                "id": item["id"],
                "sha256": item["sha256"],
                "reviewStatus": item["review_status"],
                "durationSeconds": item["duration_seconds"],
                "createdAt": item["created_at"],
                "mediaUrl": f"/api/v1/cutflow-handoffs/{handoff.id}/outputs/{item['id']}",
            }
            for item in handoff.outputs_json or []
        ],
    }


@router.get("")
async def list_handoffs(
    actor: Actor,
    session: Session,
    request: Request,
    variant_id: uuid.UUID | None = None,
) -> dict[str, object]:
    if not configured(request.app.state.settings):
        return {"enabled": False, "handoffs": []}
    query = select(CutflowHandoff).where(CutflowHandoff.user_id == actor.id)
    if variant_id is not None:
        query = query.where(CutflowHandoff.variant_id == variant_id)
    rows = (await session.scalars(query.order_by(CutflowHandoff.created_at.desc()).limit(50))).all()
    return {"enabled": True, "handoffs": [_read(row) for row in rows]}


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_handoff(
    payload: CutflowHandoffCreate,
    actor: Actor,
    session: Session,
    request: Request,
) -> dict[str, object]:
    require_review_write(actor)
    try:
        handoff = await create_cutflow_handoff(
            session,
            settings=request.app.state.settings,
            object_store=request.app.state.object_store,
            user_id=actor.id,
            task_id=payload.task_id,
            variant_id=payload.variant_id,
        )
    except CutflowHandoffError as exc:
        code_to_status = {
            "CUTFLOW_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
            "CUTFLOW_HANDOFF_DISABLED": status.HTTP_503_SERVICE_UNAVAILABLE,
            "CUTFLOW_HANDOFF_ROOT_MISSING": status.HTTP_503_SERVICE_UNAVAILABLE,
            "TASK_NOT_FOUND": status.HTTP_404_NOT_FOUND,
            "VARIANT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        }
        raise HTTPException(
            code_to_status.get(exc.code, status.HTTP_409_CONFLICT),
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    await session.commit()
    return _read(handoff)


async def _owned(handoff_id: uuid.UUID, actor: Actor, session: Session) -> CutflowHandoff:
    handoff = await session.scalar(
        select(CutflowHandoff).where(
            CutflowHandoff.id == handoff_id,
            CutflowHandoff.user_id == actor.id,
        )
    )
    if handoff is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cutflow handoff was not found")
    return handoff


@router.post("/{handoff_id}/retry")
async def retry_handoff(handoff_id: uuid.UUID, actor: Actor, session: Session):
    require_review_write(actor)
    handoff = await _owned(handoff_id, actor, session)
    if handoff.status != "FAILED":
        raise HTTPException(status.HTTP_409_CONFLICT, "handoff is not failed")
    handoff.status = "READY" if handoff.manifest_path else "QUEUED"
    handoff.failure_count = 0
    handoff.next_run_at = None
    handoff.error_code = handoff.error_message = None
    await session.commit()
    return _read(handoff)


@router.get("/{handoff_id}/outputs/{output_id}")
async def output_media(
    handoff_id: uuid.UUID,
    output_id: str,
    actor: Actor,
    session: Session,
    request: Request,
) -> FileResponse:
    handoff = await _owned(handoff_id, actor, session)
    output = next((item for item in handoff.outputs_json or [] if item["id"] == output_id), None)
    if output is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edited output was not found")
    try:
        local = await request.app.state.object_store.localize(
            output["object_key"],
            request.app.state.settings.artifact_root
            / "cutflow-downloads"
            / f"{handoff.id}-{output_id}.mp4",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_410_GONE, "edited output has expired") from exc
    return FileResponse(local, media_type="video/mp4")


@router.get("/{handoff_id}")
async def get_handoff(
    handoff_id: uuid.UUID,
    actor: Actor,
    session: Session,
) -> dict[str, object]:
    handoff = await session.scalar(
        select(CutflowHandoff).where(
            CutflowHandoff.id == handoff_id,
            CutflowHandoff.user_id == actor.id,
        )
    )
    if handoff is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cutflow handoff was not found")
    return _read(handoff)
