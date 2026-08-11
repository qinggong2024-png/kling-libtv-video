import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import Base


@pytest.mark.asyncio
async def test_live_health_does_not_require_infrastructure() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_invalid_provider_config_reload_keeps_api_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )
    app = create_app(settings)
    original_adapter = app.state.wavespeed_adapter
    attempts = 0

    def invalid_reload(_settings: Settings) -> bool:
        nonlocal attempts
        attempts += 1
        raise ValueError("newer config schema")

    async with app.router.lifespan_context(app):
        monkeypatch.setattr(
            "libtv_agent.app.wavespeed_admin_config_signature", lambda _settings: (123, 456)
        )
        monkeypatch.setattr("libtv_agent.app.load_wavespeed_admin_config", invalid_reload)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.get("/api/v1/health/live")
            second = await client.get("/api/v1/health/live")

    assert first.status_code == 200
    assert second.status_code == 200
    assert attempts == 1
    assert app.state.wavespeed_adapter is original_adapter


@pytest.mark.asyncio
async def test_system_status_exposes_deployed_source_revision() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        deployment_source_revision="abc123",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/system/status")

    assert response.status_code == 200
    body = response.json()
    assert body["sourceRevision"] == "abc123"
    assert body["schemaRevision"].startswith("metadata-equivalent:")
    assert len(body["configRevision"]) == 64
    assert body["runtimeVersion"] == "0.1.0"


@pytest.mark.asyncio
async def test_ready_health_checks_database() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["postgresql"] == "ok"
    assert response.json()["checks"]["databaseSchema"] == "ok"


@pytest.mark.asyncio
async def test_ready_health_rejects_an_outdated_database_schema() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {
        "postgresql": "ok",
        "databaseSchema": "outdated",
    }
    assert "generation_feedback" in response.json()["databaseSchema"]["missingTables"]
