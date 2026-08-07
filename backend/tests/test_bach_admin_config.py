import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import Base
from libtv_agent.services.bach_config import load_bach_admin_config
from sqlalchemy.ext.asyncio import create_async_engine

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ACCESS_KEY = "bach-access-key-never-return"
SECRET_KEY = "bach-secret-key-never-return"


async def _database(tmp_path: Path) -> str:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'bach.db').as_posix()}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return url


def _settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url=database_url,
        object_store_mode="local",
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        admin_credentials_file=tmp_path / "runtime" / "admin-credentials.json",
        kling_admin_config_file=tmp_path / "runtime" / "kling-config.json",
        wavespeed_admin_config_file=tmp_path / "runtime" / "wavespeed-config.json",
        bach_admin_config_file=tmp_path / "runtime" / "bach-config.json",
        _env_file=None,
    )


@pytest.mark.asyncio
async def test_admin_can_store_bach_ak_sk_without_echoing_them(tmp_path: Path) -> None:
    settings = _settings(await _database(tmp_path), tmp_path)
    app = create_app(settings)
    headers = {"X-User-Id": str(ADMIN_ID)}

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            initial = await client.get("/api/v1/admin/bach/config", headers=headers)
            assert initial.status_code == 200
            assert initial.json()["credentialsConfigured"] is False

            updated = await client.patch(
                "/api/v1/admin/bach/config",
                headers=headers,
                json={
                    "accessKey": ACCESS_KEY,
                    "secretKey": SECRET_KEY,
                    "enabled": True,
                    "model": "bach-image-to-video-v2",
                },
            )
            assert updated.status_code == 200
            assert updated.json()["credentialsConfigured"] is True
            assert updated.json()["credentialSource"] == "admin"
            assert ACCESS_KEY not in updated.text
            assert SECRET_KEY not in updated.text
            encrypted = settings.bach_admin_config_file.read_text(encoding="utf-8")
            assert ACCESS_KEY not in encrypted
            assert SECRET_KEY not in encrypted

            switched = await client.patch(
                "/api/v1/admin/kling/config",
                headers=headers,
                json={"backend": "bach"},
            )
            assert switched.status_code == 200, switched.text
            system = await client.get("/api/v1/system/status", headers=headers)
            assert system.status_code == 200
            assert system.json()["videoGeneration"]["provider"] == "bach"
            assert system.json()["videoGeneration"]["model"] == "bach-image-to-video-v2"
            assert system.json()["videoGeneration"]["imageInputLimit"] == 2
            assert system.json()["videoGeneration"]["videoDurations"] == [
                str(value) for value in range(1, 9)
            ]
            assert system.json()["videoGeneration"]["tailImageVideoDurations"] == [
                str(value) for value in range(1, 7)
            ]

            reloaded = _settings(settings.database_url, tmp_path)
            assert load_bach_admin_config(reloaded) is True
            assert reloaded.effective_bach_access_key == ACCESS_KEY
            assert reloaded.effective_bach_secret_key == SECRET_KEY


@pytest.mark.asyncio
async def test_non_admin_cannot_read_or_modify_bach_credentials(tmp_path: Path) -> None:
    settings = _settings(await _database(tmp_path), tmp_path)
    app = create_app(settings)
    headers = {"X-User-Id": str(USER_ID)}

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (
                await client.get("/api/v1/admin/bach/config", headers=headers)
            ).status_code == 403
            assert (
                await client.patch(
                    "/api/v1/admin/bach/config",
                    headers=headers,
                    json={"accessKey": ACCESS_KEY, "secretKey": SECRET_KEY},
                )
            ).status_code == 403
