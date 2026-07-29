import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import Base
from libtv_agent.services.libtv_login import LibTVLoginStart
from sqlalchemy.ext.asyncio import create_async_engine

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
LOGIN_URL = "https://www.liblib.tv/zh?callback_url=http%3A%2F%2F127.0.0.1%3A6708%2Fcallback"


@pytest.mark.asyncio
async def test_admin_can_start_login_and_switch_libtv_account(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'account.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    settings = Settings(
        app_env="test",
        database_url=database_url,
        libtv_adapter_mode="real",
        libtv_config_dir=tmp_path / "libtv",
        object_store_mode="local",
        _env_file=None,
    )
    app = create_app(settings)
    adapter = AsyncMock()
    adapter.list_accounts.return_value = {
        "accounts": [
            {
                "accountId": 101,
                "accountName": "个人空间",
                "accountType": "PERSONAL",
                "isActive": True,
                "teamId": 0,
            },
            {
                "accountId": 202,
                "accountName": "生产团队",
                "accountType": "TEAM",
                "isActive": False,
                "teamId": 202,
            },
        ]
    }
    adapter.use_account.return_value = {
        "ok": True,
        "accountId": 202,
        "accountName": "生产团队",
        "accountType": "TEAM",
        "teamId": 202,
    }
    login_manager = AsyncMock()
    login_manager.in_progress.return_value = False
    login_manager.start.return_value = LibTVLoginStart(
        session_id="login-session",
        login_url=LOGIN_URL,
        started_at="2026-07-28T00:00:00+00:00",
    )
    app.state.libtv_adapter = adapter
    app.state.libtv_login_manager = login_manager
    admin_headers = {"X-User-Id": str(ADMIN_ID)}

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            account = await client.get("/api/v1/admin/libtv-account", headers=admin_headers)
            assert account.status_code == 200
            assert account.json()["authenticated"] is True
            assert account.json()["activeAccount"]["accountId"] == "101"
            assert len(account.json()["accounts"]) == 2

            login_headers = {**admin_headers, "Idempotency-Key": "login-key"}
            started = await client.post(
                "/api/v1/admin/libtv-login/start",
                headers=login_headers,
            )
            assert started.status_code == 200
            assert started.json()["loginUrl"] == LOGIN_URL
            login_manager.start.assert_awaited_once_with("libtv", tmp_path / "libtv")

            switched = await client.post(
                "/api/v1/admin/libtv-account/use",
                headers={**admin_headers, "Idempotency-Key": "switch-key"},
                json={"account": "202"},
            )
            assert switched.status_code == 200
            assert switched.json()["accountName"] == "生产团队"
            adapter.use_account.assert_awaited_once_with("202")

            forbidden = await client.get(
                "/api/v1/admin/libtv-account",
                headers={"X-User-Id": str(USER_ID)},
            )
            assert forbidden.status_code == 403
