from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from libtv_agent.adapters.object_store import LocalObjectStore
from libtv_agent.creative.provider_input_lease import ProviderInputLeaseRecord
from libtv_agent.creative.provider_submission_persistence import ProviderSubmissionTicketRecord
from libtv_agent.services.creative_provider_input_lease import (
    DurableProviderInputLeaseStore,
    ProviderInputLeaseRejected,
)
from libtv_agent.services.creative_provider_preflight import (
    ProviderApprovalManifest,
    ProviderReferenceLicense,
)
from libtv_agent.services.creative_provider_submission import (
    ProviderSubmissionTicket,
    SubmissionManifestEntry,
)
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


def _png(path: Path) -> str:
    # A tiny valid PNG keeps the media-type check real without a fixture file.
    from PIL import Image

    image = Image.new("RGB", (2, 2), color=(20, 40, 60))
    image.save(path, format="PNG")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ticket(tmp_path: Path, sha256: str) -> ProviderSubmissionTicket:
    entry = SubmissionManifestEntry(
        role="PRODUCT",
        order=1,
        adapter_field="images",
        object_key="creative/product.png",
        sha256=sha256,
        path=tmp_path / "source.png",
    )
    return ProviderSubmissionTicket(
        ticket_id="pst:input-lease-1",
        request_kind="image",
        execution_mode="image_edit",
        future_adapter_action="IMAGE_PROVIDER_ADAPTER_SUBMIT",
        owner_id="owner-1",
        creative_task_id="task-1",
        package_revision_id="package-1",
        shot_id="FIRST_FRAME",
        provider="gpt",
        model="gpt-image-1",
        idempotency_key="creative-provider:image:task-1:package-1:FIRST_FRAME",
        request_hash="b" * 64,
        evidence_hash="c" * 64,
        preflight_hash="d" * 64,
        expires_at=NOW + timedelta(minutes=30),
        estimated_cost_micros=100,
        currency="USD",
        quota_units=1,
        materialized_inputs=(entry,),
        manifest_path=tmp_path / "manifest.json",
        manifest_hash="e" * 64,
    )


def _approval(ticket: ProviderSubmissionTicket) -> ProviderApprovalManifest:
    return ProviderApprovalManifest(
        approval_id="approval-1",
        revision=1,
        status="ACTIVE",
        licenses=(
            ProviderReferenceLicense(
                license_id="license-1",
                owner_id=ticket.owner_id,
                creative_task_id=ticket.creative_task_id,
                role="PRODUCT",
                object_key="creative/product.png",
                sha256=ticket.materialized_inputs[0].sha256,
                provider=ticket.provider,
                evidence_id="evidence-1",
                confirmed_by=ticket.owner_id,
                expires_at=ticket.expires_at,
            ),
        ),
    )


def _fake_preflight(ticket: ProviderSubmissionTicket, approval: ProviderApprovalManifest):
    return SimpleNamespace(
        materialized_inputs=ticket.materialized_inputs,
        manifest_path=ticket.manifest_path,
        expires_at=ticket.expires_at,
        close=lambda: None,
    )


@pytest.fixture
async def lease_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'leases.db').as_posix()}",
        connect_args={"timeout": 5},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ProviderSubmissionTicketRecord.__table__.create)
        await connection.run_sync(ProviderInputLeaseRecord.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_ticket(session, ticket: ProviderSubmissionTicket) -> None:
    from libtv_agent.services.creative_provider_submission_persistence import (
        DurableSubmissionTicketStore,
    )

    await DurableSubmissionTicketStore().claim_submission(session, ticket, now=NOW)


async def _patched_store(monkeypatch, ticket: ProviderSubmissionTicket, approval):
    fake = _fake_preflight(ticket, approval)

    async def validate(*args, **kwargs):
        return fake, approval

    monkeypatch.setattr(
        DurableProviderInputLeaseStore,
        "_validate",
        validate,
    )
    monkeypatch.setattr(
        "libtv_agent.services.creative_provider_input_lease.admit_provider_submission",
        lambda *args, **kwargs: SimpleNamespace(ticket=ticket),
    )


async def test_create_copies_verified_input_and_replays_after_new_session(
    lease_session, tmp_path, monkeypatch
):
    source = tmp_path / "source.png"
    sha256 = _png(source)
    owner_id = uuid.uuid4()
    ticket = _ticket(tmp_path, sha256).model_copy(update={"owner_id": str(owner_id)})
    approval = _approval(ticket)
    await _patched_store(monkeypatch, ticket, approval)
    object_store = LocalObjectStore(tmp_path / "objects")
    store = DurableProviderInputLeaseStore()

    async with lease_session() as session:
        await _seed_ticket(session, ticket)
        created = await store.create(
            session,
            SimpleNamespace(),
            SimpleNamespace(owner_id=ticket.owner_id),
            ticket,
            owner_id=owner_id,
            object_store=object_store,
            settings=SimpleNamespace(),
            capability=SimpleNamespace(),
            approval_manifest_path=tmp_path / "approval.json",
            now=NOW,
        )
        assert created.status == "ACTIVE"
        assert created.lease.inputs[0].durable_object_key.startswith(
            "creative-provider-inputs/"
        )
        assert await object_store.exists(created.lease.inputs[0].durable_object_key)
        await session.commit()

    async with lease_session() as session:
        replay = await store.get(session, ticket.idempotency_key, owner_id=owner_id)
        assert replay is not None
        assert replay.lease == created.lease
        materialized = await store.materialize(
            session,
            SimpleNamespace(),
            SimpleNamespace(owner_id=ticket.owner_id),
            ticket,
            owner_id=owner_id,
            object_store=object_store,
            settings=SimpleNamespace(),
            capability=SimpleNamespace(),
            approval_manifest_path=tmp_path / "approval.json",
            now=NOW,
        )
        assert materialized.state.status == "MATERIALIZED"
        assert materialized.inputs[0].path.is_file()
        assert hashlib.sha256(materialized.inputs[0].path.read_bytes()).hexdigest() == sha256
        materialized.close()


async def test_same_key_different_source_contract_is_conflict(lease_session, tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    sha256 = _png(source)
    owner_id = uuid.uuid4()
    ticket = _ticket(tmp_path, sha256).model_copy(update={"owner_id": str(owner_id)})
    approval = _approval(ticket)
    await _patched_store(monkeypatch, ticket, approval)
    store = DurableProviderInputLeaseStore()
    async with lease_session() as session:
        await _seed_ticket(session, ticket)
        await store.create(
            session,
            SimpleNamespace(),
            SimpleNamespace(owner_id=ticket.owner_id),
            ticket,
            owner_id=owner_id,
            object_store=LocalObjectStore(tmp_path / "objects"),
            settings=SimpleNamespace(),
            capability=SimpleNamespace(),
            approval_manifest_path=tmp_path / "approval.json",
            now=NOW,
        )
        conflicting = ticket.model_copy(update={"evidence_hash": "f" * 64})
        with pytest.raises(ProviderInputLeaseRejected) as rejected:
            await store.create(
                session,
                SimpleNamespace(),
                SimpleNamespace(owner_id=ticket.owner_id),
                conflicting,
                owner_id=owner_id,
                object_store=LocalObjectStore(tmp_path / "objects"),
                settings=SimpleNamespace(),
                capability=SimpleNamespace(),
                approval_manifest_path=tmp_path / "approval.json",
                now=NOW,
            )
        assert rejected.value.code == "IDEMPOTENCY_KEY_CONFLICT"


async def test_owner_scope_and_durable_byte_recheck_revoke_lease(
    lease_session, tmp_path, monkeypatch
):
    source = tmp_path / "source.png"
    sha256 = _png(source)
    owner_id = uuid.uuid4()
    ticket = _ticket(tmp_path, sha256).model_copy(update={"owner_id": str(owner_id)})
    approval = _approval(ticket)
    await _patched_store(monkeypatch, ticket, approval)
    store = DurableProviderInputLeaseStore()
    object_store = LocalObjectStore(tmp_path / "objects")
    async with lease_session() as session:
        await _seed_ticket(session, ticket)
        await store.create(
            session,
            SimpleNamespace(),
            SimpleNamespace(owner_id=ticket.owner_id),
            ticket,
            owner_id=owner_id,
            object_store=object_store,
            settings=SimpleNamespace(),
            capability=SimpleNamespace(),
            approval_manifest_path=tmp_path / "approval.json",
            now=NOW,
        )
        with pytest.raises(ProviderInputLeaseRejected) as rejected:
            await store.get(session, ticket.idempotency_key, owner_id=uuid.uuid4())
        assert rejected.value.code == "OWNER_MISMATCH"

        durable_key = (
            "creative-provider-inputs/"
            + digest_ticket(ticket)
            + "/1-"
            + sha256
        )
        durable_path = tmp_path / "objects" / durable_key
        durable_path.write_bytes(b"changed")
        with pytest.raises(ProviderInputLeaseRejected) as rejected:
            await store.assert_current(
                session,
                SimpleNamespace(),
                SimpleNamespace(owner_id=ticket.owner_id),
                ticket,
                owner_id=owner_id,
                object_store=object_store,
                settings=SimpleNamespace(),
                capability=SimpleNamespace(),
                approval_manifest_path=tmp_path / "approval.json",
                now=NOW,
            )
        assert rejected.value.code == "DURABLE_INPUT_MISMATCH"
        row = await session.scalar(
            select(ProviderInputLeaseRecord).where(
                ProviderInputLeaseRecord.idempotency_key == ticket.idempotency_key
            )
        )
        assert row is not None
        assert row.status == "REVOKED"


async def test_expiry_and_stop_close_lease_before_materialization(
    lease_session, tmp_path, monkeypatch
):
    source = tmp_path / "source.png"
    sha256 = _png(source)
    owner_id = uuid.uuid4()
    ticket = _ticket(tmp_path, sha256).model_copy(update={"owner_id": str(owner_id)})
    approval = _approval(ticket)
    await _patched_store(monkeypatch, ticket, approval)
    store = DurableProviderInputLeaseStore()
    object_store = LocalObjectStore(tmp_path / "objects")

    async with lease_session() as session:
        await _seed_ticket(session, ticket)
        await store.create(
            session,
            SimpleNamespace(),
            SimpleNamespace(owner_id=ticket.owner_id),
            ticket,
            owner_id=owner_id,
            object_store=object_store,
            settings=SimpleNamespace(),
            capability=SimpleNamespace(),
            approval_manifest_path=tmp_path / "approval.json",
            now=NOW,
        )
        with pytest.raises(ProviderInputLeaseRejected) as rejected:
            await store.assert_current(
                session,
                SimpleNamespace(),
                SimpleNamespace(owner_id=ticket.owner_id),
                ticket,
                owner_id=owner_id,
                object_store=object_store,
                settings=SimpleNamespace(),
                capability=SimpleNamespace(),
                approval_manifest_path=tmp_path / "approval.json",
                now=NOW + timedelta(minutes=31),
            )
        assert rejected.value.code == "LEASE_EXPIRED"
        expired = await store.get(session, ticket.idempotency_key, owner_id=owner_id)
        assert expired is not None
        assert expired.status == "EXPIRED"

        revoked = await store.revoke(
            session,
            ticket.idempotency_key,
            owner_id=owner_id,
            reason="USER_STOPPED",
        )
        assert revoked.status == "EXPIRED"


def digest_ticket(ticket: ProviderSubmissionTicket) -> str:
    payload = ticket.model_dump(mode="json", exclude={"manifest_path", "manifest_hash"})
    for entry in payload["materialized_inputs"]:
        entry.pop("path")
    from libtv_agent.creative.workflow import digest

    return digest(payload)


def test_migration_contains_durable_input_lease_contract(tmp_path):
    database = tmp_path / "migration.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database.as_posix()}"
    os.environ["APP_ENV"] = "test"
    from libtv_agent.config import get_settings

    get_settings.cache_clear()
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    command.upgrade(config, "e5f6a7b8c901")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        inspector = inspect(engine)
        columns = {
            column["name"] for column in inspector.get_columns("provider_input_lease")
        }
        assert {
            "owner_id",
            "creative_task_id",
            "package_revision_id",
            "shot_id",
            "request_hash",
            "evidence_hash",
            "manifest_hash",
            "manifest_json",
            "status",
            "expires_at",
        } <= columns
        unique_names = {
            item["name"]
            for item in inspector.get_unique_constraints("provider_input_lease")
        }
        assert {
            "uq_provider_input_lease_lease_id",
            "uq_provider_input_lease_ticket_id",
            "uq_provider_input_lease_idempotency_key",
        } <= unique_names
    finally:
        engine.dispose()
