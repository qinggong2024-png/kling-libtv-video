"""Durable input lease records for the Creative Provider boundary."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from libtv_agent.domain.models import Base


class ProviderInputLeaseRecord(Base):
    """Durable input manifest for one immutable Provider submission ticket.

    The lease owns staged input objects and their evidence. It deliberately has
    no relationship to image batches, attempts, quota, or accounting rows.
    """

    __tablename__ = "provider_input_lease"
    __table_args__ = (
        UniqueConstraint("lease_id", name="uq_provider_input_lease_lease_id"),
        UniqueConstraint("ticket_id", name="uq_provider_input_lease_ticket_id"),
        UniqueConstraint(
            "idempotency_key",
            name="uq_provider_input_lease_idempotency_key",
        ),
        Index("ix_provider_input_lease_owner_status", "owner_id", "status"),
        Index("ix_provider_input_lease_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    schema_version: Mapped[str] = mapped_column(String(80))
    lease_id: Mapped[str] = mapped_column(String(160))
    ticket_id: Mapped[str] = mapped_column(String(160))
    idempotency_key: Mapped[str] = mapped_column(String(240))
    owner_id: Mapped[str] = mapped_column(String(160), index=True)
    creative_task_id: Mapped[str] = mapped_column(String(160))
    package_revision_id: Mapped[str] = mapped_column(String(160))
    shot_id: Mapped[str] = mapped_column(String(40))
    request_hash: Mapped[str] = mapped_column(String(64))
    evidence_hash: Mapped[str] = mapped_column(String(64))
    request_kind: Mapped[str] = mapped_column(String(24))
    execution_mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    manifest_hash: Mapped[str] = mapped_column(String(64))
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_ticket_hash: Mapped[str] = mapped_column(String(64))
    invalidation_reason: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
