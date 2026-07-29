import asyncio
import os
import uuid
from pathlib import Path
from urllib.request import urlopen

import pytest
from libtv_agent.adapters.object_store import MinioObjectStore, PrefixedObjectStore
from libtv_agent.config import Settings
from libtv_agent.domain.enums import ParentTaskPhase, VariantKind
from libtv_agent.domain.models import (
    GenerationAttempt,
    GenerationVariant,
    ParentTask,
    PointsReservation,
    User,
)
from libtv_agent.services.idempotency import load_idempotent_response, store_idempotent_response
from libtv_agent.services.points import PointsLimitExceededError, reserve_points
from libtv_agent.services.state_machine import VersionConflictError, cas_task_phase
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.skipif(
    os.environ.get("PHASE2_ONLINE_TESTS") != "1",
    reason="set PHASE2_ONLINE_TESTS=1 after starting isolated PostgreSQL and MinIO",
)


@pytest.mark.asyncio
async def test_postgresql_cas_points_and_idempotency_contracts() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("postgresql+asyncpg://")
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    async with factory() as session:
        session.add(User(id=user_id, username=f"online-{user_id}", password_hash="disabled"))
        await session.flush()
        session.add(
            ParentTask(
                id=task_id,
                user_id=user_id,
                client_task_id=f"online-{task_id}",
                title="online CAS",
                asset_count=1,
                phase=ParentTaskPhase.AWAITING_CONFIRMATION,
                state_version=1,
            )
        )
        await session.commit()

    async def transition() -> str:
        async with factory() as session:
            try:
                await cas_task_phase(
                    session,
                    task_id,
                    ParentTaskPhase.AWAITING_CONFIRMATION.value,
                    1,
                    ParentTaskPhase.PREPARING.value,
                )
                await session.commit()
                return "updated"
            except VersionConflictError:
                await session.rollback()
                return "conflict"

    assert sorted(await asyncio.gather(transition(), transition())) == ["conflict", "updated"]

    attempt_ids = [uuid.uuid4(), uuid.uuid4()]
    async with factory() as session:
        for attempt_id, kind in zip(
            attempt_ids, (VariantKind.STABLE, VariantKind.DYNAMIC), strict=True
        ):
            variant = GenerationVariant(
                parent_task_id=task_id,
                variant_type=kind,
                generation_config_json={},
            )
            session.add(variant)
            await session.flush()
            session.add(GenerationAttempt(id=attempt_id, variant_id=variant.id))
        await session.commit()

    async def reserve(attempt_id: uuid.UUID) -> str:
        async with factory() as session:
            try:
                await reserve_points(
                    session,
                    user_id=user_id,
                    attempt_id=attempt_id,
                    estimated_points=120,
                    daily_limit=200,
                )
                await session.commit()
                return "reserved"
            except PointsLimitExceededError:
                await session.rollback()
                return "limited"

    assert sorted(await asyncio.gather(*(reserve(item) for item in attempt_ids))) == [
        "limited",
        "reserved",
    ]
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PointsReservation)
                .where(PointsReservation.user_id == user_id)
            )
            == 1
        )
        assert (
            await load_idempotent_response(
                session,
                tenant_id=str(user_id),
                operation_type="ONLINE_TEST",
                key="same-key",
                payload={"value": 1},
            )
            is None
        )
        await store_idempotent_response(
            session,
            tenant_id=str(user_id),
            operation_type="ONLINE_TEST",
            key="same-key",
            payload={"value": 1},
            response_status=200,
            response_body={"ok": True},
        )
        await session.commit()
    async with factory() as session:
        replay = await load_idempotent_response(
            session,
            tenant_id=str(user_id),
            operation_type="ONLINE_TEST",
            key="same-key",
            payload={"value": 1},
        )
        assert replay == (200, {"ok": True})
    await engine.dispose()


@pytest.mark.asyncio
async def test_minio_upload_download_presign_and_lifecycle(tmp_path: Path) -> None:
    settings = Settings(_env_file=None)
    raw_store = MinioObjectStore(settings)
    store = PrefixedObjectStore(raw_store, settings.object_store_prefix)
    source = tmp_path / "online-object.bin"
    source.write_bytes(b"phase-two-online-object")
    key = await store.put_file(
        source, f"verification/{uuid.uuid4()}.bin", "application/octet-stream"
    )
    try:
        assert key.startswith(f"{settings.object_store_prefix}/")
        assert await store.exists(key)
        downloaded = await store.localize(key, tmp_path / "downloaded.bin")
        assert downloaded.read_bytes() == source.read_bytes()
        signed = await store.presign_get(key, expires_seconds=300)
        assert signed is not None and "X-Amz-Signature=" in signed
        signed_body = await asyncio.to_thread(
            lambda: urlopen(signed, timeout=15).read()  # noqa: S310 - local MinIO URL
        )
        assert signed_body == source.read_bytes()
        lifecycle = await asyncio.to_thread(
            raw_store.client.get_bucket_lifecycle, settings.minio_bucket
        )
        assert any(
            rule.status == "Enabled" and rule.expiration is not None and rule.expiration.days == 7
            for rule in lifecycle.rules
        )
    finally:
        await store.delete(key)
