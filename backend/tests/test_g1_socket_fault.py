"""Real loopback HTTP disconnect with the production adapter transport."""

import socket
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.adapters.wavespeed import (
    WaveSpeedAdapter,
    WaveSpeedAvailability,
    WaveSpeedError,
    build_generation_payload,
)
from libtv_agent.config import Settings
from libtv_agent.domain.models import ImageGenerationItem
from sqlalchemy import select
from test_image_quota_concurrency import post, world  # noqa: F401


@pytest.fixture
def disconnected_receiver():
    bodies = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            bodies.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 18439), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield bodies
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.asyncio
async def test_receiver_accepts_paid_body_then_drops_response_without_post_retry(
    tmp_path, disconnected_receiver
):
    bodies = disconnected_receiver
    settings = Settings(
        _env_file=None,
        app_env="test",
        wavespeed_enabled=True,
        wavespeed_api_key="synthetic-only",
        wavespeed_get_max_retries=4,
        wavespeed_api_base_url="http://127.0.0.1:18439/api/v3",
        runner_root=tmp_path / "runner",
        artifact_root=tmp_path / "artifacts",
    )
    adapter = WaveSpeedAdapter(settings)
    model, payload = build_generation_payload(
        provider="gpt-image-2", mode="text-to-image", prompt="synthetic garment"
    )
    with pytest.raises(WaveSpeedError) as captured:
        await adapter.submit_prediction(model, payload)
    assert captured.value.submitted is True
    assert captured.value.uncertain is True
    assert captured.value.retryable is False
    assert len(bodies) == 1
    assert b"synthetic garment" in bodies[0]


async def test_paid_disconnect_is_persisted_and_not_reposted(world, disconnected_receiver):  # noqa: F811
    app, factory, original_provider, users = world
    app.state.settings.wavespeed_api_base_url = "http://127.0.0.1:18439/api/v3"
    adapter = WaveSpeedAdapter(app.state.settings)
    adapter._last_availability = WaveSpeedAvailability(
        "AVAILABLE", True, True, None, datetime.now(UTC)
    )
    adapter.upload_media = original_provider.upload_media
    app.state.wavespeed_adapter = adapter
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await post(client, users[0], "disconnect")
        assert created.status_code == 201, created.text
        assert created.json()["status"] == "write_uncertain"
        replay = await post(client, users[0], "disconnect")
        assert replay.status_code == 201
        assert replay.json()["id"] == created.json()["id"]
        # A replacement adapter/default must not turn an unknown into a new paid attempt.
        app.state.wavespeed_adapter = original_provider
        repeated = await post(client, users[0], "disconnect")
        assert repeated.json()["status"] == "write_uncertain"
    async with factory() as session:
        item = await session.scalar(select(ImageGenerationItem))
        assert item.status == "WRITE_UNCERTAIN"
        assert item.provider_task_id is None
    assert len(disconnected_receiver) == 1
    assert original_provider.submissions == []
