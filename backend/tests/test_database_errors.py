import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings


@pytest.mark.asyncio
async def test_missing_schema_is_reported_as_actionable_503() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/v1/tasks",
                headers={"X-User-Id": str(settings.dev_user_id)},
            )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DATABASE_SCHEMA_OUTDATED"
    assert "自动完成迁移" in response.json()["detail"]["message"]
