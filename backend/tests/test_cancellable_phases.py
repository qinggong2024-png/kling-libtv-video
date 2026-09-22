"""The cancel button and the cancel endpoint must agree on which phases are cancellable.

They did not. services.tasks._build_task_read also advertised PREPARING,
WAITING_FOR_SEAL and QUEUED, while api.tasks.cancel_task honoured only DRAFT,
ANALYZING and AWAITING_CONFIRMATION. The UI therefore rendered an enabled cancel button
that always answered 409 -- the request was never going to succeed.

Both sides now derive from domain.enums.CANCELLABLE_PHASES, and the endpoint is exercised
for every phase so a future widening of the read model alone cannot pass unnoticed.
"""

import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.api import tasks as api_tasks
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import CANCELLABLE_PHASES, ParentTaskPhase
from libtv_agent.domain.models import Base, ParentTask, User
from libtv_agent.services import tasks as service_tasks
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ALL_PHASES = list(ParentTaskPhase)
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url=database_url,
        object_store_mode="local",
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        _env_file=None,
    )


async def _seed(database_url: str) -> dict[str, uuid.UUID]:
    """Create one task per phase, owned by the dev user, and return their ids."""
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids: dict[str, uuid.UUID] = {}
    async with factory() as session:
        session.add(
            User(
                id=USER_ID,
                username="cancel-contract-user",
                password_hash="disabled",
                is_active=True,
            )
        )
        for phase in ALL_PHASES:
            task = ParentTask(
                id=uuid.uuid4(),
                user_id=USER_ID,
                client_task_id=f"cancel-{phase.value}",
                title=f"cancel {phase.value}",
                asset_count=1,
                phase=phase,
            )
            session.add(task)
            ids[phase.value] = task.id
        await session.commit()
    await engine.dispose()
    return ids


# ---------------------------------------------------------------- read model


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ALL_PHASES, ids=[p.value for p in ALL_PHASES])
async def test_read_model_offers_cancel_exactly_for_cancellable_phases(
    phase: ParentTaskPhase,
) -> None:
    # Re-read through the same accessor the endpoint uses: the read model walks
    # task.variants, so the row must be loaded with selectinload rather than handed in
    # as a transient object (which would also be missing server-side column defaults).
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        task = ParentTask(
            id=uuid.uuid4(),
            user_id=USER_ID,
            client_task_id="read-model",
            title="read model",
            asset_count=1,
            phase=phase,
        )
        session.add(task)
        await session.commit()
        loaded = await service_tasks.get_task(session, USER_ID, task.id)
        read = service_tasks._build_task_read(loaded, 5000, None, {}, {}, {}, None)
    await engine.dispose()

    assert read.action_capabilities.can_cancel is (phase in CANCELLABLE_PHASES), (
        f"can_cancel={read.action_capabilities.can_cancel} for {phase.value} would render "
        "a button that the endpoint refuses"
    )


def test_cancellable_phases_stop_before_work_is_dispatched() -> None:
    # Cancelling after confirmation would have to release the points already reserved
    # for each attempt. That is a behaviour change, not a whitelist edit, so those
    # phases stay out until that cleanup exists.
    assert CANCELLABLE_PHASES == {
        ParentTaskPhase.DRAFT,
        ParentTaskPhase.ANALYZING,
        ParentTaskPhase.AWAITING_CONFIRMATION,
    }
    for excluded in (
        ParentTaskPhase.PREPARING,
        ParentTaskPhase.WAITING_FOR_SEAL,
        ParentTaskPhase.QUEUED,
        ParentTaskPhase.GENERATING,
    ):
        assert excluded not in CANCELLABLE_PHASES


def test_cancelled_is_not_itself_cancellable() -> None:
    assert ParentTaskPhase.CANCELLED not in CANCELLABLE_PHASES


def test_read_model_and_endpoint_share_one_object() -> None:
    # Same object, not two equal copies: a future edit cannot fix one call site and
    # silently leave the other behind.
    assert service_tasks.CANCELLABLE_PHASES is CANCELLABLE_PHASES
    assert api_tasks.CANCELLABLE_PHASES is CANCELLABLE_PHASES


# ---------------------------------------------------------------- endpoint


@pytest.mark.asyncio
async def test_cancel_endpoint_honours_exactly_the_cancellable_phases(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'cancel.db').as_posix()}"
    ids = await _seed(database_url)
    settings = _settings(database_url, tmp_path)
    app = create_app(settings)
    headers = {"X-User-Id": str(USER_ID)}

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            refused: list[str] = []
            accepted: list[str] = []
            for phase in ALL_PHASES:
                response = await client.post(
                    f"/api/v1/tasks/{ids[phase.value]}/cancel",
                    headers={
                        **headers,
                        "Idempotency-Key": f"cancel-{phase.value}",
                    },
                )
                if phase in CANCELLABLE_PHASES:
                    assert response.status_code == 204, (
                        f"{phase.value} is advertised as cancellable but the endpoint "
                        f"answered {response.status_code}"
                    )
                    accepted.append(phase.value)
                else:
                    assert response.status_code == 409, (
                        f"{phase.value} is not cancellable but the endpoint answered "
                        f"{response.status_code}"
                    )
                    refused.append(phase.value)

    assert set(accepted) == {p.value for p in CANCELLABLE_PHASES}
    assert set(refused) == {p.value for p in ALL_PHASES} - set(accepted)
