import asyncio
import base64
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from libtv_agent.adapters.kling_official_cli import KlingCliError
from libtv_agent.adapters.libtv import LibTVError
from libtv_agent.adapters.openai_analysis import AnalysisTimeoutError
from libtv_agent.api.dependencies import (
    Actor,
    Session,
    can_review_across_owners,
    require_review_write,
)
from libtv_agent.config import Settings
from libtv_agent.domain.contracts import sha256_json
from libtv_agent.domain.enums import (
    CANCELLABLE_PHASES,
    DownloadStatus,
    GenerationStatus,
    ParentTaskPhase,
    QualityDecisionStatus,
    ValidationStatus,
    VariantKind,
)
from libtv_agent.domain.models import (
    AuditEvent,
    GenerationAttempt,
    GenerationFeedback,
    GenerationVariant,
    ParentTask,
)
from libtv_agent.domain.schemas import (
    AnalyzeRequest,
    ConfirmRequest,
    FinalApprovalRequest,
    PromptAssistantRequest,
    PromptAssistantResponse,
    PromptUpdateRequest,
    ReorderRequest,
    RestoreRequest,
    TaskCreate,
    TaskRead,
    TaskReuseRequest,
    VariantFeedbackRequest,
)
from libtv_agent.runner.supervisor import RunnerSupervisor
from libtv_agent.services.analysis import analyze_task
from libtv_agent.services.analysis_lifecycle import (
    StaleAnalysisRunError,
    claim_analysis_run,
    fail_active_analysis,
)
from libtv_agent.services.confirmation import confirm_task
from libtv_agent.services.feedback_learning import (
    feedback_context_for_task,
    queue_feedback_learning_job,
    rebuild_deterministic_profile,
    schedule_feedback_learning_job,
)
from libtv_agent.services.generation_safety import (
    build_generation_preview,
    paid_generation_authorized,
)
from libtv_agent.services.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    load_idempotent_response,
    release_idempotency_claim,
    store_idempotent_response,
)
from libtv_agent.services.points import PointsLimitExceededError
from libtv_agent.services.prompt_revision import PromptRevisionTimeoutError, run_prompt_assistant
from libtv_agent.services.restore import RemoteRestoreInProgressError, restore_remote_output
from libtv_agent.services.runtime_control import RuntimeControlBlockedError
from libtv_agent.services.state_machine import (
    VersionConflictError,
    aggregate_parent_phase,
    cas_task_phase,
)
from libtv_agent.services.tasks import (
    TaskNotFoundError,
    create_task,
    get_task,
    list_tasks,
    reuse_task,
    task_to_read,
    tasks_to_read,
)
from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/tasks", tags=["tasks"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key")]
logger = logging.getLogger(__name__)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


async def _read(session: Session, task, settings: Settings) -> TaskRead:
    return await task_to_read(session, task, settings.daily_user_points_limit)


async def _persist_analysis_failure(
    app,
    task_id: uuid.UUID,
    analysis_run_id: uuid.UUID,
    *,
    reason_code: str,
    audit_action: str,
    reason: str,
) -> None:
    async def persist() -> None:
        async with app.state.database.session_factory() as recovery_session:
            await fail_active_analysis(
                recovery_session,
                task_id,
                reason_code=reason_code,
                audit_action=audit_action,
                reason=reason,
                analysis_run_id=analysis_run_id,
            )

    cleanup = asyncio.create_task(persist())
    try:
        await asyncio.shield(cleanup)
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None:
            while current.cancelling():
                current.uncancel()
        try:
            await cleanup
        except Exception:
            logger.exception(
                "cancelled analysis cleanup failed",
                extra={"task_id": str(task_id), "reason_code": reason_code},
            )
    except Exception:
        logger.exception(
            "failed to persist analysis terminal state",
            extra={"task_id": str(task_id), "reason_code": reason_code},
        )


async def _run_analysis_job(
    app,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    analysis_run_id: uuid.UUID,
) -> None:
    try:
        async with app.state.database.session_factory() as session:
            task = await get_task(session, user_id, task_id)
            await analyze_task(
                session,
                task,
                app.state.settings,
                app.state.object_store,
                app.state.kling_adapter,
                analysis_run_id=analysis_run_id,
            )
    except StaleAnalysisRunError:
        logger.info(
            "discarded stale analysis result",
            extra={"task_id": str(task_id), "analysis_run_id": str(analysis_run_id)},
        )
    except asyncio.CancelledError:
        await _persist_analysis_failure(
            app,
            task_id,
            analysis_run_id,
            reason_code="ANALYSIS_CANCELLED",
            audit_action="ANALYSIS_REQUEST_CANCELLED",
            reason="analysis background task was cancelled before completion",
        )
        raise
    except AnalysisTimeoutError as exc:
        await _persist_analysis_failure(
            app,
            task_id,
            analysis_run_id,
            reason_code="ANALYSIS_TIMEOUT",
            audit_action="ANALYSIS_REQUEST_TIMED_OUT",
            reason=str(exc),
        )
    except KlingCliError as exc:
        await _persist_analysis_failure(
            app,
            task_id,
            analysis_run_id,
            reason_code=exc.code,
            audit_action="ANALYSIS_REQUEST_REJECTED",
            reason=str(exc),
        )
    except (RuntimeError, ValueError) as exc:
        await _persist_analysis_failure(
            app,
            task_id,
            analysis_run_id,
            reason_code="ANALYSIS_SCHEMA_INVALID",
            audit_action="ANALYSIS_REQUEST_REJECTED",
            reason=str(exc),
        )
    except Exception as exc:
        await _persist_analysis_failure(
            app,
            task_id,
            analysis_run_id,
            reason_code="ANALYSIS_PROVIDER_FAILED",
            audit_action="ANALYSIS_REQUEST_FAILED",
            reason=type(exc).__name__,
        )
        logger.exception("analysis provider request failed", extra={"task_id": str(task_id)})


async def _persist_confirmation_failure(
    app,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    reason_code: str,
    reason: str,
    idempotency_key: str | None = None,
    payload_json: dict | None = None,
) -> None:
    async with app.state.database.session_factory() as session:
        if idempotency_key is not None:
            # The background job outlives the HTTP request that claimed this idempotency
            # key. If that request died -- client disconnect, app shutdown, process
            # restart -- nobody else will ever settle the claim, so it stays at
            # response_status=0 and every replay answers 409 IDEMPOTENCY_REQUEST_IN_PROGRESS
            # forever. Production held 11 such rows. release_idempotency_claim only deletes
            # rows that are still unsettled, so a request that already stored its response
            # is left alone.
            await release_idempotency_claim(
                session,
                tenant_id=str(user_id),
                operation_type=f"CONFIRM_TASK:{task_id}",
                key=idempotency_key,
                payload=payload_json or {},
            )
        task = await get_task(session, user_id, task_id)
        if task.phase != ParentTaskPhase.PREPARING:
            return
        task.phase = ParentTaskPhase.ACTION_REQUIRED
        task.phase_reason_code = reason_code
        task.state_version += 1
        session.add(
            AuditEvent(
                actor_id=user_id,
                action="CONFIRMATION_BACKGROUND_FAILED",
                entity_type="parent_task",
                entity_id=str(task_id),
                from_state=ParentTaskPhase.PREPARING.value,
                to_state=ParentTaskPhase.ACTION_REQUIRED.value,
                reason=reason,
                correlation_id=str(uuid.uuid4()),
                evidence_refs_json=[],
            )
        )
        await session.commit()


async def _run_confirmation_job(
    app,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    accept_risk: bool,
    expected_state_version: int,
    selected_variant_kinds: list[VariantKind] | None,
    preparing: asyncio.Future[None],
    idempotency_key: str | None = None,
    payload_json: dict | None = None,
) -> None:
    def mark_preparing() -> None:
        if not preparing.done():
            preparing.set_result(None)

    try:
        async with app.state.database.session_factory() as session:
            task = await get_task(session, user_id, task_id)
            await confirm_task(
                session,
                app.state.libtv_adapter,
                app.state.object_store,
                task,
                user_id,
                app.state.settings,
                kling_adapter=app.state.kling_adapter,
                accept_risk=accept_risk,
                expected_state_version=expected_state_version,
                selected_variant_kinds=selected_variant_kinds,
                on_preparing=mark_preparing,
            )
        mark_preparing()
    except asyncio.CancelledError:
        if not preparing.done():
            preparing.set_exception(asyncio.CancelledError())
        await _persist_confirmation_failure(
            app,
            task_id,
            user_id,
            reason_code="CONFIRMATION_CANCELLED",
            reason="background preparation was cancelled before completion",
            idempotency_key=idempotency_key,
            payload_json=payload_json,
        )
        raise
    except Exception as exc:
        if not preparing.done():
            preparing.set_exception(exc)
            return
        reason_code = str(getattr(exc, "code", "CONFIRMATION_BACKGROUND_FAILED"))
        await _persist_confirmation_failure(
            app,
            task_id,
            user_id,
            reason_code=reason_code,
            reason=str(exc),
            idempotency_key=idempotency_key,
            payload_json=payload_json,
        )
        logger.exception(
            "confirmation background preparation failed",
            extra={"task_id": str(task_id), "reason_code": reason_code},
        )


async def _cached(
    session: Session,
    actor_id: uuid.UUID,
    operation: str,
    key: str,
    payload: dict,
) -> TaskRead | None:
    try:
        cached = await load_idempotent_response(
            session,
            tenant_id=str(actor_id),
            operation_type=operation,
            key=key,
            payload=payload,
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
    return TaskRead.model_validate(cached[1]) if cached else None


def _encode_task_cursor(updated_at: datetime, task_id: uuid.UUID) -> str:
    payload = json.dumps(
        [updated_at.isoformat(), str(task_id)],
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_task_cursor(cursor: str | None) -> tuple[datetime | None, uuid.UUID | None]:
    if cursor is None:
        return None, None
    try:
        padding = "=" * (-len(cursor) % 4)
        updated_at_raw, task_id_raw = json.loads(
            base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
        )
        return datetime.fromisoformat(updated_at_raw), uuid.UUID(task_id_raw)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "CURSOR_INVALID", "message": "task cursor is invalid"},
        ) from exc


@router.get("", response_model=list[TaskRead])
async def get_tasks(
    actor: Actor,
    session: Session,
    request: Request,
    response: Response,
    limit: int = Query(default=100, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=300),
) -> list[TaskRead]:
    settings = _settings(request)
    cursor_updated_at, cursor_id = _decode_task_cursor(cursor)
    tasks = await list_tasks(
        session,
        actor.id,
        limit=limit + 1,
        cursor_updated_at=cursor_updated_at,
        cursor_id=cursor_id,
    )
    if len(tasks) > limit:
        tasks = tasks[:limit]
        last = tasks[-1]
        response.headers["X-Next-Cursor"] = _encode_task_cursor(last.updated_at, last.id)
    return await tasks_to_read(session, tasks, settings.daily_user_points_limit)


@router.get("/{task_id}/generation-preview")
async def get_generation_preview(
    task_id: uuid.UUID, actor: Actor, session: Session, request: Request
) -> dict[str, object]:
    task = await get_task(session, actor.id, task_id)
    rows = list(
        await session.execute(
            select(GenerationAttempt, GenerationVariant)
            .join(GenerationVariant, GenerationVariant.id == GenerationAttempt.variant_id)
            .where(GenerationVariant.parent_task_id == task.id)
            .order_by(GenerationAttempt.created_at)
        )
    )
    settings = _settings(request)
    commands = [
        build_generation_preview(
            executable=settings.libtv_executable,
            project_uuid=attempt.project_uuid or "",
            node_key=attempt.video_node_key or "",
            params=variant.generation_config_json,
            prompt_hash=variant.prompt_hash,
            execution_mode=settings.libtv_execution_mode,
            authorized=paid_generation_authorized(settings),
        )
        for attempt, variant in rows
        if attempt.video_node_key and attempt.project_uuid
    ]
    return {
        "taskId": str(task.id),
        "phase": task.phase.value,
        "previewFile": str(settings.runner_root / "previews" / f"{task.id}.json"),
        "commands": commands,
    }


@router.get("/{task_id}", response_model=TaskRead)
async def get_task_detail(
    task_id: uuid.UUID, actor: Actor, session: Session, request: Request
) -> TaskRead:
    try:
        task = await get_task(session, actor.id, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return await _read(session, task, _settings(request))


@router.put("/{task_id}/variants/{variant_id}/feedback", response_model=TaskRead)
async def put_variant_feedback(
    task_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: VariantFeedbackRequest,
    actor: Actor,
    session: Session,
    request: Request,
) -> TaskRead:
    try:
        task = await get_task(session, actor.id, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    variant = next((item for item in task.variants if item.id == variant_id), None)
    if variant is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "VARIANT_NOT_FOUND", "message": "task variant was not found"},
        )
    if variant.generation_status != GenerationStatus.SUCCEEDED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "FEEDBACK_NOT_READY",
                "message": "feedback is only available after video generation succeeds",
            },
        )
    existing = await session.scalar(
        select(GenerationFeedback).where(GenerationFeedback.variant_id == variant.id)
    )
    context = feedback_context_for_task(task, variant)
    learning_scope_key = context.get("learningScopeKey")
    previous = existing.value if existing is not None else None
    if payload.feedback is None:
        if existing is not None:
            await session.execute(
                delete(GenerationFeedback).where(GenerationFeedback.id == existing.id)
            )
    else:
        feedback_changed = previous != payload.feedback
        reason_codes = (
            [reason.value for reason in payload.reasons]
            if "reasons" in payload.model_fields_set and payload.reasons is not None
            else (
                []
                if feedback_changed or existing is None
                else list(existing.reason_codes_json or [])
            )
        )
        comment = (
            payload.comment
            if "comment" in payload.model_fields_set
            else (None if feedback_changed or existing is None else existing.comment)
        )
        if existing is None:
            session.add(
                GenerationFeedback(
                    user_id=actor.id,
                    parent_task_id=task.id,
                    variant_id=variant.id,
                    variant_type=variant.variant_type,
                    value=payload.feedback,
                    scene_key=context["sceneKey"],
                    context_json=context,
                    prompt_snapshot=variant.prompt_text,
                    reason_codes_json=reason_codes,
                    comment=comment,
                )
            )
        else:
            existing.value = payload.feedback
            existing.scene_key = context["sceneKey"]
            existing.context_json = context
            existing.prompt_snapshot = variant.prompt_text
            existing.reason_codes_json = reason_codes
            existing.comment = comment
    session.add(
        AuditEvent(
            action="GENERATION_FEEDBACK_UPDATED",
            entity_type="GenerationVariant",
            entity_id=str(variant.id),
            reason=(
                f"{previous.value if previous else 'NONE'}"
                f"->{payload.feedback.value if payload.feedback else 'NONE'}"
            ),
            correlation_id=uuid.uuid4().hex,
            evidence_refs_json=[
                variant.prompt_hash or "",
                variant.variant_type.value,
            ],
        )
    )
    queued_scope_key: str | None = None
    settings = _settings(request)
    if learning_scope_key and settings.feedback_learning_enabled:
        await session.flush()
        profile = await rebuild_deterministic_profile(
            session,
            user_id=actor.id,
            scope_key=str(learning_scope_key),
            max_history=settings.feedback_learning_max_history,
        )
        if (
            profile is not None
            and settings.feedback_learning_llm_enabled
            and settings.openai_api_key
        ):
            await queue_feedback_learning_job(session, profile=profile)
            queued_scope_key = profile.scope_key
    await session.commit()
    if queued_scope_key:
        schedule_feedback_learning_job(
            request.app,
            user_id=actor.id,
            scope_key=queued_scope_key,
        )
    return await _read(session, task, settings)


@router.put(
    "/{task_id}/variants/{variant_id}/final-approval",
    response_model=TaskRead,
)
async def put_variant_final_approval(
    task_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: FinalApprovalRequest,
    actor: Actor,
    session: Session,
    request: Request,
) -> TaskRead:
    require_review_write(actor)
    try:
        if can_review_across_owners(actor):
            task = await session.scalar(
                select(ParentTask)
                .where(ParentTask.id == task_id)
                .options(selectinload(ParentTask.variants), selectinload(ParentTask.assets))
            )
            if task is None:
                raise TaskNotFoundError("task was not found")
        else:
            task = await get_task(session, actor.id, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    variant = next((item for item in task.variants if item.id == variant_id), None)
    if variant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant was not found")
    if task.state_version != payload.expected_state_version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "VERSION_CONFLICT",
                "message": "task state changed; refresh before reviewing",
                "currentStateVersion": task.state_version,
            },
        )
    technical_pass = (
        variant.generation_status in {GenerationStatus.SUCCEEDED, GenerationStatus.PARTIAL}
        and variant.download_status == DownloadStatus.READY
        and variant.validation_status in {ValidationStatus.PASSED, ValidationStatus.WARNING}
    )
    if not technical_pass:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "TECHNICAL_HARD_GATE_NOT_PASSED",
                "message": "final approval requires a downloaded, technically valid video",
            },
        )
    previous = variant.final_approval_status
    variant.final_approval_status = QualityDecisionStatus(payload.decision)
    variant.quality_gates_json = {
        "PRODUCT_FIDELITY": {
            "verification": "HUMAN_REQUIRED",
            "outcome": "PASS" if payload.product_fidelity_pass else "FAIL",
        },
        "EDITING_ASSEMBLY": {
            "verification": "HUMAN_REQUIRED",
            "outcome": "PASS" if payload.editing_assembly_pass else "FAIL",
        },
        "HUMAN_CRITICAL": {
            "verification": "HUMAN_REQUIRED",
            "outcome": "PASS" if payload.human_critical_pass else "FAIL",
        },
        "TECHNICAL_CRITICAL": {
            "verification": "MACHINE_VERIFIED",
            "outcome": "PASS",
            "validationStatus": variant.validation_status.value,
        },
    }
    variant.final_approved_by = actor.id
    variant.final_approved_at = datetime.now(UTC)
    variant.human_review_seconds = payload.human_review_seconds
    variant.review_notes = payload.notes
    task.phase = aggregate_parent_phase(task.variants)
    task.phase_reason_code = (
        None
        if task.phase in {ParentTaskPhase.DELIVERABLE, ParentTaskPhase.PARTIALLY_DELIVERABLE}
        else "FINAL_APPROVAL_REJECTED"
    )
    task.state_version += 1
    session.add(
        AuditEvent(
            actor_id=actor.id,
            action="FINAL_VIDEO_APPROVAL",
            entity_type="generation_variant",
            entity_id=str(variant.id),
            from_state=previous.value,
            to_state=variant.final_approval_status.value,
            reason=payload.notes or "Required Hard Gates reviewed",
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[f"parent_task:{task.id}"],
        )
    )
    await session.commit()
    await session.refresh(task)
    return await _read(session, task, _settings(request))


def _validate_prompt_edit(task, expected_state_version: int) -> None:
    if task.phase != ParentTaskPhase.AWAITING_CONFIRMATION:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "PROMPT_LOCKED",
                "message": "prompts can only be edited while awaiting confirmation",
            },
        )
    if task.state_version != expected_state_version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "VERSION_CONFLICT",
                "message": "task state changed",
                "currentStateVersion": task.state_version,
            },
        )


def _apply_prompts(task, stable_prompt: str, dynamic_prompt: str) -> None:
    prompts = {
        VariantKind.STABLE: stable_prompt.strip(),
        VariantKind.DYNAMIC: dynamic_prompt.strip(),
    }
    for variant in task.variants:
        variant.prompt_text = prompts[variant.variant_type]
        variant.prompt_hash = sha256_json(variant.prompt_text)


async def _claim_prompt_update(session: Session, task: ParentTask) -> None:
    claimed = await session.execute(
        update(ParentTask)
        .where(
            ParentTask.id == task.id,
            ParentTask.phase == ParentTaskPhase.AWAITING_CONFIRMATION,
            ParentTask.state_version == task.state_version,
        )
        .values(state_version=ParentTask.state_version + 1)
        .execution_options(synchronize_session="fetch")
    )
    if claimed.rowcount == 1:
        return
    await session.rollback()
    current_state_version = await session.scalar(
        select(ParentTask.state_version).where(ParentTask.id == task.id)
    )
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        detail={
            "code": "VERSION_CONFLICT",
            "message": "task state changed",
            "currentStateVersion": current_state_version,
        },
    )


@router.patch("/{task_id}/prompts", response_model=TaskRead)
async def patch_task_prompts(
    task_id: uuid.UUID,
    payload: PromptUpdateRequest,
    actor: Actor,
    session: Session,
    request: Request,
) -> TaskRead:
    task = await get_task(session, actor.id, task_id)
    _validate_prompt_edit(task, payload.expected_state_version)
    await _claim_prompt_update(session, task)
    _apply_prompts(task, payload.stable_prompt, payload.dynamic_prompt)
    session.add(
        AuditEvent(
            actor_id=actor.id,
            action="EDIT_TASK_PROMPTS",
            entity_type="parent_task",
            entity_id=str(task.id),
            from_state=task.phase.value,
            to_state=task.phase.value,
            reason="manual prompt edit",
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[variant.prompt_hash or "" for variant in task.variants],
        )
    )
    await session.commit()
    task = await get_task(session, actor.id, task_id)
    return await _read(session, task, _settings(request))


@router.post("/{task_id}/prompt-assistant", response_model=PromptAssistantResponse)
async def post_prompt_assistant(
    task_id: uuid.UUID,
    payload: PromptAssistantRequest,
    actor: Actor,
    session: Session,
    request: Request,
) -> PromptAssistantResponse:
    task = await get_task(session, actor.id, task_id)
    _validate_prompt_edit(task, payload.expected_state_version)
    settings = _settings(request)
    model = next(
        (
            str(variant.generation_config_json.get("analysisModel"))
            for variant in task.variants
            if variant.generation_config_json.get("analysisModel")
        ),
        settings.openai_model,
    )
    revision_started_at = time.perf_counter()
    try:
        result = await run_prompt_assistant(
            settings,
            model=model,
            action=payload.action,
            instruction=payload.instruction,
            stable_prompt=payload.stable_prompt,
            dynamic_prompt=payload.dynamic_prompt,
            user_requirement=task.user_requirement_raw,
            analysis_result=task.analysis_result_json,
            target_variant=payload.target_variant.value if payload.target_variant else None,
        )
    except PromptRevisionTimeoutError as exc:
        if payload.action == "REGENERATE":
            elapsed = time.perf_counter() - revision_started_at
            task.analysis_duration_seconds += elapsed
            task.prompt_analysis_duration_seconds += elapsed
            task.analysis_attempt_count += 1
            await session.commit()
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"code": "PROMPT_ASSISTANT_TIMEOUT", "message": str(exc)},
        ) from exc
    except RuntimeError as exc:
        if payload.action == "REGENERATE":
            elapsed = time.perf_counter() - revision_started_at
            task.analysis_duration_seconds += elapsed
            task.prompt_analysis_duration_seconds += elapsed
            task.analysis_attempt_count += 1
            await session.commit()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={"code": "PROMPT_ASSISTANT_FAILED", "message": str(exc)},
        ) from exc
    if payload.action == "REGENERATE":
        elapsed = time.perf_counter() - revision_started_at
        task.analysis_duration_seconds += elapsed
        task.prompt_analysis_duration_seconds += elapsed
        task.analysis_attempt_count += 1
        stable_prompt = (
            payload.stable_prompt
            if payload.target_variant == VariantKind.DYNAMIC
            else result.stable_prompt
        )
        dynamic_prompt = (
            payload.dynamic_prompt
            if payload.target_variant == VariantKind.STABLE
            else result.dynamic_prompt
        )
        await _claim_prompt_update(session, task)
        _apply_prompts(task, stable_prompt, dynamic_prompt)
        session.add(
            AuditEvent(
                actor_id=actor.id,
                action="REGENERATE_TASK_PROMPTS",
                entity_type="parent_task",
                entity_id=str(task.id),
                from_state=task.phase.value,
                to_state=task.phase.value,
                reason="model-assisted prompt revision",
                correlation_id=str(uuid.uuid4()),
                evidence_refs_json=[variant.prompt_hash or "" for variant in task.variants],
            )
        )
        await session.commit()
        task = await get_task(session, actor.id, task_id)
    return PromptAssistantResponse(
        task=await _read(session, task, settings),
        advice=result.advice,
    )


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def post_task(
    payload: TaskCreate,
    actor: Actor,
    session: Session,
    request: Request,
    idempotency_key: IdempotencyKey,
) -> TaskRead:
    payload_json = payload.model_dump(mode="json", by_alias=True)
    if cached := await _cached(session, actor.id, "CREATE_TASK", idempotency_key, payload_json):
        return cached
    try:
        task = await create_task(session, actor.id, payload)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INPUT_INVALID", "message": str(exc)},
        ) from exc
    result = await _read(session, task, _settings(request))
    await store_idempotent_response(
        session,
        tenant_id=str(actor.id),
        operation_type="CREATE_TASK",
        key=idempotency_key,
        payload=payload_json,
        response_status=201,
        response_body=result.model_dump(mode="json", by_alias=True),
    )
    await session.commit()
    return result


@router.post(
    "/{task_id}/reuse",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_reuse_task(
    task_id: uuid.UUID,
    payload: TaskReuseRequest,
    actor: Actor,
    session: Session,
    request: Request,
    idempotency_key: IdempotencyKey,
) -> TaskRead:
    payload_json = payload.model_dump(mode="json", by_alias=True)
    operation = f"REUSE_TASK:{task_id}"
    if cached := await _cached(session, actor.id, operation, idempotency_key, payload_json):
        return cached
    try:
        source = await get_task(session, actor.id, task_id)
        task = await reuse_task(session, actor.id, source, payload)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INPUT_INVALID", "message": str(exc)},
        ) from exc
    result = await _read(session, task, _settings(request))
    await store_idempotent_response(
        session,
        tenant_id=str(actor.id),
        operation_type=operation,
        key=idempotency_key,
        payload=payload_json,
        response_status=201,
        response_body=result.model_dump(mode="json", by_alias=True),
    )
    await session.commit()
    return result


@router.patch("/{task_id}", response_model=TaskRead)
async def reorder_task(
    task_id: uuid.UUID,
    payload: ReorderRequest,
    actor: Actor,
    session: Session,
    request: Request,
    idempotency_key: IdempotencyKey,
) -> TaskRead:
    task = await get_task(session, actor.id, task_id)
    payload_json = payload.model_dump(mode="json", by_alias=True)
    if cached := await _cached(
        session, actor.id, f"REORDER_TASK:{task_id}", idempotency_key, payload_json
    ):
        return cached
    if task.phase != ParentTaskPhase.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "VERSION_CONFLICT", "message": "only DRAFT tasks can be reordered"},
        )
    if task.state_version != payload.expected_state_version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "VERSION_CONFLICT",
                "message": "task state changed",
                "currentStateVersion": task.state_version,
            },
        )
    if set(payload.ordered_asset_ids) != {asset.id for asset in task.assets}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INPUT_INVALID",
                "message": "orderedAssetIds must contain every task asset exactly once",
            },
        )
    by_id = {asset.id: asset for asset in task.assets}
    for order, asset_id in enumerate(payload.ordered_asset_ids, start=1):
        by_id[asset_id].order_no = -order
    await session.flush()
    for asset in task.assets:
        asset.order_no = -asset.order_no
    task.state_version += 1
    await session.commit()
    task = await get_task(session, actor.id, task_id)
    result = await _read(session, task, _settings(request))
    await store_idempotent_response(
        session,
        tenant_id=str(actor.id),
        operation_type=f"REORDER_TASK:{task_id}",
        key=idempotency_key,
        payload=payload_json,
        response_status=200,
        response_body=result.model_dump(mode="json", by_alias=True),
    )
    await session.commit()
    return result


@router.post(
    "/{task_id}/analyze",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_analyze(
    task_id: uuid.UUID,
    payload: AnalyzeRequest,
    actor: Actor,
    session: Session,
    request: Request,
    idempotency_key: IdempotencyKey,
) -> TaskRead:
    payload_json = payload.model_dump(mode="json", by_alias=True)
    if cached := await _cached(
        session, actor.id, f"ANALYZE_TASK:{task_id}", idempotency_key, payload_json
    ):
        return cached
    try:
        analysis_run_id = await claim_analysis_run(
            session,
            task_id,
            actor.id,
            payload.expected_state_version,
        )
    except VersionConflictError as exc:
        current = await get_task(session, actor.id, task_id)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "VERSION_CONFLICT",
                "message": str(exc),
                "currentStateVersion": current.state_version,
            },
        ) from exc
    task = await get_task(session, actor.id, task_id)
    result = await _read(session, task, _settings(request))
    await store_idempotent_response(
        session,
        tenant_id=str(actor.id),
        operation_type=f"ANALYZE_TASK:{task_id}",
        key=idempotency_key,
        payload=payload_json,
        response_status=status.HTTP_202_ACCEPTED,
        response_body=result.model_dump(mode="json", by_alias=True),
    )
    await session.commit()
    job = asyncio.create_task(_run_analysis_job(request.app, task_id, actor.id, analysis_run_id))
    request.app.state.analysis_jobs.add(job)
    job.add_done_callback(request.app.state.analysis_jobs.discard)
    return result


@router.post("/{task_id}/confirm", response_model=TaskRead)
async def post_confirm(
    task_id: uuid.UUID,
    payload: ConfirmRequest,
    actor: Actor,
    session: Session,
    request: Request,
    idempotency_key: IdempotencyKey,
) -> TaskRead:
    actor_id = actor.id
    payload_json = payload.model_dump(mode="json", by_alias=True)
    if cached := await _cached(
        session, actor_id, f"CONFIRM_TASK:{task_id}", idempotency_key, payload_json
    ):
        return cached
    task = await get_task(session, actor_id, task_id)
    if task.state_version != payload.expected_state_version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "VERSION_CONFLICT",
                "message": "task state changed",
                "currentStateVersion": task.state_version,
            },
        )
    settings = _settings(request)
    background_confirmation = (
        settings.libtv_adapter_mode == "real"
        and task.phase == ParentTaskPhase.AWAITING_CONFIRMATION
    )

    async def release_claim() -> None:
        # Called from every error path below. By then _cached has already inserted a
        # claim for this key, whether or not the request took the background branch, so
        # the release must not be gated on background_confirmation -- gating it left the
        # non-background path leaking a claim on every failure.
        await release_idempotency_claim(
            session,
            tenant_id=str(actor_id),
            operation_type=f"CONFIRM_TASK:{task_id}",
            key=idempotency_key,
            payload=payload_json,
        )

    try:
        if background_confirmation:
            # Release the request transaction before the worker claims PREPARING. This is
            # required by SQLite's single-writer model and also makes the HTTP response fast.
            await session.commit()
            preparing = asyncio.get_running_loop().create_future()
            job = asyncio.create_task(
                _run_confirmation_job(
                    request.app,
                    task_id,
                    actor_id,
                    accept_risk=payload.accept_risk,
                    expected_state_version=payload.expected_state_version,
                    selected_variant_kinds=payload.variants,
                    preparing=preparing,
                    # Hand the claim to the job: it outlives this request, so it is the
                    # only party that can still settle the key if this request dies.
                    idempotency_key=idempotency_key,
                    payload_json=payload_json,
                )
            )
            request.app.state.confirmation_jobs.add(job)
            job.add_done_callback(request.app.state.confirmation_jobs.discard)
            await preparing
            session.expire_all()
        else:
            await confirm_task(
                session,
                request.app.state.libtv_adapter,
                request.app.state.object_store,
                task,
                actor_id,
                settings,
                kling_adapter=request.app.state.kling_adapter,
                accept_risk=payload.accept_risk,
                expected_state_version=payload.expected_state_version,
                selected_variant_kinds=payload.variants,
            )
    except asyncio.CancelledError:
        await release_claim()
        raise
    except PointsLimitExceededError as exc:
        await release_claim()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": "POINTS_LIMIT_EXCEEDED", "message": str(exc)}
        ) from exc
    except RuntimeControlBlockedError as exc:
        await release_claim()
        raise HTTPException(
            status.HTTP_423_LOCKED, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except LibTVError as exc:
        await release_claim()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except KlingCliError as exc:
        await release_claim()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except VersionConflictError as exc:
        await release_claim()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "VERSION_CONFLICT", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        await release_claim()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "CONSISTENCY_REVIEW_REQUIRED", "message": str(exc)},
        ) from exc
    except Exception:
        await release_claim()
        raise
    if settings.auto_run_fake_commands and settings.libtv_adapter_mode in {"fake", "replay"}:
        await RunnerSupervisor(
            request.app.state.libtv_adapter,
            request.app.state.object_store,
            settings,
            kling_adapter=request.app.state.kling_adapter,
        ).run_ready(session)
    task = await get_task(session, actor_id, task_id)
    result = await _read(session, task, settings)
    await store_idempotent_response(
        session,
        tenant_id=str(actor_id),
        operation_type=f"CONFIRM_TASK:{task_id}",
        key=idempotency_key,
        payload=payload_json,
        response_status=200,
        response_body=result.model_dump(mode="json", by_alias=True),
    )
    await session.commit()
    return result


@router.post("/{task_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(
    task_id: uuid.UUID,
    actor: Actor,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> Response:
    operation = f"CANCEL_TASK:{task_id}"
    try:
        cached = await load_idempotent_response(
            session,
            tenant_id=str(actor.id),
            operation_type=operation,
            key=idempotency_key,
            payload={},
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
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    task = await get_task(session, actor.id, task_id)
    if task.phase not in CANCELLABLE_PHASES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "VERSION_CONFLICT", "message": "task can no longer be cancelled"},
        )
    try:
        await cas_task_phase(
            session, task.id, task.phase.value, task.state_version,
            ParentTaskPhase.CANCELLED.value,
        )
    except VersionConflictError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "VERSION_CONFLICT", "message": "task can no longer be cancelled"},
        ) from exc
    await store_idempotent_response(
        session,
        tenant_id=str(actor.id),
        operation_type=operation,
        key=idempotency_key,
        payload={},
        response_status=204,
        response_body={},
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/restore-remote-output")
async def restore_task_output(
    task_id: uuid.UUID,
    payload: RestoreRequest,
    actor: Actor,
    session: Session,
    request: Request,
    idempotency_key: IdempotencyKey,
) -> dict[str, str]:
    payload_json = payload.model_dump(mode="json", by_alias=True)
    try:
        cached = await load_idempotent_response(
            session,
            tenant_id=str(actor.id),
            operation_type=f"RESTORE_OUTPUT:{task_id}",
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
        return {key: str(value) for key, value in cached[1].items()}
    task = await get_task(session, actor.id, task_id)
    try:
        artifact = await restore_remote_output(
            session,
            request.app.state.libtv_adapter,
            request.app.state.object_store,
            _settings(request),
            task,
            payload.variant,
            actor.id,
            request.app.state.kling_adapter,
        )
    except (KlingCliError, LibTVError, ValueError) as exc:
        if isinstance(exc, RemoteRestoreInProgressError):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "DOWNLOAD_ALREADY_IN_PROGRESS",
                    "message": str(exc),
                },
            ) from exc
        code = (
            exc.code if isinstance(exc, (KlingCliError, LibTVError)) else "VALIDATION_MANUAL_REVIEW"
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": code, "message": str(exc)}
        ) from exc
    response = {
        "artifactId": str(artifact.id),
        "downloadUrl": f"/api/v1/downloads/{artifact.id}",
    }
    await store_idempotent_response(
        session,
        tenant_id=str(actor.id),
        operation_type=f"RESTORE_OUTPUT:{task_id}",
        key=idempotency_key,
        payload=payload_json,
        response_status=200,
        response_body=response,
    )
    await session.commit()
    return response
