from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from libtv_agent.api.dependencies import Actor, Session, require_review_write
from libtv_agent.creative.workflow import AssetLink, Command
from libtv_agent.domain.models import Product
from libtv_agent.services.creative_workflow import create_task, execute, owned, reject
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

router = APIRouter(prefix="/creative-workflow", tags=["creative-workflow-offline"])


def offline_only(request: Request) -> None:
    settings = request.app.state.settings
    if settings.app_env != "test" or settings.ai_adapter_mode not in {"fake", "replay"}:
        reject("OFFLINE_WORKFLOW_DISABLED", 403)
    if settings.paid_generation_enabled:
        reject("PAID_MODE_NOT_ALLOWED", 403)
    if settings.object_store_mode != "local":
        reject("LOCAL_OBJECT_STORE_REQUIRED", 403)


@router.post("/tasks", status_code=201)
async def create(
    request: Request, actor: Actor, session: Session,
    product_id: Annotated[uuid.UUID, Form()],
    front: Annotated[UploadFile, File()],
    client_key: Annotated[str | None, Form()] = None,
    product_version_id: Annotated[uuid.UUID | None, Form()] = None,
) -> dict:
    offline_only(request)
    require_review_write(actor)
    product = await session.scalar(select(Product).where(
        Product.id == product_id, Product.user_id == actor.id,
    ))
    if product is None:
        reject("PRODUCT_NOT_FOUND", 404)
    await front.seek(0)
    data = await front.read(10 * 1024 * 1024 + 1)
    if not data or len(data) > 10 * 1024 * 1024:
        reject("IMAGE_SIZE_INVALID", 422)
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                reject("IMAGE_FORMAT_INVALID", 422)
            width, height = image.size
            if width * height > 40_000_000:
                reject("IMAGE_DIMENSIONS_INVALID", 422)
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        reject("IMAGE_INVALID", 422)
    sha = hashlib.sha256(data).hexdigest()
    key = f"creative-offline/{actor.id}/{sha}"
    store = request.app.state.object_store
    # Reuse the local store's normal put_file contract; uploaded files never become URLs.
    with TemporaryDirectory(prefix="cw-upload-") as directory:
        local = Path(directory) / "front"
        local.write_bytes(data)
        await store.put_file(local, key, "application/octet-stream")
    result = await create_task(session, actor.id, product_id, AssetLink(
        owner_id=actor.id, object_key=key, sha256=sha, width=width, height=height,
    ), client_key=client_key, product_version_id=product_version_id)
    return result


@router.get("/tasks/{task_id}")
async def read(task_id: uuid.UUID, request: Request, actor: Actor, session: Session) -> dict:
    offline_only(request)
    task = await owned(session, task_id, actor.id)
    return {
        "id": str(task.id), "status": task.status, "state_version": task.state_version,
        "snapshot": task.snapshot_json, "mode": "OFFLINE_FAKE_ONLY",
    }


@router.post("/tasks/{task_id}/commands")
async def command(
    task_id: uuid.UUID, payload: Command, request: Request, actor: Actor, session: Session,
) -> dict:
    offline_only(request)
    require_review_write(actor)
    task = await owned(session, task_id, actor.id)
    try:
        return await execute(session, task, payload, request.app.state.object_store, actor.id)
    except OperationalError:
        await session.rollback()
        reject("RETRYABLE_DATABASE_CONFLICT")
