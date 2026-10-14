import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock

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
    AuditEvent,
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
from libtv_agent.services.generation_safety import PAID_GENERATION_CONFIRMATION
from libtv_agent.services.runtime_control import (
    RuntimeControlBlockedError,
    assess_unknown_submission_risk,
    default_runtime_config,
    ensure_paid_submission_allowed,
    ensure_provider_submission_allowed,
    generation_claims_allowed,
    get_runtime_config,
    provider_claims_allowed,
    reserve_internal_pilot_budget,
    set_libtv_auth_required,
    update_runtime_config,
    validate_runtime_config,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OPERATOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000088")
OTHER_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
THIRD_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")

PROVIDER_CONFIGS = [
    {"kling_provider_backend": "api", "kling_api_enabled": True},
    {
        "kling_provider_backend": "wavespeed",
        "wavespeed_enabled": True,
        "wavespeed_api_key": "isolated-unused-wavespeed-key",
    },
    {
        "kling_provider_backend": "bach",
        "bach_enabled": True,
        "bach_access_key": "isolated-unused-bach-key",
        "bach_secret_key": "isolated-unused-bach-secret",
    },
]


def authorized_provider_settings(**options) -> Settings:
    return Settings(
        **{
            "app_env": "development",
            "shared_authentication_enabled": True,
            "session_secret": "isolated-runtime-control-session-secret",
            "libtv_execution_mode": "live",
            "paid_generation_enabled": True,
            "paid_generation_confirmation": PAID_GENERATION_CONFIRMATION,
            **options,
        },
        _env_file=None,
    )


@pytest.fixture
async def pilot_database(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'pilot-safety.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                User(id=identity, username=str(identity), password_hash="offline-disabled")
                for identity in (ADMIN_ID, USER_ID, OTHER_USER_ID, THIRD_USER_ID)
            ]
        )
        await get_runtime_config(session, Settings(app_env="test", _env_file=None))
        await session.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


async def configure_pilot(factory, settings: Settings, **options) -> None:
    async with factory() as session:
        current = await get_runtime_config(session, settings)
        config = dict(current.config_json)
        config.update(
            {
                "internalPilotEnabled": True,
                "pilotUserIds": [str(USER_ID)],
                "pilotBudgetLimit": 2,
                "pilotSubmittedCount": 0,
                **options,
            }
        )
        await update_runtime_config(
            session,
            settings,
            config=config,
            actor_id=ADMIN_ID,
            reason="isolated pilot test setup",
            expected_version=current.version,
        )
        await session.commit()


@pytest.mark.parametrize("provider_options", PROVIDER_CONFIGS, ids=["kling", "wavespeed", "bach"])
@pytest.mark.parametrize("libtv_mode", ["fake", "replay"])
@pytest.mark.parametrize(
    "missing_authorization",
    [
        {"libtv_execution_mode": "dry-run"},
        {"paid_generation_enabled": False},
        {"paid_generation_confirmation": ""},
        {"paid_generation_confirmation": "incorrect-confirmation"},
    ],
    ids=["not-live", "disabled", "no-confirmation", "wrong-confirmation"],
)
async def test_production_synthetic_libtv_cannot_authorize_real_provider_submission_or_claim(
    pilot_database, provider_options, libtv_mode, missing_authorization
) -> None:
    settings = authorized_provider_settings(
        app_env="production",
        libtv_adapter_mode=libtv_mode,
        paid_submissions_paused=False,
        **provider_options,
        **missing_authorization,
    )
    async with pilot_database() as session:
        with pytest.raises(RuntimeControlBlockedError) as captured:
            await ensure_provider_submission_allowed(
                session, settings, settings.active_kling_provider_name, user_id=USER_ID
            )
        assert captured.value.code == "PAID_GENERATION_BLOCKED"
        assert not await provider_claims_allowed(
            session, settings, settings.active_kling_provider_name, user_id=USER_ID
        )


@pytest.mark.parametrize("provider_options", PROVIDER_CONFIGS, ids=["kling", "wavespeed", "bach"])
@pytest.mark.parametrize("libtv_mode", ["fake", "replay"])
async def test_real_provider_stays_blocked_in_test_with_synthetic_libtv(
    pilot_database, provider_options, libtv_mode
) -> None:
    settings = Settings(
        app_env="test",
        libtv_adapter_mode=libtv_mode,
        paid_submissions_paused=False,
        **provider_options,
        _env_file=None,
    )
    async with pilot_database() as session:
        with pytest.raises(RuntimeControlBlockedError) as captured:
            await ensure_provider_submission_allowed(
                session, settings, settings.active_kling_provider_name, user_id=USER_ID
            )
        assert captured.value.code == "PAID_GENERATION_BLOCKED"
        assert not await provider_claims_allowed(
            session, settings, settings.active_kling_provider_name, user_id=USER_ID
        )


@pytest.mark.parametrize("provider_options", PROVIDER_CONFIGS, ids=["kling", "wavespeed", "bach"])
async def test_authorized_real_provider_allows_submission_and_claim_without_real_libtv(
    pilot_database, provider_options
) -> None:
    settings = authorized_provider_settings(paid_submissions_paused=False, **provider_options)
    await configure_pilot(pilot_database, settings, paidSubmissionsPaused=False)
    async with pilot_database() as session:
        await ensure_provider_submission_allowed(
            session, settings, settings.active_kling_provider_name, user_id=USER_ID
        )
        assert await provider_claims_allowed(
            session, settings, settings.active_kling_provider_name, user_id=USER_ID
        )


@pytest.mark.parametrize("provider_options", PROVIDER_CONFIGS, ids=["kling", "wavespeed", "bach"])
@pytest.mark.parametrize("libtv_mode", ["fake", "replay"])
async def test_runner_direct_execution_rejects_before_calling_real_provider(
    tmp_path: Path, provider_options, libtv_mode
) -> None:
    settings = Settings(
        app_env="production",
        libtv_adapter_mode=libtv_mode,
        runner_root=tmp_path / "runner",
        **provider_options,
        _env_file=None,
    )
    provider = Mock()
    provider.get_provider_name.return_value = settings.active_kling_provider_name
    provider.submit = AsyncMock()
    object_store = AsyncMock()
    supervisor = RunnerSupervisor(
        Mock(), object_store, settings, kling_adapter=provider, command_host_manager=Mock()
    )
    supervisor._handle_error = AsyncMock()
    session = AsyncMock()
    command = GenerationCommand(id=uuid.uuid4(), attempt_id=uuid.uuid4())
    attempt = GenerationAttempt(
        id=command.attempt_id, variant_id=uuid.uuid4(), provider=settings.active_kling_provider_name
    )
    assert await supervisor._execute_kling(session, command, attempt) is True
    assert supervisor._handle_error.await_args.args[-1].code == "PAID_GENERATION_BLOCKED"
    provider.submit.assert_not_awaited()
    object_store.localize.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "options",
    [
        {"shared_authentication_enabled": True},
        {"wavespeed_enabled": True},
        {"shared_authentication_enabled": True, "wavespeed_enabled": True},
        {"ai_adapter_mode": "openai"},
    ],
    ids=["shared", "real-provider", "shared-real-provider", "real-analysis"],
)
async def test_development_shared_or_real_provider_requires_pilot_allow_list_and_budget(
    pilot_database, options
) -> None:
    settings = Settings(app_env="development", **options, _env_file=None)
    async with pilot_database() as session:
        with pytest.raises(RuntimeControlBlockedError) as captured:
            await reserve_internal_pilot_budget(session, settings, user_id=USER_ID, units=1)
        assert captured.value.code == "INTERNAL_PILOT_DISABLED"
        await session.rollback()
    await configure_pilot(pilot_database, settings)
    async with pilot_database() as session:
        with pytest.raises(RuntimeControlBlockedError) as captured:
            await reserve_internal_pilot_budget(session, settings, user_id=OTHER_USER_ID, units=1)
        assert captured.value.code == "INTERNAL_PILOT_USER_NOT_ALLOWED"
        await session.rollback()
    async with pilot_database() as session:
        with pytest.raises(RuntimeControlBlockedError) as captured:
            await reserve_internal_pilot_budget(session, settings, user_id=USER_ID, units=3)
        assert captured.value.code == "PILOT_BUDGET_EXCEEDED"
        await session.rollback()
    async with pilot_database() as session:
        current = await get_runtime_config(session, settings)
        assert current.config_json["pilotSubmittedCount"] == 0


async def test_shared_development_real_pilot_admission_records_actual_actor(pilot_database) -> None:
    settings = authorized_provider_settings(wavespeed_enabled=True)
    await configure_pilot(pilot_database, settings)
    async with pilot_database() as session:
        admitted = await reserve_internal_pilot_budget(session, settings, user_id=USER_ID, units=2)
        await session.commit()
        assert admitted.config_json["pilotSubmittedCount"] == 2
        assert admitted.changed_by == USER_ID
        events = list(
            await session.scalars(
                select(AuditEvent).where(AuditEvent.reason.like("internal pilot admission%"))
            )
        )
        assert len(events) == 1
        assert events[0].actor_id == USER_ID
        assert events[0].entity_id == str(admitted.version)


async def test_shared_development_pilot_budget_serializes_competing_users(pilot_database) -> None:
    settings = authorized_provider_settings(wavespeed_enabled=True)
    await configure_pilot(
        pilot_database,
        settings,
        pilotUserIds=[str(USER_ID), str(OTHER_USER_ID), str(THIRD_USER_ID)],
        pilotBudgetLimit=1,
    )
    start = asyncio.Event()

    async def admit(user_id):
        async with pilot_database() as session:
            await start.wait()
            try:
                await reserve_internal_pilot_budget(session, settings, user_id=user_id, units=1)
                await session.commit()
                return user_id, "ADMITTED"
            except RuntimeControlBlockedError as exc:
                await session.rollback()
                return user_id, exc.code

    pending = [
        asyncio.create_task(admit(identity)) for identity in (USER_ID, OTHER_USER_ID, THIRD_USER_ID)
    ]
    start.set()
    results = await asyncio.gather(*pending)
    admitted = [identity for identity, result in results if result == "ADMITTED"]
    assert len(admitted) == 1
    assert sum(result == "PILOT_BUDGET_EXCEEDED" for _, result in results) == 2
    async with pilot_database() as session:
        current = await get_runtime_config(session, settings)
        assert current.config_json["pilotSubmittedCount"] == 1
        assert current.changed_by == admitted[0]
        events = list(
            await session.scalars(
                select(AuditEvent).where(AuditEvent.reason.like("internal pilot admission%"))
            )
        )
        assert len(events) == 1
        assert events[0].actor_id == admitted[0]


async def test_pilot_budget_and_actor_audit_roll_back_together(pilot_database) -> None:
    settings = authorized_provider_settings(wavespeed_enabled=True)
    await configure_pilot(pilot_database, settings)
    async with pilot_database() as session:
        await reserve_internal_pilot_budget(session, settings, user_id=USER_ID, units=1)
        await session.rollback()
    async with pilot_database() as session:
        current = await get_runtime_config(session, settings)
        assert current.config_json["pilotSubmittedCount"] == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.reason.like("internal pilot admission%"))
            )
            == 0
        )


@pytest.mark.parametrize("environment", ["development", "test"])
@pytest.mark.parametrize("libtv_mode", ["fake", "replay"])
async def test_local_synthetic_modes_keep_pilot_and_submission_compatibility(
    pilot_database, environment, libtv_mode
) -> None:
    settings = Settings(app_env=environment, libtv_adapter_mode=libtv_mode, _env_file=None)
    async with pilot_database() as session:
        current = await get_runtime_config(session, settings)
        admitted = await reserve_internal_pilot_budget(session, settings, user_id=USER_ID, units=3)
        assert admitted.version == current.version
        assert admitted.config_json["pilotSubmittedCount"] == 0
        await ensure_provider_submission_allowed(session, settings, "libtv", user_id=USER_ID)
        assert await provider_claims_allowed(session, settings, "libtv", user_id=USER_ID)


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
async def test_internal_pilot_allow_list_and_budget_are_atomic(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'pilot.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(app_env="production", _env_file=None)

    async with factory() as session:
        current = await get_runtime_config(session, settings)
        assert current is not None
        config = dict(current.config_json)
        config.update(
            {
                "internalPilotEnabled": True,
                "pilotUserIds": [str(USER_ID)],
                "pilotBudgetLimit": 2,
                "pilotSubmittedCount": 0,
            }
        )
        await update_runtime_config(
            session,
            settings,
            config=config,
            actor_id=ADMIN_ID,
            reason="enable pilot for test",
            expected_version=current.version,
        )
        await session.commit()

        await reserve_internal_pilot_budget(session, settings, user_id=USER_ID, units=2)
        await session.commit()
        current = await get_runtime_config(session, settings)
        assert current is not None
        assert current.config_json["pilotSubmittedCount"] == 2

        with pytest.raises(RuntimeControlBlockedError) as captured:
            await reserve_internal_pilot_budget(session, settings, user_id=USER_ID, units=1)
        assert captured.value.code == "PILOT_BUDGET_EXCEEDED"

    await engine.dispose()


@pytest.mark.asyncio
async def test_libtv_auth_required_blocks_only_libtv_provider(
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
        kling_api_enabled=True,
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
        assert current.config_json["paidSubmissionsPaused"] is False
        assert not await generation_claims_allowed(session, settings)
        with pytest.raises(RuntimeControlBlockedError) as captured:
            await ensure_paid_submission_allowed(session, settings)
        assert captured.value.code == "LIBTV_AUTH_REQUIRED"
        await ensure_provider_submission_allowed(session, settings, "kling")

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
        assert recovered.config_json["paidSubmissionsPaused"] is False
        assert await generation_claims_allowed(session, settings)

    await engine.dispose()


@pytest.mark.asyncio
async def test_libtv_auth_required_preserves_existing_paid_pause(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'auth-paused.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        app_env="development",
        libtv_adapter_mode="real",
        paid_submissions_paused=True,
        _env_file=None,
    )

    async with factory() as session:
        await set_libtv_auth_required(
            session,
            settings,
            required=True,
            reason="test expired login while globally paused",
        )
        await session.commit()
        current = await get_runtime_config(session, settings)
        assert current is not None
        assert current.config_json["libtvAuthRequired"] is True
        assert current.config_json["paidSubmissionsPaused"] is True

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


@pytest.mark.asyncio
async def test_real_kling_provider_requires_explicit_paid_authorization(tmp_path: Path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'provider-gate.db').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        app_env="development",
        libtv_adapter_mode="real",
        kling_api_enabled=True,
        kling_api_key="synthetic-configured-key",
        paid_submissions_paused=False,
        object_store_mode="local",
        _env_file=None,
    )
    async with factory() as session:
        with pytest.raises(RuntimeControlBlockedError) as captured:
            await ensure_provider_submission_allowed(
                session,
                settings,
                settings.kling_api_provider_name,
                user_id=USER_ID,
            )
        assert captured.value.code == "PAID_GENERATION_BLOCKED"
        assert not await provider_claims_allowed(
            session,
            settings,
            settings.kling_api_provider_name,
            user_id=USER_ID,
        )

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_kling_provider_opens_only_with_exact_paid_authorization(tmp_path: Path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'provider-open.db').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        app_env="development",
        libtv_adapter_mode="real",
        libtv_execution_mode="live",
        paid_generation_enabled=True,
        paid_generation_confirmation="I_ACCEPT_LIBTV_POINT_CHARGES",
        kling_api_enabled=True,
        kling_api_key="synthetic-configured-key",
        paid_submissions_paused=False,
        object_store_mode="local",
        _env_file=None,
    )
    async with factory() as session:
        await ensure_provider_submission_allowed(
            session,
            settings,
            settings.kling_api_provider_name,
            user_id=USER_ID,
        )
        assert await provider_claims_allowed(
            session,
            settings,
            settings.kling_api_provider_name,
            user_id=USER_ID,
        )

    await engine.dispose()


def _risk_attempt(
    index: int,
    *,
    user_id: uuid.UUID,
    provider: str,
    status: AttemptStatus,
    event_at: datetime,
) -> GenerationAttempt:
    task = ParentTask(
        user_id=user_id,
        client_task_id=f"risk-{provider}-{index}",
        title=f"Risk {provider} {index}",
        asset_count=1,
        consistency_level=ConsistencyLevel.PASS,
    )
    variant = GenerationVariant(
        parent_task=task,
        variant_type=VariantKind.STABLE,
        generation_config_json={},
    )
    return GenerationAttempt(
        variant=variant,
        intent_hash=f"{index:064d}",
        status=status,
        provider=provider,
        launch_started_at=event_at,
        updated_at=event_at,
    )


@pytest.mark.asyncio
async def test_single_unknown_does_not_pause_other_tasks_or_mutate_global_config(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'risk-one.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = authorized_provider_settings(
        kling_api_enabled=True,
        paid_submissions_paused=False,
        object_store_mode="local",
    )
    now = datetime.now(UTC)
    async with factory() as session:
        session.add_all(
            [
                _risk_attempt(
                    100,
                    user_id=USER_ID,
                    provider=settings.kling_api_provider_name,
                    status=AttemptStatus.UNKNOWN_AFTER_SUBMIT,
                    event_at=now - timedelta(minutes=5),
                ),
                _risk_attempt(
                    99,
                    user_id=USER_ID,
                    provider=settings.kling_api_provider_name,
                    status=AttemptStatus.UNKNOWN_AFTER_SUBMIT,
                    event_at=now - timedelta(hours=2),
                ),
            ]
        )
        await session.commit()

        await ensure_provider_submission_allowed(
            session,
            settings,
            "kling",
            user_id=OTHER_USER_ID,
        )
        await ensure_provider_submission_allowed(
            session,
            settings,
            "kling",
            user_id=USER_ID,
        )
        assert await provider_claims_allowed(
            session,
            settings,
            settings.kling_api_provider_name,
            user_id=OTHER_USER_ID,
        )
        current = await get_runtime_config(session, settings)
        assert current is not None
        assert current.version == 1
        assert current.config_json["paidSubmissionsPaused"] is False

    await engine.dispose()


@pytest.mark.asyncio
async def test_two_unknown_variants_of_one_parent_count_as_one_task(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'risk-parent.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = authorized_provider_settings(
        kling_api_enabled=True,
        paid_submissions_paused=False,
        object_store_mode="local",
    )
    now = datetime.now(UTC)
    task = ParentTask(
        user_id=USER_ID,
        client_task_id="risk-shared-parent",
        title="Risk shared parent",
        asset_count=1,
        consistency_level=ConsistencyLevel.PASS,
    )
    for index, kind in enumerate((VariantKind.STABLE, VariantKind.DYNAMIC), start=1):
        variant = GenerationVariant(
            parent_task=task,
            variant_type=kind,
            generation_config_json={},
        )
        GenerationAttempt(
            variant=variant,
            intent_hash=f"{300 + index:064d}",
            status=AttemptStatus.UNKNOWN_AFTER_SUBMIT,
            provider=settings.kling_api_provider_name,
            launch_started_at=now - timedelta(minutes=index),
            updated_at=now - timedelta(minutes=index),
        )
    async with factory() as session:
        session.add(task)
        await session.commit()

        risk = await assess_unknown_submission_risk(
            session,
            settings,
            "kling",
            user_id=USER_ID,
            now=now,
        )
        assert risk.user_unknown_task_count == 1
        assert risk.provider_unknown_task_count == 1
        assert not risk.block_user
        assert not risk.block_provider

    await engine.dispose()


@pytest.mark.asyncio
async def test_user_unknown_circuit_isolated_by_provider_and_user(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'risk-user.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = authorized_provider_settings(
        kling_api_enabled=True,
        paid_submissions_paused=False,
        object_store_mode="local",
    )
    now = datetime.now(UTC)
    async with factory() as session:
        session.add_all(
            [
                _risk_attempt(
                    index,
                    user_id=USER_ID,
                    provider=settings.kling_api_provider_name,
                    status=AttemptStatus.UNKNOWN_AFTER_SUBMIT,
                    event_at=now - timedelta(minutes=offset),
                )
                for offset, index in enumerate((101, 102), start=1)
            ]
        )
        await session.commit()

        with pytest.raises(RuntimeControlBlockedError) as captured:
            await ensure_provider_submission_allowed(
                session,
                settings,
                "kling",
                user_id=USER_ID,
            )
        assert captured.value.code == "USER_PROVIDER_UNKNOWN_CIRCUIT_OPEN"
        assert not await provider_claims_allowed(
            session,
            settings,
            settings.kling_api_provider_name,
            user_id=USER_ID,
        )
        assert await provider_claims_allowed(
            session,
            settings,
            settings.kling_api_provider_name,
            user_id=OTHER_USER_ID,
        )
        await ensure_provider_submission_allowed(
            session,
            settings,
            "kling",
            user_id=OTHER_USER_ID,
        )
        libtv_risk = await assess_unknown_submission_risk(
            session,
            settings,
            "libtv",
            user_id=USER_ID,
            now=now,
        )
        assert not libtv_risk.block_user
        assert not libtv_risk.block_provider

    await engine.dispose()


@pytest.mark.asyncio
async def test_provider_unknown_circuit_requires_multi_user_burst_and_minimum_sample(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'risk-provider.db').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = authorized_provider_settings(
        kling_api_enabled=True,
        paid_submissions_paused=False,
        object_store_mode="local",
    )
    now = datetime.now(UTC)
    users = [USER_ID, OTHER_USER_ID, THIRD_USER_ID, USER_ID, OTHER_USER_ID]
    async with factory() as session:
        session.add_all(
            [
                _risk_attempt(
                    200 + index,
                    user_id=user_id,
                    provider=settings.kling_api_provider_name,
                    status=AttemptStatus.UNKNOWN_AFTER_SUBMIT,
                    event_at=now - timedelta(seconds=index),
                )
                for index, user_id in enumerate(users)
            ]
            + [
                _risk_attempt(
                    299,
                    user_id=THIRD_USER_ID,
                    provider=settings.kling_api_provider_name,
                    status=AttemptStatus.SUCCEEDED,
                    event_at=now,
                )
            ]
        )
        await session.commit()

        risk = await assess_unknown_submission_risk(
            session,
            settings,
            "kling",
            user_id=uuid.uuid4(),
            now=now,
        )
        assert risk.block_provider
        assert risk.provider_attempt_count == 6
        assert risk.provider_unknown_task_count == 5
        assert risk.provider_unknown_user_count == 3
        assert not await provider_claims_allowed(
            session,
            settings,
            settings.kling_api_provider_name,
            user_id=uuid.uuid4(),
        )

    await engine.dispose()


@pytest.mark.asyncio
async def test_manual_paid_pause_blocks_confirmation_but_not_already_queued_claims(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'manual-pause.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = authorized_provider_settings(
        kling_api_enabled=True,
        paid_submissions_paused=True,
        object_store_mode="local",
    )
    async with factory() as session:
        with pytest.raises(RuntimeControlBlockedError) as captured:
            await ensure_provider_submission_allowed(
                session,
                settings,
                "kling",
                user_id=USER_ID,
            )
        assert captured.value.code == "PAID_SUBMISSIONS_PAUSED"
        assert await provider_claims_allowed(
            session,
            settings,
            settings.kling_api_provider_name,
            user_id=USER_ID,
        )

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
async def test_kling_capacity_uses_parent_task_when_canvas_is_absent(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'kling-slots.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(object_store_mode="local", _env_file=None)
    async with factory() as session:
        session.add(User(id=USER_ID, username="kling-capacity-user", password_hash="disabled"))
        task, _variant, attempt, command = _command_graph(3)
        attempt.provider = settings.kling_cli_provider_name
        attempt.project_uuid = None
        session.add(command)
        await session.commit()

        lease = await acquire_capacity(session, settings, command)

        assert lease is not None
        assert len(lease.slot_ids) == 3
        assert task.id is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_libtv_and_kling_use_independent_capacity_scopes(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'provider-slots.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(object_store_mode="local", _env_file=None)
    async with factory() as session:
        session.add(User(id=USER_ID, username="provider-capacity-user", password_hash="disabled"))
        libtv_command = _command_graph(4)[-1]
        _task, _variant, kling_attempt, kling_command = _command_graph(5)
        kling_attempt.provider = settings.kling_cli_provider_name
        kling_attempt.project_uuid = None
        second_libtv_command = _command_graph(6)[-1]
        session.add_all([libtv_command, kling_command, second_libtv_command])
        await session.commit()

        assert await acquire_capacity(session, settings, libtv_command) is not None
        assert await acquire_capacity(session, settings, kling_command) is not None
        assert await acquire_capacity(session, settings, second_libtv_command) is None
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
