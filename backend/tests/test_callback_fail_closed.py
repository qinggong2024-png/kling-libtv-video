import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from libtv_agent.api.kling import router
from libtv_agent.config import Settings
from libtv_agent.runner.supervisor import RunnerSupervisor


def test_provider_routing_survives_default_provider_replacement(tmp_path, monkeypatch):
    class Adapter:
        def __init__(self, name):
            self.name = name

        def get_provider_name(self):
            return self.name

    original = Adapter("kling_official_api")
    replacement = Adapter("wavespeed_video")
    requested = []

    def factory(settings, provider):
        requested.append(provider)
        assert provider == "kling_official_api"
        return original

    monkeypatch.setattr(
        "libtv_agent.runner.supervisor.create_kling_adapter_for_provider", factory
    )
    supervisor = RunnerSupervisor(
        object(), object(),
        Settings(_env_file=None, app_env="test", runner_root=tmp_path / "runner"),
        kling_adapter=original,
    )
    supervisor.replace_kling_adapter(replacement)
    assert supervisor._kling_adapter_for("kling_official_api") is original
    assert supervisor._kling_adapter_for("kling_official_api") is original
    assert supervisor._kling_adapter_for("wavespeed_video") is replacement
    assert requested == ["kling_official_api"]


@pytest.mark.parametrize("body", [b"", b"not-json", b'{"id":"synthetic"}'])
@pytest.mark.parametrize("signature", [None, "forged-signature"])
async def test_callback_rejects_without_database_or_provider(body, signature):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    headers = {"Content-Type": "application/json"}
    if signature:
        headers["X-Kling-Callback-Signature"] = signature
    # No settings, DB or adapter exists: any dependency access fails this test.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/kling/callback", content=body, headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "KLING_CALLBACK_DISABLED"
    assert response.json()["detail"]["retryable"] is False
