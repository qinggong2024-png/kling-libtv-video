"""Transactional persistence boundary for MVP-4A Provider submission tickets.

This module stores the permission to reach a future adapter boundary. It does not
reserve quota, charge points, create a generation attempt, or call a Provider.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal, cast

from libtv_agent.creative.provider_submission_persistence import (
    ProviderSubmissionTicketRecord,
)
from libtv_agent.services.creative_provider_preflight import (
    CreativeProviderPreflight,
    CreativeProviderPreflightResult,
    ProviderApprovalManifest,
)
from libtv_agent.services.creative_provider_submission import (
    ProviderSubmissionAdmissionRejected,
    ProviderSubmissionResult,
    ProviderSubmissionTicket,
    ProviderSubmissionTicketState,
    SubmissionClaim,
    SubmissionTicketStore,
    admit_provider_submission,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

TicketState = Literal["READY_TO_SUBMIT", "SUBMITTED", "UNKNOWN", "FAILED", "INVALIDATED"]


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        raise ProviderSubmissionAdmissionRejected("TIMEZONE_REQUIRED")
    return current


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _ticket_payload(ticket: ProviderSubmissionTicket) -> dict[str, Any]:
    return cast(dict[str, Any], ticket.model_dump(mode="json"))


def _result_summary(result: ProviderSubmissionResult) -> str:
    return json.dumps(
        result.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )


def _record_values(ticket: ProviderSubmissionTicket) -> dict[str, Any]:
    payload = _ticket_payload(ticket)
    return {
        "schema_version": ticket.schema_version,
        "ticket_id": ticket.ticket_id,
        "status": ticket.status,
        "request_kind": ticket.request_kind,
        "execution_mode": ticket.execution_mode,
        "future_adapter_action": ticket.future_adapter_action,
        "owner_id": ticket.owner_id,
        "creative_task_id": ticket.creative_task_id,
        "package_revision_id": ticket.package_revision_id,
        "shot_id": ticket.shot_id,
        "provider": ticket.provider,
        "model": ticket.model,
        "idempotency_key": ticket.idempotency_key,
        "request_hash": ticket.request_hash,
        "evidence_hash": ticket.evidence_hash,
        "preflight_hash": ticket.preflight_hash,
        "expires_at": ticket.expires_at,
        "estimated_cost_micros": ticket.estimated_cost_micros,
        "currency": ticket.currency,
        "quota_units": ticket.quota_units,
        "manifest_path": str(ticket.manifest_path),
        "manifest_hash": ticket.manifest_hash,
        "materialized_inputs_json": payload["materialized_inputs"],
        "ticket_payload_json": payload,
    }


def _state_from_record(record: ProviderSubmissionTicketRecord) -> ProviderSubmissionTicketState:
    result = (
        ProviderSubmissionResult.model_validate(record.result_json)
        if record.result_json is not None
        else None
    )
    return ProviderSubmissionTicketState(
        ticket=ProviderSubmissionTicket.model_validate(record.ticket_payload_json),
        state=cast(TicketState, record.status),
        invalidation_reason=record.invalidation_reason,
        result=result,
    )


def _assert_same_ticket(
    record: ProviderSubmissionTicketRecord,
    ticket: ProviderSubmissionTicket,
) -> None:
    if record.ticket_id != ticket.ticket_id or record.ticket_payload_json != _ticket_payload(
        ticket
    ):
        raise ProviderSubmissionAdmissionRejected("IDEMPOTENCY_KEY_CONFLICT")


@asynccontextmanager
async def _transaction(session: AsyncSession) -> AsyncIterator[None]:
    """Use a savepoint when the caller already owns an outer transaction.

    The caller must commit an outer transaction before treating a claim as
    durable. PostgreSQL row locks are intentionally kept at this boundary, but
    this MVP only proves the SQLite behavior below.
    """

    if session.in_transaction():
        async with session.begin_nested():
            yield
    else:
        async with session.begin():
            yield


class DurableSubmissionTicketStore:
    """Database-backed ticket registry with a unique idempotency claim."""

    async def get(
        self,
        session: AsyncSession,
        idempotency_key: str,
    ) -> ProviderSubmissionTicketState | None:
        record = await session.scalar(
            select(ProviderSubmissionTicketRecord).where(
                ProviderSubmissionTicketRecord.idempotency_key == idempotency_key
            )
        )
        return _state_from_record(record) if record is not None else None

    async def claim_submission(
        self,
        session: AsyncSession,
        ticket: ProviderSubmissionTicket,
        *,
        now: datetime | None = None,
    ) -> SubmissionClaim:
        current_time = _now(now)
        if _as_utc(ticket.expires_at) <= _as_utc(current_time):
            existing = await self.get(session, ticket.idempotency_key)
            if existing is None:
                raise ProviderSubmissionAdmissionRejected("TICKET_EXPIRED")

        values = _record_values(ticket)
        insert_factory = (
            sqlite_insert
            if session.get_bind().dialect.name == "sqlite"
            else postgresql_insert
        )
        async with _transaction(session):
            inserted = await session.execute(
                insert_factory(ProviderSubmissionTicketRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
            record = await session.scalar(
                select(ProviderSubmissionTicketRecord)
                .where(ProviderSubmissionTicketRecord.idempotency_key == ticket.idempotency_key)
                .with_for_update()
            )
            if record is None:
                raise RuntimeError("durable submission ticket claim disappeared")
            if inserted.rowcount != 1:
                _assert_same_ticket(record, ticket)
            if (
                record.status == "READY_TO_SUBMIT"
                and _as_utc(ticket.expires_at) <= _as_utc(current_time)
            ):
                record.status = "INVALIDATED"
                record.invalidation_reason = "TICKET_EXPIRED"
                await session.flush()
            state = _state_from_record(record)
            return SubmissionClaim(
                ticket=state.ticket,
                state=state,
                created=inserted.rowcount == 1,
            )

    async def invalidate(
        self,
        session: AsyncSession,
        idempotency_key: str,
        reason: str,
    ) -> ProviderSubmissionTicketState:
        async with _transaction(session):
            record = await session.scalar(
                select(ProviderSubmissionTicketRecord)
                .where(ProviderSubmissionTicketRecord.idempotency_key == idempotency_key)
                .with_for_update()
            )
            if record is None:
                raise ProviderSubmissionAdmissionRejected("TICKET_NOT_FOUND")
            if record.status not in {"SUBMITTED", "UNKNOWN", "FAILED"}:
                record.status = "INVALIDATED"
                record.invalidation_reason = reason
                await session.flush()
            return _state_from_record(record)

    async def record_provider_result(
        self,
        session: AsyncSession,
        idempotency_key: str,
        result: ProviderSubmissionResult,
    ) -> ProviderSubmissionTicketState:
        async with _transaction(session):
            record = await session.scalar(
                select(ProviderSubmissionTicketRecord)
                .where(ProviderSubmissionTicketRecord.idempotency_key == idempotency_key)
                .with_for_update()
            )
            if record is None:
                raise ProviderSubmissionAdmissionRejected("TICKET_NOT_FOUND")
            ticket = ProviderSubmissionTicket.model_validate(record.ticket_payload_json)
            if (
                result.ticket_id != ticket.ticket_id
                or result.idempotency_key != ticket.idempotency_key
            ):
                raise ProviderSubmissionAdmissionRejected("SUBMISSION_RESULT_MISMATCH")
            if record.result_json is not None:
                if record.result_json == result.model_dump(mode="json"):
                    return _state_from_record(record)
                raise ProviderSubmissionAdmissionRejected("SUBMISSION_RESULT_CONFLICT")
            if record.status != "READY_TO_SUBMIT":
                raise ProviderSubmissionAdmissionRejected("TICKET_NOT_SUBMITTABLE")
            record.status = result.status
            record.result_status = result.status
            record.result_summary = _result_summary(result)
            record.result_json = cast(dict[str, Any], result.model_dump(mode="json"))
            record.provider_task_id = result.provider_task_id
            record.response_digest = result.response_digest
            record.error_code = result.error_code
            record.error_message = result.error_message
            record.invalidation_reason = (
                "EXECUTION_UNKNOWN"
                if result.status == "UNKNOWN"
                else "PROVIDER_SUBMISSION_FAILED"
                if result.status == "FAILED"
                else None
            )
            await session.flush()
            return _state_from_record(record)


async def admit_provider_submission_durable(
    session: AsyncSession,
    preflight: CreativeProviderPreflight | CreativeProviderPreflightResult,
    *,
    current_preflight: CreativeProviderPreflight | CreativeProviderPreflightResult,
    approval: ProviderApprovalManifest,
    store: DurableSubmissionTicketStore,
    now: datetime | None = None,
) -> SubmissionClaim:
    """Validate MVP-4A admission, then persist the resulting ticket."""

    candidate = preflight.result if isinstance(preflight, CreativeProviderPreflight) else preflight
    try:
        temporary_claim = admit_provider_submission(
            preflight,
            current_preflight=current_preflight,
            approval=approval,
            store=SubmissionTicketStore(),
            now=now,
        )
    except ProviderSubmissionAdmissionRejected as exc:
        existing = await store.get(session, candidate.idempotency_key)
        if existing is not None and existing.state == "READY_TO_SUBMIT":
            reason = {
                "PREFLIGHT_EXPIRED": "TICKET_EXPIRED",
                "PREFLIGHT_STALE": "SOURCE_CHANGED",
                "PROVIDER_APPROVAL_REVOKED": "AUTHORIZATION_REVOKED",
                "HUMAN_PROVIDER_AUTHORIZATION_EXPIRED": "AUTHORIZATION_REVOKED",
            }.get(exc.code, "ADMISSION_REJECTED")
            await store.invalidate(session, candidate.idempotency_key, reason)
        raise
    return await store.claim_submission(session, temporary_claim.ticket, now=now)


async def claim_durable_submission(
    session: AsyncSession,
    store: DurableSubmissionTicketStore,
    ticket: ProviderSubmissionTicket,
    *,
    now: datetime | None = None,
) -> SubmissionClaim:
    return await store.claim_submission(session, ticket, now=now)


async def record_durable_provider_submission_result(
    session: AsyncSession,
    store: DurableSubmissionTicketStore,
    ticket: ProviderSubmissionTicket,
    result: ProviderSubmissionResult,
) -> ProviderSubmissionTicketState:
    return await store.record_provider_result(session, ticket.idempotency_key, result)

