"""Safe local reconciliation; this endpoint never submits or polls a provider."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Response
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.models import (
    ApiIdempotencyRecord,
    AuditEvent,
    ImageGenerationBatch,
    ParentTask,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import noload

router = APIRouter(prefix="/submission-recovery", tags=["submission-recovery"])


class RecoveryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["video", "image"]
    client_id: str | None = Field(default=None, alias="clientId", min_length=1, max_length=160)
    idempotency_key: str | None = Field(
        default=None, alias="idempotencyKey", min_length=1, max_length=200
    )

    @model_validator(mode="after")
    def require_identity(self) -> "RecoveryQuery":
        if not self.client_id and not self.idempotency_key:
            raise ValueError("clientId or idempotencyKey is required")
        return self


class RecoveryRead(BaseModel):
    authority: Literal["server"] = "server"
    source: Literal["local_database"] = "local_database"
    state: Literal["submitted", "in_progress", "unknown", "not_found"]
    resourceId: str | None = None
    resourceStatus: str | None = None
    stateVersion: int | None = None
    checkedAt: datetime
    auditId: str
    retryAllowed: Literal[False] = False
    requiresAdminReview: bool


@router.post("/query", response_model=RecoveryRead)
async def query_submission(
    payload: RecoveryQuery, actor: Actor, session: Session, response: Response
) -> RecoveryRead:
    response.headers["Cache-Control"] = "no-store"
    checked_at = datetime.now(UTC)
    state = "not_found"
    resource = None
    record = None
    if payload.kind == "image":
        statement = select(ImageGenerationBatch).where(ImageGenerationBatch.user_id == actor.id)
        if payload.client_id:
            statement = statement.where(ImageGenerationBatch.client_batch_id == payload.client_id)
        if payload.idempotency_key:
            statement = statement.where(
                ImageGenerationBatch.idempotency_key == payload.idempotency_key
            )
        matches = list(await session.scalars(statement.options(noload("*")).limit(2)))
        if len(matches) == 1:
            resource = matches[0]
        elif matches:
            state = "unknown"
    else:
        if payload.idempotency_key:
            record = await session.scalar(
                select(ApiIdempotencyRecord).where(
                    ApiIdempotencyRecord.tenant_id == str(actor.id),
                    ApiIdempotencyRecord.operation_type == "CREATE_FIXED_VIDEO_TASK",
                    ApiIdempotencyRecord.idempotency_key == payload.idempotency_key,
                )
            )
        task_id = None
        if record and record.response_status:
            try:
                task_id = uuid.UUID(str(record.response_body_json.get("id")))
            except (ValueError, TypeError, AttributeError):
                pass
        if payload.client_id or task_id:
            statement = select(ParentTask).where(ParentTask.user_id == actor.id)
            if payload.client_id:
                statement = statement.where(ParentTask.client_task_id == payload.client_id)
            if task_id:
                statement = statement.where(ParentTask.id == task_id)
            resource = await session.scalar(statement.options(noload("*")))
        if record:
            state = "in_progress" if record.response_status == 0 else "unknown"
    if resource is not None:
        state = "submitted"
    stale_claim = bool(
        state == "in_progress"
        and record
        and record.created_at.replace(tzinfo=UTC) <= checked_at - timedelta(minutes=15)
    )

    # Store only an opaque identity digest, never request bodies, URLs or provider credentials.
    identity = f"{payload.kind}:{payload.client_id or ''}:{payload.idempotency_key or ''}"
    audit = AuditEvent(
        id=uuid.uuid4(),
        actor_id=actor.id,
        action="SUBMISSION_RECOVERY_QUERY",
        entity_type="submission_recovery",
        entity_id=hashlib.sha256(identity.encode()).hexdigest(),
        to_state=state,
        reason="local_database_lookup_only",
        correlation_id=str(uuid.uuid4()),
    )
    session.add(audit)
    result = RecoveryRead(
        state=state,
        resourceId=str(resource.id) if resource else None,
        resourceStatus=(
            resource.phase.value if isinstance(resource, ParentTask) else resource.status
        ) if resource else None,
        stateVersion=resource.state_version if isinstance(resource, ParentTask) else None,
        checkedAt=checked_at,
        auditId=str(audit.id),
        requiresAdminReview=stale_claim or state in {"unknown", "not_found"},
    )
    await session.commit()
    return result
