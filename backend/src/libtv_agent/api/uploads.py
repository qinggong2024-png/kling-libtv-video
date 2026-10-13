import asyncio
import hashlib
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.creative.media_qualification import is_offline_synthetic_output
from libtv_agent.domain.enums import QualityDecisionStatus
from libtv_agent.domain.models import (
    Asset,
    ImageGenerationBatch,
    ImageGenerationItem,
    ImageGenerationOutput,
    ParentTask,
    StagedUpload,
)
from libtv_agent.domain.schemas import UploadRead
from libtv_agent.services.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    load_idempotent_response,
    store_idempotent_response,
)
from libtv_agent.services.preprocessing import preprocess_image
from sqlalchemy import select

router = APIRouter(tags=["uploads"])


@router.post("/uploads", response_model=UploadRead, status_code=status.HTTP_201_CREATED)
async def upload_storyboard(
    actor: Actor,
    session: Session,
    request: Request,
    file: Annotated[UploadFile, File()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    source_image_output_id: Annotated[
        uuid.UUID | None, Header(alias="X-Source-Image-Output-Id")
    ] = None,
) -> UploadRead:
    settings = request.app.state.settings
    data = await file.read(settings.max_input_image_bytes + 1)
    if len(data) > settings.max_input_image_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"code": "INPUT_TOO_LARGE", "message": "image exceeds the configured limit"},
        )
    raw_sha256 = hashlib.sha256(data).hexdigest()
    if source_image_output_id is not None:
        row = (
            await session.execute(
            select(ImageGenerationOutput, ImageGenerationItem, ImageGenerationBatch)
            .join(ImageGenerationItem, ImageGenerationItem.id == ImageGenerationOutput.item_id)
            .join(ImageGenerationBatch, ImageGenerationBatch.id == ImageGenerationItem.batch_id)
            .where(
                ImageGenerationOutput.id == source_image_output_id,
                ImageGenerationBatch.user_id == actor.id,
            )
            )
        ).first()
        source_output = row[0] if row else None
        source_item = row[1] if row else None
        source_batch = row[2] if row else None
        if source_output is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "source image output was not found")
        if is_offline_synthetic_output(
            source_output, item=source_item, batch=source_batch
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "SOURCE_IMAGE_OFFLINE_SYNTHETIC",
                    "message": "offline synthetic source image cannot be uploaded for production",
                },
            )
        if source_output.qualification_status != QualityDecisionStatus.QUALIFIED:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "SOURCE_IMAGE_NOT_QUALIFIED",
                    "message": "source image output requires human qualification",
                },
            )
        if source_output.sha256 != raw_sha256:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "SOURCE_IMAGE_HASH_MISMATCH",
                    "message": "uploaded bytes do not match the qualified source image",
                },
            )
    payload = {
        "filename": file.filename or "storyboard",
        "sha256": raw_sha256,
        "sourceImageOutputId": str(source_image_output_id) if source_image_output_id else None,
    }
    try:
        cached = await load_idempotent_response(
            session,
            tenant_id=str(actor.id),
            operation_type="UPLOAD",
            key=idempotency_key,
            payload=payload,
        )
    except (IdempotencyConflictError, IdempotencyInProgressError) as exc:
        code = (
            "IDEMPOTENCY_REQUEST_IN_PROGRESS"
            if isinstance(exc, IdempotencyInProgressError)
            else "IDEMPOTENCY_KEY_REUSED"
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": code, "message": str(exc)}
        ) from exc
    if cached:
        return UploadRead.model_validate(cached[1])
    processed = None
    stored_keys: list[str] = []
    try:
        try:
            processed = await asyncio.to_thread(
                preprocess_image,
                data,
                file.filename or "storyboard",
                1,
                request.app.state.settings.artifact_root / "staging",
                max_bytes=settings.max_input_image_bytes,
            )
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "INPUT_INVALID", "message": str(exc)},
            ) from exc
        object_key = await request.app.state.object_store.put_file(
            processed.normalized_path,
            f"users/{actor.id}/inputs/{processed.asset_id}/normalized.jpg",
            "image/jpeg",
        )
        stored_keys.append(object_key)
        thumbnail_key = await request.app.state.object_store.put_file(
            processed.thumbnail_path,
            f"users/{actor.id}/thumbnails/{processed.asset_id}.jpg",
            "image/jpeg",
        )
        stored_keys.append(thumbnail_key)
        upload = StagedUpload(
            id=processed.asset_id,
            user_id=actor.id,
            original_filename=file.filename or "storyboard",
            sha256=processed.sha256,
            mime_type=processed.mime_type,
            size_bytes=processed.normalized_path.stat().st_size,
            width=processed.width,
            height=processed.height,
            object_key=object_key,
            thumbnail_key=thumbnail_key,
            source_image_output_id=source_image_output_id,
        )
        session.add(upload)
        response = UploadRead(
            id=upload.id,
            original_filename=upload.original_filename,
            sha256=upload.sha256,
            width=upload.width,
            height=upload.height,
            mime_type=upload.mime_type,
            size_bytes=upload.size_bytes,
            thumbnail_url=f"/api/v1/uploads/{upload.id}/thumbnail",
            source_image_output_id=upload.source_image_output_id,
        )
        await store_idempotent_response(
            session,
            tenant_id=str(actor.id),
            operation_type="UPLOAD",
            key=idempotency_key,
            payload=payload,
            response_status=201,
            response_body=response.model_dump(mode="json", by_alias=True),
        )
        await session.commit()
        return response
    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        await asyncio.gather(
            *(request.app.state.object_store.delete(key) for key in reversed(stored_keys)),
            return_exceptions=True,
        )
        raise
    finally:
        if processed is not None:
            await asyncio.to_thread(processed.normalized_path.unlink, missing_ok=True)
            await asyncio.to_thread(processed.thumbnail_path.unlink, missing_ok=True)


@router.get("/uploads/{upload_id}/thumbnail")
async def staged_thumbnail(
    upload_id: uuid.UUID, actor: Actor, session: Session, request: Request
) -> FileResponse:
    upload = await session.scalar(
        select(StagedUpload).where(StagedUpload.id == upload_id, StagedUpload.user_id == actor.id)
    )
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "upload was not found")
    try:
        local = await request.app.state.object_store.localize(
            upload.thumbnail_key,
            request.app.state.settings.artifact_root / "cache" / "thumbnails" / f"{upload.id}.jpg",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thumbnail file was not found") from exc
    return FileResponse(local, media_type="image/jpeg")


@router.get("/assets/{asset_id}/thumbnail")
async def asset_thumbnail(
    asset_id: uuid.UUID, actor: Actor, session: Session, request: Request
) -> FileResponse:
    asset = await session.scalar(
        select(Asset)
        .join(ParentTask, ParentTask.id == Asset.parent_task_id)
        .where(Asset.id == asset_id, ParentTask.user_id == actor.id)
    )
    if asset is None or not asset.thumbnail_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "asset was not found")
    try:
        local = await request.app.state.object_store.localize(
            asset.thumbnail_key,
            request.app.state.settings.artifact_root / "cache" / "thumbnails" / f"{asset.id}.jpg",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thumbnail file was not found") from exc
    return FileResponse(local, media_type="image/jpeg")
