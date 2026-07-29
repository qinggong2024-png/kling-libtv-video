import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import (
    AttemptStatus,
    ChargeStatus,
    CommandStatus,
    ConsistencyLevel,
    UserRole,
    VariantKind,
)
from libtv_agent.domain.models import (
    Base,
    GenerationAttempt,
    GenerationCommand,
    GenerationVariant,
    ParentTask,
    User,
)
from libtv_agent.runner.supervisor import RunnerSupervisor
from libtv_agent.services.capacity import acquire_capacity, release_capacity
from libtv_agent.services.credentials import load_admin_credentials
from libtv_agent.services.runtime_control import (
    RuntimeControlBlockedError,
    default_runtime_config,
    ensure_paid_submission_allowed,
    generation_claims_allowed,
    get_runtime_config,
    set_libtv_auth_required,
    validate_runtime_config,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OPERATOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000088")


def test_runtime_config_allows_pass_only_auto_confirmation() -> None:
    settings = Settings(_env_file=None)
    assert default_runtime_config(settings)["promptConfirmationRequired"] is True
    assert default_runtime_config(settings)["libtvAuthRequired"] is False
    config = {
        "globalPaused": False,
        "paidSubmissionsPaused": True,
        "generationConcurrency": {"sameProject": 1, "perUser": 1, "global": 1},
        "preparedQueue": {"lowWatermark": 12, "highWatermark": 24},
        "promptConfirmationRequired": True,
        "autoConfirmLevels": ["PASS", "WARNING"],
    }

    with pytest.raises(ValueError, match="only PASS"):
        validate_runtime_config(config)
    config["autoConfirmLevels"] = ["PASS"]
    config["promptConfirmationRequired"] = False
    assert validate_runtime_config(config)["promptConfirmationRequired"] is False
    with pytest.raises(ValueError, match="only PASS"):
        Settings(auto_confirm_levels="PASS,WARNING", _env_file=None)
    assert settings.paid_submissions_paused is True
    assert settings.generation_global == 1
    assert settings.libtv_execution_mode == "dry-run"
    assert settings.paid_generation_enabled is False
    with pytest.raises(ValueError, match="test environments cannot enable"):
        Settings(
            app_env="test",
            libtv_execution_mode="live",
            paid_generation_enabled=True,
            _env_file=None,
        )


@pytest.mark.asyncio
async def test_libtv_auth_required_pauses_paid_work_without_auto_unpausing(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'auth.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        app_env="development",
        libtv_adapter_mode="real",
        libtv_execution_mode="live",
        paid_generation_enabled=True,
        paid_generation_confirmation="I_ACCEPT_LIBTV_POINT_CHARGES",
        paid_submissions_paused=False,
        _env_file=None,
    )

    async with factory() as session:
        await set_libtv_auth_required(
            session,
            settings,
            required=True,
            reason="test expired login",
        )
        await session.commit()
        current = await get_runtime_config(session, settings)
        assert current is not None
        assert current.config_json["libtvAuthRequired"] is True
        assert current.config_json["paidSubmissionsPaused"] is True
        assert not await generation_claims_allowed(session, settings)

        await set_libtv_auth_required(
            session,
            settings,
            required=False,
            reason="test login recovered",
        )
        await session.commit()
        recovered = await get_runtime_config(session, settings)
        assert recovered is not None
        assert recovered.config_json["libtvAuthRequired"] is False
        assert recovered.config_json["paidSubmissionsPaused"] is True
        assert await generation_claims_allowed(session, settings)

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_paid_submission_is_closed_by_default(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'gate.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        libtv_adapter_mode="real",
        object_store_mode="local",
        _env_file=None,
    )
    async with factory() as session:
        with pytest.raises(RuntimeControlBlockedError) as captured:
            await ensure_paid_submission_allowed(session, settings)
        assert captured.value.code == "PAID_GENERATION_BLOCKED"
    await engine.dispose()


def _command_graph(
    index: int,
) -> tuple[ParentTask, GenerationVariant, GenerationAttempt, GenerationCommand]:
    task = ParentTask(
        user_id=USER_ID,
        client_task_id=f"capacity-{index}",
        title=f"Capacity {index}",
        asset_count=1,
        consistency_level=ConsistencyLevel.PASS,
    )
    variant = GenerationVariant(
        parent_task=task,
        variant_type=VariantKind.STABLE,
        generation_config_json={},
    )
    attempt = GenerationAttempt(
        variant=variant,
        project_uuid="project-one",
        video_node_key=f"node-{index}",
        intent_hash=f"{index:064d}",
        status=AttemptStatus.DISPATCH_PENDING,
    )
    command = GenerationCommand(attempt=attempt, status=CommandStatus.READY)
    return task, variant, attempt, command


@pytest.mark.asyncio
async def test_capacity_slots_enforce_and_release_three_scopes(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'slots.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(object_store_mode="local", _env_file=None)
    async with factory() as session:
        session.add(User(id=USER_ID, username="capacity-user", password_hash="disabled"))
        first = _command_graph(1)[-1]
        second = _command_graph(2)[-1]
        session.add_all([first, second])
        await session.commit()
        first_lease = await acquire_capacity(session, settings, first)
        assert first_lease is not None
        assert len(first_lease.slot_ids) == 3
        assert await acquire_capacity(session, settings, second) is None
        assert await release_capacity(session, first.id) == 3
        assert await acquire_capacity(session, settings, second) is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_unknown_charge_keeps_capacity_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    release = AsyncMock(return_value=3)
    monkeypatch.setattr("libtv_agent.runner.supervisor.release_capacity", release)
    supervisor = RunnerSupervisor(None, None, Settings(_env_file=None))  # type: ignore[arg-type]
    command = GenerationCommand(id=uuid.uuid4(), attempt_id=uuid.uuid4())
    attempt = GenerationAttempt(
        id=command.attempt_id,
        variant_id=uuid.uuid4(),
        charge_status=ChargeStatus.UNKNOWN,
    )

    assert not await supervisor._release_capacity_if_charge_classified(None, command, attempt)  # type: ignore[arg-type]
    release.assert_not_awaited()

    attempt.charge_status = ChargeStatus.CHARGED
    assert await supervisor._release_capacity_if_charge_classified(None, command, attempt)  # type: ignore[arg-type]
    release.assert_awaited_once_with(None, command.id)


@pytest.mark.asyncio
async def test_admin_control_plane_pause_rollback_and_sse(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'admin.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    settings = Settings(
        app_env="test",
        database_url=database_url,
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        object_store_mode="local",
        _env_file=None,
    )
    app = create_app(settings)
    headers = {"X-User-Id": str(ADMIN_ID)}
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            initial = await client.get("/api/v1/admin/runtime-config", headers=headers)
            assert initial.status_code == 200
            assert initial.json()["version"] == 1
            paused = await client.post(
                "/api/v1/admin/pause",
                headers=headers,
                json={
                    "expectedVersion": 1,
                    "scope": "GLOBAL",
                    "paused": True,
                    "reason": "controlled stop drill",
                },
            )
            assert paused.status_code == 200
            assert paused.json()["config"]["globalPaused"] is True
            rolled_back = await client.post(
                "/api/v1/admin/runtime-config/rollback",
                headers=headers,
                json={
                    "expectedVersion": 2,
                    "targetVersion": 1,
                    "reason": "rollback drill complete",
                },
            )
            assert rolled_back.status_code == 200
            assert rolled_back.json()["config"]["globalPaused"] is False
            automatic = await client.post(
                "/api/v1/admin/prompt-confirmation",
                headers=headers,
                json={"expectedVersion": 3, "automatic": True},
            )
            assert automatic.status_code == 200
            assert automatic.json()["version"] == 4
            assert automatic.json()["config"]["promptConfirmationRequired"] is False
            manual = await client.post(
                "/api/v1/admin/prompt-confirmation",
                headers=headers,
                json={"expectedVersion": 4, "automatic": False},
            )
            assert manual.status_code == 200
            assert manual.json()["version"] == 5
            assert manual.json()["config"]["promptConfirmationRequired"] is True
            operations = await client.get("/api/v1/admin/operations", headers=headers)
            assert operations.status_code == 200
            assert "generationSlotUtilization" in operations.json()["metrics"]
            event = await client.get("/api/v1/events?once=true", headers=headers)
            assert event.status_code == 200
            assert "event: operations.snapshot" in event.text


@pytest.mark.asyncio
async def test_only_admin_can_store_provider_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIBTV_ACCESS_KEY", raising=False)
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'credentials.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            User(
                id=OPERATOR_ID,
                username="credential-operator",
                password_hash="disabled",
                role=UserRole.OPERATOR,
            )
        )
        await session.commit()
    await engine.dispose()
    credential_file = tmp_path / "runtime" / "admin-credentials.json"
    settings = Settings(
        app_env="test",
        database_url=database_url,
        admin_credentials_file=credential_file,
        libtv_access_key=None,
        object_store_mode="local",
        openai_api_key=None,
        _env_file=None,
    )
    app = create_app(settings)
    admin_headers = {"X-User-Id": str(ADMIN_ID)}
    user_headers = {"X-User-Id": str(USER_ID)}
    operator_headers = {"X-User-Id": str(OPERATOR_ID)}
    libtv_key = "libtv-test-secret-key"
    model_key = "model-test-secret-key"
    model_base_url = "https://gateway.example.test/v1"

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            initial_requests = await asyncio.gather(
                *(client.get("/api/v1/admin/credentials", headers=admin_headers) for _ in range(3))
            )
            assert all(response.status_code == 200 for response in initial_requests)
            assert all(
                response.json()
                == {
                    "libtvConfigured": False,
                    "modelConfigured": False,
                    "modelBaseUrl": None,
                    "updatedAt": None,
                }
                for response in initial_requests
            )

            forbidden = await client.get("/api/v1/admin/credentials", headers=user_headers)
            assert forbidden.status_code == 403
            operator_forbidden = await client.get(
                "/api/v1/admin/credentials", headers=operator_headers
            )
            assert operator_forbidden.status_code == 403

            updated = await client.patch(
                "/api/v1/admin/credentials",
                headers=admin_headers,
                json={
                    "libtvAccessKey": libtv_key,
                    "modelApiKey": model_key,
                    "modelBaseUrl": model_base_url,
                },
            )
            assert updated.status_code == 200
            assert updated.json()["libtvConfigured"] is True
            assert updated.json()["modelConfigured"] is True
            assert updated.json()["modelBaseUrl"] == model_base_url
            assert libtv_key not in updated.text
            assert model_key not in updated.text

            assert settings.libtv_access_key == libtv_key
            assert settings.openai_api_key == model_key
            assert settings.openai_base_url == model_base_url
            assert credential_file.is_file()
            stored_text = credential_file.read_text(encoding="utf-8")
            assert libtv_key not in stored_text
            assert model_key not in stored_text
            assert json.loads(stored_text)["format"] == "dpapi-machine-v1"
            reloaded = settings.model_copy(
                update={"libtv_access_key": None, "openai_api_key": None, "openai_base_url": None}
            )
            load_admin_credentials(reloaded)
            assert reloaded.libtv_access_key == libtv_key
            assert reloaded.openai_api_key == model_key
            assert reloaded.openai_base_url == model_base_url

            invalid_url = await client.patch(
                "/api/v1/admin/credentials",
                headers=admin_headers,
                json={"modelBaseUrl": "http://gateway.example.test/v1"},
            )
            assert invalid_url.status_code == 422
            assert settings.openai_base_url == model_base_url

            cleared_url = await client.patch(
                "/api/v1/admin/credentials",
                headers=admin_headers,
                json={"clearModelBaseUrl": True},
            )
            assert cleared_url.status_code == 200
            assert cleared_url.json()["modelBaseUrl"] is None
            assert settings.openai_base_url is None

            system_status = await client.get("/api/v1/system/status")
            assert system_status.status_code == 200
            assert system_status.json()["libtvConfigured"] is True
            assert system_status.json()["openaiConfigured"] is True
