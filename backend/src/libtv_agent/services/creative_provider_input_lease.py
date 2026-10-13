"""Local durable input leases; no Provider, accounting, or generation writes.

Every create/materialize replays persisted qualification and trusted approval
evidence through MVP-3B. Only this module's deterministic local objects are
written. Caller-owned outer transactions must be committed for durable replay.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from libtv_agent.adapters.object_store import LocalObjectStore, PrefixedObjectStore
from libtv_agent.config import Settings
from libtv_agent.creative.provider_input_lease import ProviderInputLeaseRecord
from libtv_agent.creative.provider_submission_persistence import ProviderSubmissionTicketRecord
from libtv_agent.creative.workflow import digest
from libtv_agent.domain.models import CreativeTask
from libtv_agent.services.creative_provider_preflight import (
    CreativeProviderPreflightRejected,
    ProviderCapabilityDeclaration,
    ProviderRequest,
    _read_approval,
    preflight_creative_provider_request,
)
from libtv_agent.services.creative_provider_requests import FrozenContract
from libtv_agent.services.creative_provider_submission import (
    ProviderSubmissionAdmissionRejected,
    ProviderSubmissionTicket,
    SubmissionTicketStore,
    admit_provider_submission,
)
from PIL import Image, UnidentifiedImageError
from pydantic import Field, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

LeaseStatus = Literal["ACTIVE", "MATERIALIZED", "EXPIRED", "REVOKED"]


class ProviderInputLeaseRejected(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DurableProviderInput(FrozenContract):
    role: Literal["PRODUCT", "FIRST_FRAME", "STORYBOARD"]
    order: int = Field(ge=1)
    adapter_field: str
    object_key: str
    durable_object_key: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    size_bytes: int = Field(gt=0)
    license_id: str
    license_evidence_id: str
    license_expires_at: datetime


class ProviderInputLease(FrozenContract):
    schema_version: Literal["creative-provider-input-lease.v1"] = (
        "creative-provider-input-lease.v1"
    )
    lease_id: str
    ticket_id: str
    idempotency_key: str
    owner_id: str
    creative_task_id: str
    package_revision_id: str
    shot_id: Literal["FIRST_FRAME", "SHOT_01"]
    request_kind: Literal["image", "video"]
    execution_mode: Literal["image_edit", "director_fixed"]
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    preflight_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_ticket_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime
    inputs: tuple[DurableProviderInput, ...] = Field(min_length=1)
    actual_submitted: Literal[False] = False
    provider_submission_allowed: Literal[False] = False
    qualification_scope: Literal["OFFLINE_SYNTHETIC_ONLY"] = "OFFLINE_SYNTHETIC_ONLY"
    deliverable_eligible: Literal[False] = False


class ProviderInputLeaseState(FrozenContract):
    lease: ProviderInputLease
    status: LeaseStatus
    invalidation_reason: str | None = None


class MaterializedLeaseInput(DurableProviderInput):
    path: Path


@dataclass
class MaterializedProviderInputLease:
    state: ProviderInputLeaseState
    inputs: tuple[MaterializedLeaseInput, ...]
    manifest_path: Path
    _directory: TemporaryDirectory[str]
    closed: bool = False

    def close(self) -> None:
        self._directory.cleanup()
        self.closed = True

    def __enter__(self) -> MaterializedProviderInputLease:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    async def __aenter__(self) -> MaterializedProviderInputLease:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.close()


def _reject(code: str) -> None:
    raise ProviderInputLeaseRejected(code)


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        _reject("TIMEZONE_REQUIRED")
    return current.astimezone(UTC)


def _local_store(store) -> None:
    inner = store
    while isinstance(inner, PrefixedObjectStore):
        inner = inner.inner
    if not isinstance(inner, LocalObjectStore):
        _reject("LOCAL_OBJECT_STORE_REQUIRED")


def _safe_key(key: str) -> None:
    if (
        not key
        or key.startswith(("/", "\\"))
        or "\\" in key
        or ":" in key
        or any(part in {"", ".", ".."} for part in key.split("/"))
        or re.search(r"[\x00-\x1f]", key)
    ):
        _reject("OBJECT_KEY_UNSAFE")


def _ticket_identity(ticket: ProviderSubmissionTicket) -> dict:
    # Temporary paths and their manifest hash cannot be a durable identity.
    payload = ticket.model_dump(mode="json", exclude={"manifest_path", "manifest_hash"})
    for entry in payload["materialized_inputs"]:
        entry.pop("path")
    return payload


def _inspect_file(path: Path, expected_hash: str) -> tuple[str, int]:
    if not path.is_file() or path.is_symlink():
        _reject("MATERIAL_INPUT_MISSING")
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
            size += len(chunk)
    if hasher.hexdigest() != expected_hash:
        _reject("MATERIAL_INPUT_HASH_MISMATCH")
    try:
        with Image.open(path) as image:
            media_type = Image.MIME.get(image.format)
            image.verify()
    except (OSError, UnidentifiedImageError, ValueError, SyntaxError):
        _reject("MEDIA_TYPE_INVALID")
    if media_type not in {"image/png", "image/jpeg", "image/webp"}:
        _reject("MEDIA_TYPE_UNSUPPORTED")
    return media_type, size


def _state(record: ProviderInputLeaseRecord) -> ProviderInputLeaseState:
    try:
        lease = ProviderInputLease.model_validate(record.manifest_json)
        if digest(record.manifest_json) != record.manifest_hash:
            _reject("LEASE_MANIFEST_CORRUPT")
        for field in (
            "schema_version", "lease_id", "ticket_id", "idempotency_key", "owner_id",
            "creative_task_id", "package_revision_id", "shot_id", "request_hash",
            "evidence_hash", "request_kind", "execution_mode", "source_ticket_hash",
        ):
            if getattr(record, field) != getattr(lease, field):
                _reject("LEASE_MANIFEST_CORRUPT")
        expiry = record.expires_at
        if (expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry) != lease.expires_at:
            _reject("LEASE_MANIFEST_CORRUPT")
        return ProviderInputLeaseState(
            lease=lease, status=record.status, invalidation_reason=record.invalidation_reason
        )
    except ValidationError as exc:
        raise ProviderInputLeaseRejected("LEASE_MANIFEST_CORRUPT") from exc


@asynccontextmanager
async def _transaction(session: AsyncSession) -> AsyncIterator[None]:
    if session.in_transaction():
        async with session.begin_nested():
            yield
    else:
        async with session.begin():
            yield


class DurableProviderInputLeaseStore:
    """Local/replay boundary, not a lock spanning a future Provider call."""

    async def get(
        self, session: AsyncSession, idempotency_key: str, *, owner_id: uuid.UUID
    ) -> ProviderInputLeaseState | None:
        with session.no_autoflush:
            record = await session.scalar(
                select(ProviderInputLeaseRecord)
                .where(ProviderInputLeaseRecord.idempotency_key == idempotency_key)
                .execution_options(populate_existing=True)
            )
        if record is None:
            return None
        if record.owner_id != str(owner_id):
            _reject("OWNER_MISMATCH")
        return _state(record)

    async def revoke(
        self, session: AsyncSession, idempotency_key: str, *,
        owner_id: uuid.UUID, reason: str = "AUTHORIZATION_REVOKED",
    ) -> ProviderInputLeaseState:
        async with _transaction(session):
            record = await session.scalar(
                select(ProviderInputLeaseRecord)
                .where(ProviderInputLeaseRecord.idempotency_key == idempotency_key)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if record is None:
                _reject("LEASE_NOT_FOUND")
            if record.owner_id != str(owner_id):
                _reject("OWNER_MISMATCH")
            if record.status in {"ACTIVE", "MATERIALIZED"}:
                record.status = "EXPIRED" if reason == "LEASE_EXPIRED" else "REVOKED"
                record.invalidation_reason = reason
                await session.flush()
            return _state(record)

    async def _validate(
        self, session, task, request, ticket, *, owner_id, object_store,
        settings, capability, approval_manifest_path, now,
    ):
        if ticket.owner_id != str(owner_id) or request.owner_id != str(owner_id):
            _reject("OWNER_MISMATCH")
        for entry in ticket.materialized_inputs:
            _safe_key(entry.object_key)
        with session.no_autoflush:
            saved = await session.scalar(
                select(ProviderSubmissionTicketRecord)
                .where(ProviderSubmissionTicketRecord.idempotency_key == ticket.idempotency_key)
                .execution_options(populate_existing=True)
            )
            if saved is None:
                _reject("DURABLE_TICKET_REQUIRED")
            if saved.ticket_payload_json != ticket.model_dump(mode="json"):
                _reject("IDEMPOTENCY_KEY_CONFLICT")
            if saved.status != "READY_TO_SUBMIT":
                _reject("TICKET_NOT_SUBMITTABLE")
            if ticket.expires_at.tzinfo is None or ticket.expires_at <= now:
                _reject("LEASE_EXPIRED")
            current = await preflight_creative_provider_request(
                session, task, request, owner_id=owner_id, object_store=object_store,
                settings=settings, capability=capability,
                approval_manifest_path=approval_manifest_path, now=now,
            )
        try:
            approval = await asyncio.to_thread(_read_approval, approval_manifest_path)
            fresh = admit_provider_submission(
                current, current_preflight=current, approval=approval,
                store=SubmissionTicketStore(), now=now,
            ).ticket
            if _ticket_identity(fresh) != _ticket_identity(ticket):
                _reject("SOURCE_CHANGED")
            return current, approval
        except BaseException:
            current.close()
            raise

    async def create(
        self, session: AsyncSession, task: CreativeTask, request: ProviderRequest,
        ticket: ProviderSubmissionTicket, *, owner_id: uuid.UUID, object_store,
        settings: Settings, capability: ProviderCapabilityDeclaration,
        approval_manifest_path: Path, now: datetime | None = None,
    ) -> ProviderInputLeaseState:
        """Persist verified local copies, independent of the old temporary paths."""
        _local_store(object_store)
        current_time = _now(now)
        existing = await self.get(session, ticket.idempotency_key, owner_id=owner_id)
        if existing is not None:
            if existing.lease.source_ticket_hash != digest(_ticket_identity(ticket)):
                _reject("IDEMPOTENCY_KEY_CONFLICT")
            await self.assert_current(
                session, task, request, ticket, owner_id=owner_id, object_store=object_store,
                settings=settings, capability=capability,
                approval_manifest_path=approval_manifest_path, now=current_time,
            )
            return existing
        current = None
        try:
            current, approval = await self._validate(
                session, task, request, ticket, owner_id=owner_id, object_store=object_store,
                settings=settings, capability=capability,
                approval_manifest_path=approval_manifest_path, now=current_time,
            )
            ticket_hash = digest(_ticket_identity(ticket))
            entries = []
            for entry, grant in zip(current.materialized_inputs, approval.licenses, strict=True):
                media_type, size = await asyncio.to_thread(
                    _inspect_file, entry.path, entry.sha256
                )
                key = f"creative-provider-inputs/{ticket_hash}/{entry.order}-{entry.sha256}"
                _safe_key(key)
                if not await object_store.exists(key):
                    key = await object_store.put_file(entry.path, key, media_type)
                path = await object_store.localize(key, entry.path)
                if await asyncio.to_thread(_inspect_file, path, entry.sha256) != (media_type, size):
                    _reject("DURABLE_INPUT_MISMATCH")
                entries.append(DurableProviderInput(
                    **entry.model_dump(exclude={"path"}), durable_object_key=key,
                    media_type=media_type, size_bytes=size, license_id=grant.license_id,
                    license_evidence_id=grant.evidence_id, license_expires_at=grant.expires_at,
                ))
            lease = ProviderInputLease(
                lease_id=f"pil:{ticket_hash}", ticket_id=ticket.ticket_id,
                idempotency_key=ticket.idempotency_key, owner_id=ticket.owner_id,
                creative_task_id=ticket.creative_task_id,
                package_revision_id=ticket.package_revision_id, shot_id=ticket.shot_id,
                request_kind=ticket.request_kind, execution_mode=ticket.execution_mode,
                request_hash=ticket.request_hash, evidence_hash=ticket.evidence_hash,
                preflight_hash=ticket.preflight_hash, source_ticket_hash=ticket_hash,
                approval_hash=digest(approval.model_dump(mode="json")),
                expires_at=min(ticket.expires_at, current.expires_at), inputs=tuple(entries),
            )
            # Recheck persisted evidence after local writes, before creating the lease.
            final, final_approval = await self._validate(
                session, task, request, ticket, owner_id=owner_id, object_store=object_store,
                settings=settings, capability=capability,
                approval_manifest_path=approval_manifest_path, now=_now(now),
            )
            final.close()
            if final_approval != approval:
                _reject("PROVIDER_APPROVAL_STALE")
            values = lease.model_dump(mode="python", include={
                "schema_version", "lease_id", "ticket_id", "idempotency_key", "owner_id",
                "creative_task_id", "package_revision_id", "shot_id", "request_hash",
                "evidence_hash", "request_kind", "execution_mode", "expires_at",
                "source_ticket_hash",
            })
            payload = lease.model_dump(mode="json")
            values.update(status="ACTIVE", manifest_json=payload, manifest_hash=digest(payload))
            dialect = session.get_bind().dialect.name
            if dialect not in {"sqlite", "postgresql"}:
                _reject("DATABASE_DIALECT_UNSUPPORTED")
            insert = sqlite_insert if dialect == "sqlite" else postgresql_insert
            async with _transaction(session):
                await session.execute(
                    insert(ProviderInputLeaseRecord).values(**values).on_conflict_do_nothing()
                )
                state = await self.get(session, ticket.idempotency_key, owner_id=owner_id)
                if state is None or state.lease != lease:
                    _reject("IDEMPOTENCY_KEY_CONFLICT")
                return state
        except (CreativeProviderPreflightRejected, ProviderSubmissionAdmissionRejected) as exc:
            raise ProviderInputLeaseRejected(exc.code) from exc
        finally:
            if current is not None:
                current.close()

    async def assert_current(
        self, session: AsyncSession, task: CreativeTask, request: ProviderRequest,
        ticket: ProviderSubmissionTicket, *, owner_id: uuid.UUID, object_store,
        settings: Settings, capability: ProviderCapabilityDeclaration,
        approval_manifest_path: Path, now: datetime | None = None,
    ) -> ProviderInputLeaseState:
        """Revalidate source/rights/qualification and durable bytes before use."""
        _local_store(object_store)
        current_time = _now(now)
        state = await self.get(session, ticket.idempotency_key, owner_id=owner_id)
        if state is None:
            _reject("LEASE_NOT_FOUND")
        if state.lease.source_ticket_hash != digest(_ticket_identity(ticket)):
            _reject("IDEMPOTENCY_KEY_CONFLICT")
        if state.status not in {"ACTIVE", "MATERIALIZED"}:
            _reject(f"LEASE_{state.status}")
        current = None
        try:
            if state.lease.expires_at <= current_time:
                _reject("LEASE_EXPIRED")
            current, approval = await self._validate(
                session, task, request, ticket, owner_id=owner_id, object_store=object_store,
                settings=settings, capability=capability,
                approval_manifest_path=approval_manifest_path, now=current_time,
            )
            if state.lease.approval_hash != digest(approval.model_dump(mode="json")):
                _reject("PROVIDER_APPROVAL_STALE")
            for entry in state.lease.inputs:
                _safe_key(entry.durable_object_key)
                if not await object_store.exists(entry.durable_object_key):
                    _reject("DURABLE_INPUT_MISSING")
                path = await object_store.localize(entry.durable_object_key, current.manifest_path)
                try:
                    observed = await asyncio.to_thread(_inspect_file, path, entry.sha256)
                except ProviderInputLeaseRejected as exc:
                    if exc.code in {"MATERIAL_INPUT_HASH_MISMATCH", "MEDIA_TYPE_INVALID",
                                    "MEDIA_TYPE_UNSUPPORTED"}:
                        _reject("DURABLE_INPUT_MISMATCH")
                    raise
                if observed != (entry.media_type, entry.size_bytes):
                    _reject("DURABLE_INPUT_MISMATCH")
            return state
        except (
            ProviderInputLeaseRejected, CreativeProviderPreflightRejected,
            ProviderSubmissionAdmissionRejected,
        ) as exc:
            await self.revoke(
                session, ticket.idempotency_key, owner_id=owner_id, reason=exc.code
            )
            raise ProviderInputLeaseRejected(exc.code) from exc
        finally:
            if current is not None:
                current.close()

    async def materialize(
        self, session: AsyncSession, task: CreativeTask, request: ProviderRequest,
        ticket: ProviderSubmissionTicket, *, owner_id: uuid.UUID, object_store,
        settings: Settings, capability: ProviderCapabilityDeclaration,
        approval_manifest_path: Path, now: datetime | None = None,
    ) -> MaterializedProviderInputLease:
        state = await self.assert_current(
            session, task, request, ticket, owner_id=owner_id, object_store=object_store,
            settings=settings, capability=capability,
            approval_manifest_path=approval_manifest_path, now=now,
        )
        directory = TemporaryDirectory(prefix="creative-durable-input-")
        try:
            entries = []
            for entry in state.lease.inputs:
                target = Path(directory.name) / str(entry.order)
                source = await object_store.localize(entry.durable_object_key, target)
                if source.resolve() != target.resolve():
                    await asyncio.to_thread(shutil.copyfile, source, target)
                if await asyncio.to_thread(_inspect_file, target, entry.sha256) != (
                    entry.media_type, entry.size_bytes
                ):
                    _reject("DURABLE_INPUT_MISMATCH")
                entries.append(MaterializedLeaseInput(**entry.model_dump(), path=target))
            manifest = Path(directory.name) / "manifest.json"
            payload = {
                "schema_version": "creative-provider-materialized-lease.v1",
                "lease_id": state.lease.lease_id,
                "request_hash": state.lease.request_hash,
                "evidence_hash": state.lease.evidence_hash,
                "references": [entry.model_dump(mode="json") for entry in entries],
            }
            await asyncio.to_thread(manifest.write_text, json.dumps(payload), encoding="utf-8")
            final = await self.assert_current(
                session, task, request, ticket, owner_id=owner_id, object_store=object_store,
                settings=settings, capability=capability,
                approval_manifest_path=approval_manifest_path, now=_now(now),
            )
            async with _transaction(session):
                row = await session.scalar(
                    select(ProviderInputLeaseRecord)
                    .where(ProviderInputLeaseRecord.idempotency_key == ticket.idempotency_key)
                    .with_for_update().execution_options(populate_existing=True)
                )
                if row.status not in {"ACTIVE", "MATERIALIZED"}:
                    _reject(f"LEASE_{row.status}")
                row.status = "MATERIALIZED"
                await session.flush()
                final = _state(row)
            return MaterializedProviderInputLease(final, tuple(entries), manifest, directory)
        except BaseException:
            directory.cleanup()
            raise
