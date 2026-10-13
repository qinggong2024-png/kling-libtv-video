from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from libtv_agent.creative.provider_submission_persistence import (
    ProviderSubmissionTicketRecord,
)
from libtv_agent.services.creative_provider_submission import (
    ProviderSubmissionAdmissionRejected,
    ProviderSubmissionTicket,
    SubmissionManifestEntry,
    provider_submission_result,
)
from libtv_agent.services.creative_provider_submission_persistence import (
    DurableSubmissionTicketStore,
)
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "d2f3a4b5c607"
REVISION = "e4f5a6b7c809"


def _ticket(tmp_path: Path, *, kind: str = "image", key: str | None = None):
    now = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
    is_video = kind == "video"
    entry = SubmissionManifestEntry(
        role="PRODUCT",
        order=1,
        adapter_field="image" if not is_video else "product_image",
        object_key="creative/product.png",
        sha256="a" * 64,
        path=tmp_path / "product.png",
    )
    return (
        ProviderSubmissionTicket(
            ticket_id=f"pst:{key or uuid.uuid4()}",
            request_kind=kind,
            execution_mode="director_fixed" if is_video else "image_edit",
            future_adapter_action=(
                "VIDEO_PROVIDER_ADAPTER_SUBMIT"
                if is_video
                else "IMAGE_PROVIDER_ADAPTER_SUBMIT"
            ),
            owner_id="owner-1",
            creative_task_id="creative-task-1",
            package_revision_id="package-1",
            shot_id="SHOT_01" if is_video else "FIRST_FRAME",
            provider="provider-test",
            model="model-test",
            idempotency_key=key or f"idem:{uuid.uuid4()}",
            request_hash="b" * 64,
            evidence_hash="c" * 64,
            preflight_hash="d" * 64,
            expires_at=now + timedelta(minutes=30),
            estimated_cost_micros=100,
            currency="USD",
            quota_units=2 if is_video else 1,
            materialized_inputs=(entry,),
            manifest_path=tmp_path / "manifest.json",
            manifest_hash="e" * 64,
        ),
        now,
    )


@pytest.fixture
async def ticket_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'tickets.db').as_posix()}",
        connect_args={"timeout": 5},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ProviderSubmissionTicketRecord.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _claim(factory, ticket, now):
    async with factory() as session:
        return await DurableSubmissionTicketStore().claim_submission(session, ticket, now=now)


@pytest.mark.parametrize("kind", ["image", "video"])
async def test_durable_claim_persists_contract_and_replays_after_new_session(
    ticket_session,
    tmp_path,
    kind,
):
    ticket, now = _ticket(tmp_path, kind=kind, key=f"persist:{kind}")
    store = DurableSubmissionTicketStore()
    async with ticket_session() as session:
        first = await store.claim_submission(session, ticket, now=now)
        assert first.created is True
        await session.commit()

    async with ticket_session() as session:
        replay = await store.claim_submission(session, ticket, now=now)
        assert replay.created is False
        assert replay.ticket == ticket
        row = await session.scalar(
            select(ProviderSubmissionTicketRecord).where(
                ProviderSubmissionTicketRecord.idempotency_key == ticket.idempotency_key
            )
        )
        assert row is not None
        assert row.request_hash == ticket.request_hash
        assert row.evidence_hash == ticket.evidence_hash
        assert row.preflight_hash == ticket.preflight_hash
        assert row.owner_id == ticket.owner_id
        assert row.creative_task_id == ticket.creative_task_id
        assert row.package_revision_id == ticket.package_revision_id
        assert row.shot_id == ticket.shot_id
        assert row.provider == ticket.provider
        assert row.model == ticket.model
        assert row.estimated_cost_micros == ticket.estimated_cost_micros
        assert row.quota_units == ticket.quota_units
        assert row.manifest_hash == ticket.manifest_hash
        assert row.status == "READY_TO_SUBMIT"
        assert row.result_summary is None


async def test_same_key_with_different_hash_is_a_durable_conflict(ticket_session, tmp_path):
    ticket, now = _ticket(tmp_path, key="conflict:1")
    conflicting = ticket.model_copy(
        update={
            "ticket_id": "pst:conflict:changed",
            "evidence_hash": "f" * 64,
        }
    )
    store = DurableSubmissionTicketStore()
    async with ticket_session() as session:
        await store.claim_submission(session, ticket, now=now)
        with pytest.raises(ProviderSubmissionAdmissionRejected) as rejected:
            await store.claim_submission(session, conflicting, now=now)
        assert rejected.value.code == "IDEMPOTENCY_KEY_CONFLICT"


async def test_expired_ticket_is_closed_and_cannot_reclaim(ticket_session, tmp_path):
    ticket, now = _ticket(tmp_path, key="expired:1")
    store = DurableSubmissionTicketStore()
    async with ticket_session() as session:
        await store.claim_submission(session, ticket, now=now)
        expired = await store.claim_submission(
            session,
            ticket,
            now=now + timedelta(minutes=31),
        )
        assert expired.created is False
        assert expired.state.state == "INVALIDATED"
        assert expired.state.invalidation_reason == "TICKET_EXPIRED"

    async with ticket_session() as session:
        saved = await store.get(session, ticket.idempotency_key)
        assert saved is not None
        assert saved.state == "INVALIDATED"


@pytest.mark.parametrize("status", ["SUBMITTED", "UNKNOWN", "FAILED"])
async def test_terminal_result_cannot_be_reclaimed_with_same_key(
    ticket_session,
    tmp_path,
    status,
):
    ticket, now = _ticket(tmp_path, kind="video", key=f"terminal:{status}")
    store = DurableSubmissionTicketStore()
    async with ticket_session() as session:
        claim = await store.claim_submission(session, ticket, now=now)
        result = provider_submission_result(
            ticket,
            status=status,
            provider_task_id="provider-task-1" if status == "SUBMITTED" else None,
            provider_status=status.lower(),
            error_code="PROVIDER_FAILED" if status == "FAILED" else None,
        )
        saved = await store.record_provider_result(session, ticket.idempotency_key, result)
        assert saved.state == status
        assert saved.result == result
        assert saved.result.retry_policy in {
            "NONE",
            "RECONCILE_ONLY",
            "EXPLICIT_NEW_IDEMPOTENCY_KEY",
        }
        replay = await store.claim_submission(session, claim.ticket, now=now)
        assert replay.created is False
        assert replay.state == saved
        row = await session.scalar(
            select(ProviderSubmissionTicketRecord).where(
                ProviderSubmissionTicketRecord.idempotency_key == ticket.idempotency_key
            )
        )
        assert row is not None
        assert row.result_status == status
        assert row.result_summary == json.dumps(
            result.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )


async def test_stopped_ticket_cannot_be_reclaimed(ticket_session, tmp_path):
    ticket, now = _ticket(tmp_path, key="stopped:1")
    store = DurableSubmissionTicketStore()
    async with ticket_session() as session:
        await store.claim_submission(session, ticket, now=now)
        stopped = await store.invalidate(session, ticket.idempotency_key, "USER_STOPPED")
        assert stopped.state == "INVALIDATED"
        replay = await store.claim_submission(session, ticket, now=now)
        assert replay.created is False
        assert replay.state == stopped


async def test_sqlite_unique_insert_makes_one_claim_winner(ticket_session, tmp_path):
    ticket, now = _ticket(tmp_path, key="race:1")
    first, second = await asyncio.gather(
        _claim(ticket_session, ticket, now),
        _claim(ticket_session, ticket, now),
    )
    assert sorted([first.created, second.created]) == [False, True]


def _migration_config(database: Path) -> Config:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database.as_posix()}"
    os.environ["APP_ENV"] = "test"
    from libtv_agent.config import get_settings

    get_settings.cache_clear()
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    return config


def test_migration_adds_only_durable_ticket_table_and_unique_claim_key(tmp_path):
    database = tmp_path / "migration.db"
    config = _migration_config(database)
    command.upgrade(config, REVISION)
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        inspector = inspect(engine)
        assert "provider_submission_ticket" in inspector.get_table_names()
        columns = {column["name"] for column in inspector.get_columns("provider_submission_ticket")}
        assert {
            "request_hash",
            "evidence_hash",
            "preflight_hash",
            "owner_id",
            "creative_task_id",
            "package_revision_id",
            "shot_id",
            "provider",
            "model",
            "idempotency_key",
            "estimated_cost_micros",
            "quota_units",
            "manifest_hash",
            "status",
            "result_summary",
        } <= columns
        unique_names = {
            item["name"] for item in inspector.get_unique_constraints("provider_submission_ticket")
        }
        assert "uq_provider_submission_ticket_idempotency_key" in unique_names
        assert "uq_provider_submission_ticket_ticket_id" in unique_names
        assert inspector.get_foreign_keys("provider_submission_ticket") == []
    finally:
        engine.dispose()

