from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from libtv_agent.adapters.libtv import LibTVError
from libtv_agent.config import Settings
from libtv_agent.domain.models import Base
from libtv_agent.runner.service_runtime import _refresh_libtv_auth_state
from libtv_agent.runner.windows_service import (
    SERVICE_ACCOUNT,
    SERVICE_NAME,
    service_preflight,
)
from libtv_agent.services.runtime_control import get_runtime_config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def test_windows_service_contract_matches_runtime_settings() -> None:
    settings = Settings(_env_file=None)

    assert SERVICE_NAME == settings.runner_service_name
    assert SERVICE_ACCOUNT == settings.runner_service_account


def test_windows_runner_preflight_has_no_missing_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("LIBTV_EXECUTION_MODE", "dry-run")
    monkeypatch.setenv("PAID_GENERATION_ENABLED", "false")
    monkeypatch.setenv("PAID_GENERATION_CONFIRMATION", "")
    result = service_preflight()

    assert result["status"] == "PASS", result["issues"]
    assert result["serviceName"] == SERVICE_NAME
    assert result["serviceAccount"] == SERVICE_ACCOUNT
    assert result["issues"] == []


@pytest.mark.asyncio
async def test_runner_account_monitor_sets_and_clears_auth_requirement(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'monitor.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        app_env="test",
        libtv_adapter_mode="real",
        _env_file=None,
    )
    adapter = AsyncMock()
    adapter.check_account.side_effect = LibTVError(
        "LIBTV_AUTH_REQUIRED",
        "login expired",
    )

    async with factory() as session:
        assert not await _refresh_libtv_auth_state(session, adapter, settings)
        await session.commit()
        expired = await get_runtime_config(session, settings)
        assert expired is not None
        assert expired.config_json["libtvAuthRequired"] is True

        adapter.check_account.side_effect = None
        adapter.check_account.return_value = {"ok": True}
        assert await _refresh_libtv_auth_state(session, adapter, settings)
        await session.commit()
        recovered = await get_runtime_config(session, settings)
        assert recovered is not None
        assert recovered.config_json["libtvAuthRequired"] is False
        assert recovered.config_json["paidSubmissionsPaused"] is True

    await engine.dispose()
