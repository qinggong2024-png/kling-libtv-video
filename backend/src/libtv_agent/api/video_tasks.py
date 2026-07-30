from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.schemas import TaskRead, VideoTaskCreate
from libtv_agent.services.fixed_video_tasks import (
    FixedVideoTaskValidationError,
    create_fixed_video_task,
)
from libtv_agent.services.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    load_idempotent_response,
    release_idempotency_claim,
    store_idempotent_response,
)
from libtv_agent.services.subject_elements import schedule_subject_element_job
from libtv_agent.services.tasks import task_to_read

router = APIRouter(prefix="/video-tasks", tags=["video-tasks"])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_video_task(
    payload: VideoTaskCreate,
    actor: Actor,
    session: Session,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> TaskRead:
    operation = "CREATE_FIXED_VIDEO_TASK"
    payload_json = payload.model_dump(mode="json", by_alias=True)
    try:
        cached = await load_idempotent_response(
            session,
            tenant_id=str(actor.id),
            operation_type=operation,
            key=idempotency_key,
            payload=payload_json,
        )
    except (IdempotencyConflictError, IdempotencyInProgressError) as exc:
        code = (
            "IDEMPOTENCY_REQUEST_IN_PROGRESS"
            if isinstance(exc, IdempotencyInProgressError)
            else "IDEMPOTENCY_KEY_REUSED"
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": code, "message": str(exc)},
        ) from exc
    if cached:
        cached_result = TaskRead.model_validate(cached[1])
        schedule_subject_element_job(
            request.app,
            task_id=cached_result.id,
            user_id=actor.id,
        )
        return cached_result

    try:
        task = await create_fixed_video_task(
            session,
            user_id=actor.id,
            payload=payload,
            settings=request.app.state.settings,
            kling_adapter=request.app.state.kling_adapter,
            object_store=request.app.state.object_store,
        )
    except FixedVideoTaskValidationError as exc:
        await release_idempotency_claim(
            session,
            tenant_id=str(actor.id),
            operation_type=operation,
            key=idempotency_key,
            payload=payload_json,
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": str(exc), "details": exc.details},
        ) from exc
    except Exception:
        await release_idempotency_claim(
            session,
            tenant_id=str(actor.id),
            operation_type=operation,
            key=idempotency_key,
            payload=payload_json,
        )
        raise

    result = await task_to_read(
        session,
        task,
        request.app.state.settings.daily_user_points_limit,
    )
    await store_idempotent_response(
        session,
        tenant_id=str(actor.id),
        operation_type=operation,
        key=idempotency_key,
        payload=payload_json,
        response_status=status.HTTP_201_CREATED,
        response_body=result.model_dump(mode="json", by_alias=True),
    )
    await session.commit()
    if payload.subject_images:
        schedule_subject_element_job(
            request.app,
            task_id=task.id,
            user_id=actor.id,
        )
    return result
