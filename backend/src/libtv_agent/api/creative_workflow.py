from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from libtv_agent.api.dependencies import Actor, Session, require_review_write
from libtv_agent.creative.workflow import AssetLink, Command
from libtv_agent.domain.models import CreativeCreation, CreativeTask, Product
from libtv_agent.services.creative_package_export import with_creative_package_exports
from libtv_agent.services.creative_workflow import (
    create_task,
    execute,
    owned,
    persist_analysis_failure,
    reject,
)
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

router = APIRouter(prefix="/creative-workflow", tags=["creative-workflow"])


def director_response_mode(request: Request) -> str:
    settings = request.app.state.settings
    if settings.director_workflow_mode == "offline_demo":
        if settings.app_env != "test" or settings.ai_adapter_mode not in {"fake", "replay"}:
            reject("OFFLINE_WORKFLOW_DISABLED", 403)
        if settings.paid_generation_enabled:
            reject("PAID_MODE_NOT_ALLOWED", 403)
        if settings.object_store_mode != "local":
            reject("LOCAL_OBJECT_STORE_REQUIRED", 403)
        return "OFFLINE_FAKE_ONLY"
    if settings.director_workflow_mode == "live_director":
        return "LIVE_DIRECTOR"
    reject("DIRECTOR_WORKFLOW_MODE_INVALID", 500)


@router.get("/tasks")
async def list_tasks(
    request: Request,
    actor: Actor,
    session: Session,
    limit: int = Query(default=100, ge=1, le=200),
    cursor: uuid.UUID | None = Query(default=None),
) -> list[dict]:
    mode = director_response_mode(request)
    statement = (
        select(CreativeTask).join(Product, Product.id == CreativeTask.product_id)
        .where(CreativeTask.user_id == actor.id, Product.user_id == actor.id)
        .order_by(CreativeTask.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        anchor = await session.scalar(
            select(CreativeTask).join(Product, Product.id == CreativeTask.product_id).where(
                CreativeTask.id == cursor,
                CreativeTask.user_id == actor.id,
                Product.user_id == actor.id,
            )
        )
        if anchor is None:
            raise HTTPException(status_code=422, detail="Invalid history cursor")
        if anchor is not None:
            statement = statement.where(
                CreativeTask.id < anchor.id
            )
    creations = list((await session.scalars(statement)).all())
    has_more = len(creations) > limit
    creations = creations[:limit]
    results: list[dict] = []
    for creation in creations:
        task = creation
        results.append(with_creative_package_exports({
            "id": str(task.id),
            "status": task.status,
            "state_version": task.state_version,
            "snapshot": task.snapshot_json,
            "mode": mode,
            "recovery": {"created": True},
        }))
    if has_more and results:
        results[-1]["nextCursor"] = str(creations[-1].id)
    return results


@router.post("/tasks", status_code=201)
async def create(
    request: Request, actor: Actor, session: Session,
    product_id: Annotated[uuid.UUID, Form()],
    front: Annotated[UploadFile, File()],
    client_key: Annotated[str | None, Form()] = None,
    product_version_id: Annotated[uuid.UUID | None, Form()] = None,
    brand_profile_id: Annotated[str | None, Form(max_length=80)] = None,
    brand_profile_version: Annotated[str | None, Form(max_length=40)] = None,
) -> dict:
    mode = director_response_mode(request)
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
    ), client_key=client_key, product_version_id=product_version_id,
        brand_profile_id=brand_profile_id, brand_profile_version=brand_profile_version)
    result["mode"] = mode
    return with_creative_package_exports(result)


@router.get("/tasks/{task_id}")
async def read(task_id: uuid.UUID, request: Request, actor: Actor, session: Session) -> dict:
    mode = director_response_mode(request)
    task = await owned(session, task_id, actor.id)
    return with_creative_package_exports({
        "id": str(task.id), "status": task.status, "state_version": task.state_version,
        "snapshot": task.snapshot_json, "mode": mode,
        "recovery": {
            "created": True,
            "can_retry_analysis": task.status in {"DRAFT", "ANALYSIS_FAILED"},
            "analysis_failure": task.snapshot_json.get("analysis_failure"),
        },
    })


@router.get("/recovery/{client_key}")
async def recover(client_key: str, request: Request, actor: Actor, session: Session) -> dict:
    creation = await session.scalar(select(CreativeCreation).where(
        CreativeCreation.user_id == actor.id, CreativeCreation.client_key == client_key,
    ))
    if creation is None:
        reject("TASK_NOT_FOUND", 404)
    return await read(creation.task_id, request, actor, session)


@router.post("/tasks/{task_id}/commands")
async def command(
    task_id: uuid.UUID, payload: Command, request: Request, actor: Actor, session: Session,
) -> dict:
    actor_id = actor.id
    mode = director_response_mode(request)
    if mode == "LIVE_DIRECTOR" and payload.action not in {
        "analyze", "retry_analysis", "select_direction", "stop", "revoke_asset",
    }:
        reject("OFFLINE_COMMAND_NOT_ALLOWED", 403)
    require_review_write(actor)
    task = await owned(session, task_id, actor_id)
    try:
        result = await execute(
            session, task, payload, request.app.state.object_store, actor_id,
        )
        result["mode"] = mode
        return with_creative_package_exports(result)
    except OperationalError:
        await session.rollback()
        reject("RETRYABLE_DATABASE_CONFLICT")
    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        if payload.action not in {"analyze", "retry_analysis"}:
            raise
        await persist_analysis_failure(
            session, task_id, actor_id, payload.expected_version, payload.command_key,
        )
        reject("DIRECTOR_ANALYSIS_FAILED", 503)
