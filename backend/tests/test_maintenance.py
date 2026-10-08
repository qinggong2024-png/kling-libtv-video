import httpx
import pytest

from libtv_agent.config import Settings
from libtv_agent.maintenance import create_maintenance_app


async def test_query_only_lifecycle_and_write_boundary(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Recovery must not run")

    monkeypatch.setattr("libtv_agent.app._recover_stale_analyses", forbidden)
    monkeypatch.setattr("libtv_agent.app.recover_subject_element_jobs", forbidden)
    settings = Settings(
        _env_file=None, app_env="test", shared_authentication_enabled=True,
        session_secret="test-maintenance-secret-with-at-least-32-characters",
        database_url="sqlite+aiosqlite:///:memory:",
        runner_root=tmp_path / "runner", artifact_root=tmp_path / "artifacts",
        object_store_mode="local",
    )
    app = create_maintenance_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            live = await client.get("/api/v1/health/live")
            assert live.status_code == 200
            assert live.headers["X-LibTV-Maintenance"] == "query-only"
            for method, path in [("POST", "/api/v1/tasks"), ("POST", "/api/v1/confirmations"), ("GET", "/api/v1/kling/elements")]:
                response = await client.request(method, path)
                assert response.status_code == 503
                assert response.json()["detail"]["code"] == "MAINTENANCE_QUERY_ONLY"
                assert response.json()["detail"]["message"] == "当前仅支持登录和查询已保存任务，生成暂不可用。"
            assert (await client.get("/api/v1/auth/me")).status_code == 401


def test_maintenance_requires_authentication(tmp_path):
    with pytest.raises(ValueError, match="shared authentication"):
        create_maintenance_app(Settings(
            _env_file=None, app_env="test", shared_authentication_enabled=False,
            runner_root=tmp_path / "runner", artifact_root=tmp_path / "artifacts",
            object_store_mode="local",
        ))
