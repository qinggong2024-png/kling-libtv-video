import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status
from libtv_agent.adapters.kling_official_cli import KlingCliError
from libtv_agent.adapters.libtv import LibTVError
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.schemas import (
    BatchConfirmationRequest,
    BatchConfirmationResponse,
    BatchConfirmationResult,
)
from libtv_agent.runner.supervisor import RunnerSupervisor
from libtv_agent.services.confirmation import confirm_task
from libtv_agent.services.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    load_idempotent_response,
    release_idempotency_claim,
    store_idempotent_response,
)
from libtv_agent.services.points import PointsLimitExceededError
from libtv_agent.services.runtime_control import RuntimeControlBlockedError
from libtv_agent.services.state_machine import VersionConflictError
from libtv_agent.services.tasks import TaskNotFoundError, get_task, task_to_read

router = APIRouter(prefix="/confirmations", tags=["confirmations"])


def _confirmation_error_code(exc: Exception) -> str:
    if isinstance(exc, PointsLimitExceededError):
        return "POINTS_LIMIT_EXCEEDED"
    if isinstance(exc, TaskNotFoundError):
        return "TASK_NOT_FOUND"
    if isinstance(exc, VersionConflictError):
        return "VERSION_CONFLICT"
    if isinstance(exc, ValueError):
        return "CONFIRMATION_REJECTED"
    return str(getattr(exc, "code", type(exc).__name__.upper()))


@router.post("/preflight")
async def confirmation_preflight(
    payload: BatchConfirmationRequest, actor: Actor, session: Session, request: Request
) -> dict[str, object]:
    settings = request.app.state.settings
    try:
        tasks = [await get_task(session, actor.id, item.task_id) for item in payload.tasks]
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    variant_count = sum(len(task.variants) for task in tasks)
    return {
        "taskCount": len(tasks),
        "variantCount": variant_count,
        "estimatedPoints": variant_count * settings.generation_estimated_points,
        "dailyLimit": settings.daily_user_points_limit,
    }


@router.post("/execute", response_model=BatchConfirmationResponse)
async def execute_confirmations(
    payload: BatchConfirmationRequest,
    actor: Actor,
    session: Session,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> BatchConfirmationResponse:
    settings = request.app.state.settings
    payload_json = payload.model_dump(mode="json", by_alias=True)
    try:
        cached = await load_idempotent_response(
            session,
            tenant_id=str(actor.id),
            operation_type="BATCH_CONFIRM",
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
            status.HTTP_409_CONFLICT, detail={"code": code, "message": str(exc)}
        ) from exc
    if cached:
        return BatchConfirmationResponse.model_validate(cached[1])

    results: list[BatchConfirmationResult] = []
    confirmed_ids: list[uuid.UUID] = []
    known_errors = (
        LibTVError,
        KlingCliError,
        PointsLimitExceededError,
        RuntimeControlBlockedError,
        TaskNotFoundError,
        VersionConflictError,
        ValueError,
    )
    try:
        for item in payload.tasks:
            try:
                task = await get_task(session, actor.id, item.task_id)
                if task.state_version != item.expected_state_version:
                    results.append(
                        BatchConfirmationResult(
                            task_id=item.task_id,
                            status="FAILED",
                            error_code="VERSION_CONFLICT",
                            message=f"task {task.id} changed before confirmation",
                        )
                    )
                    continue
                await confirm_task(
                    session,
                    request.app.state.libtv_adapter,
                    request.app.state.object_store,
                    task,
                    actor.id,
                    settings,
                    kling_adapter=request.app.state.kling_adapter,
                    accept_risk=item.accept_risk,
                    expected_state_version=item.expected_state_version,
                )
                confirmed_ids.append(item.task_id)
                results.append(BatchConfirmationResult(task_id=item.task_id, status="SUCCEEDED"))
            except known_errors as exc:
                await session.rollback()
                results.append(
                    BatchConfirmationResult(
                        task_id=item.task_id,
                        status="FAILED",
                        error_code=_confirmation_error_code(exc),
                        message=str(exc),
                    )
                )

        if (
            confirmed_ids
            and settings.auto_run_fake_commands
            and settings.libtv_adapter_mode
            in {
                "fake",
                "replay",
            }
        ):
            await RunnerSupervisor(
                request.app.state.libtv_adapter,
                request.app.state.object_store,
                settings,
                kling_adapter=request.app.state.kling_adapter,
            ).run_ready(session)
        by_id = {result.task_id: result for result in results}
        for task_id in confirmed_ids:
            task = await get_task(session, actor.id, task_id)
            by_id[task_id].task = await task_to_read(
                session, task, settings.daily_user_points_limit
            )

        response = BatchConfirmationResponse(
            results=results,
            succeeded_count=sum(result.status == "SUCCEEDED" for result in results),
            failed_count=sum(result.status == "FAILED" for result in results),
        )
        await store_idempotent_response(
            session,
            tenant_id=str(actor.id),
            operation_type="BATCH_CONFIRM",
            key=idempotency_key,
            payload=payload_json,
            response_status=200,
            response_body=response.model_dump(mode="json", by_alias=True),
        )
        await session.commit()
        return response
    except Exception:
        await session.rollback()
        await release_idempotency_claim(
            session,
            tenant_id=str(actor.id),
            operation_type="BATCH_CONFIRM",
            key=idempotency_key,
            payload=payload_json,
        )
        raise
