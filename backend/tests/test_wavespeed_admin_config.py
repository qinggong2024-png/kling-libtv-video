import json
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.adapters.wavespeed import WaveSpeedHttpResponse
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import AuditEvent, Base
from libtv_agent.services.wavespeed_config import (
    _StoredWaveSpeedConfig,
    update_wavespeed_admin_config,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ADMIN_KEY = "wavespeed-admin-secret-never-return"
ENVIRONMENT_KEY = "wavespeed-environment-secret-never-return"


async def _database(tmp_path: Path) -> str:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'wavespeed.db').as_posix()}"
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
        wavespeed_enabled=False,
        wavespeed_api_key=ENVIRONMENT_KEY,
        _env_file=None,
    )


def test_stored_config_preserves_future_fields_during_rolling_upgrades() -> None:
    config = _StoredWaveSpeedConfig.model_validate(
        {
            "format": "libtv-wavespeed-config-v1",
            "enabled": False,
            "futureProviderOption": {"mode": "safe"},
        }
    )

    assert config.model_dump()["futureProviderOption"] == {"mode": "safe"}


@pytest.mark.asyncio
async def test_admin_config_never_echoes_key_verifies_read_only_and_falls_back_to_env(
    tmp_path: Path,
) -> None:
    settings = _settings(await _database(tmp_path), tmp_path)
    app = create_app(settings)
    headers = {"X-User-Id": str(ADMIN_ID)}

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            initial = await client.get("/api/v1/admin/wavespeed/config", headers=headers)
            assert initial.status_code == 200
            assert initial.json()["credentialSource"] == "environment"
            assert initial.json()["apiKeyConfigured"] is True
            assert ENVIRONMENT_KEY not in initial.text

            updated = await client.patch(
                "/api/v1/admin/wavespeed/config",
                headers=headers,
                json={"apiKey": ADMIN_KEY, "enabled": True, "maxSubmitConcurrency": 50},
            )
            assert updated.status_code == 200
            assert updated.json()["credentialSource"] == "admin"
            assert updated.json()["maxSubmitConcurrency"] == 50
            assert updated.json()["status"] == "WAVESPEED_CONFIGURED_UNVERIFIED"
            assert ADMIN_KEY not in updated.text
            assert ADMIN_KEY not in settings.wavespeed_admin_config_file.read_text(encoding="utf-8")

            calls: list[tuple[str, bytes | None]] = []

            async def verify_http(
                method: str,
                url: str,
                request_headers: dict[str, str],
                body: bytes | None,
                request_timeout: float,
            ) -> WaveSpeedHttpResponse:
                del url, request_headers, request_timeout
                calls.append((method, body))
                return WaveSpeedHttpResponse(404, {}, b'{"message":"not found"}')

            app.state.wavespeed_adapter._http_request = verify_http
            verified = await client.post("/api/v1/admin/wavespeed/verify", headers=headers)
            assert verified.status_code == 200
            assert verified.json()["status"] == "WAVESPEED_READY"
            assert verified.json()["available"] is True
            assert verified.json()["verificationMayGenerateOrCharge"] is False
            assert calls == [("GET", None)]

            cleared = await client.patch(
                "/api/v1/admin/wavespeed/config",
                headers=headers,
                json={"clearApiKey": True},
            )
            assert cleared.status_code == 200
            assert cleared.json()["credentialSource"] == "environment"
            assert cleared.json()["apiKeyConfigured"] is True
            assert ADMIN_KEY not in cleared.text
            assert ENVIRONMENT_KEY not in cleared.text

            async with app.state.database.session_factory() as session:
                audits = list(
                    (
                        await session.scalars(
                            select(AuditEvent).where(
                                AuditEvent.action.in_(
                                    {
                                        "WAVESPEED_CONFIG_UPDATED",
                                        "WAVESPEED_CREDENTIALS_VERIFIED",
                                    }
                                )
                            )
                        )
                    ).all()
                )
            serialized = json.dumps(
                [
                    {
                        "action": audit.action,
                        "reason": audit.reason,
                        "evidence": audit.evidence_refs_json,
                    }
                    for audit in audits
                ]
            )
            assert ADMIN_KEY not in serialized
            assert ENVIRONMENT_KEY not in serialized


@pytest.mark.asyncio
async def test_wavespeed_submit_concurrency_rejects_values_above_50(tmp_path: Path) -> None:
    settings = _settings(await _database(tmp_path), tmp_path)
    app = create_app(settings)
    headers = {"X-User-Id": str(ADMIN_ID)}

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                "/api/v1/admin/wavespeed/config",
                headers=headers,
                json={"maxSubmitConcurrency": 51},
            )
            assert response.status_code == 422


@pytest.mark.asyncio
async def test_non_admin_cannot_read_or_modify_wavespeed_credentials(tmp_path: Path) -> None:
    settings = _settings(await _database(tmp_path), tmp_path)
    app = create_app(settings)
    headers = {"X-User-Id": str(USER_ID)}

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (
                await client.get("/api/v1/admin/wavespeed/config", headers=headers)
            ).status_code == 403
            assert (
                await client.patch(
                    "/api/v1/admin/wavespeed/config",
                    headers=headers,
                    json={"apiKey": ADMIN_KEY},
                )
            ).status_code == 403
            assert (
                await client.post("/api/v1/admin/wavespeed/verify", headers=headers)
            ).status_code == 403


def test_shared_environment_rejects_loopback_wavespeed_admin_endpoint(tmp_path: Path) -> None:
    settings = Settings(
        app_env="production",
        session_secret="production-session-secret",
        minio_secret_key="production-minio-secret",
        object_store_prefix="production",
        libtv_workspace_id="production-workspace",
        libtv_project_uuid="production-project",
        wavespeed_admin_config_file=tmp_path / "wavespeed-config.json",
        _env_file=None,
    )

    with pytest.raises(ValueError, match="loopback"):
        update_wavespeed_admin_config(settings, {"baseUrl": "http://127.0.0.1:9999"})
