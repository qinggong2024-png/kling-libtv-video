"""Durable SQLAlchemy record for the MVP-4B submission ticket boundary."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from libtv_agent.domain.models import Base


class ProviderSubmissionTicketRecord(Base):
    """Durable ticket snapshot; execution/accounting records remain separate."""

    __tablename__ = "provider_submission_ticket"
    __table_args__ = (
        UniqueConstraint("ticket_id", name="uq_provider_submission_ticket_ticket_id"),
        UniqueConstraint(
            "idempotency_key",
            name="uq_provider_submission_ticket_idempotency_key",
        ),
        Index(
            "ix_provider_submission_ticket_owner_status",
            "owner_id",
            "status",
        ),
        Index(
            "ix_provider_submission_ticket_task_status",
            "creative_task_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    schema_version: Mapped[str] = mapped_column(String(80))
    ticket_id: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), index=True)
    request_kind: Mapped[str] = mapped_column(String(24))
    execution_mode: Mapped[str] = mapped_column(String(32))
    future_adapter_action: Mapped[str] = mapped_column(String(80))
    owner_id: Mapped[str] = mapped_column(String(160), index=True)
    creative_task_id: Mapped[str] = mapped_column(String(160), index=True)
    package_revision_id: Mapped[str] = mapped_column(String(160))
    shot_id: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(200))
    idempotency_key: Mapped[str] = mapped_column(String(240))
    request_hash: Mapped[str] = mapped_column(String(64))
    evidence_hash: Mapped[str] = mapped_column(String(64))
    preflight_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    estimated_cost_micros: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(16))
    quota_units: Mapped[int] = mapped_column(Integer)
    manifest_path: Mapped[str] = mapped_column(String(1000))
    manifest_hash: Mapped[str] = mapped_column(String(64))
    materialized_inputs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    ticket_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    invalidation_reason: Mapped[str | None] = mapped_column(String(80))
    result_status: Mapped[str | None] = mapped_column(String(32))
    result_summary: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider_task_id: Mapped[str | None] = mapped_column(String(200))
    response_digest: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

