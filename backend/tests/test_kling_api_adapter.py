from __future__ import annotations

import asyncio
import base64
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from libtv_agent.adapters.kling_official_api import (
    ApiHttpResponse,
    KlingApiError,
    KlingOfficialApiAdapter,
    map_kling_api_status,
)
from libtv_agent.adapters.video_provider import VideoGenerationRequest
from libtv_agent.config import Settings
from PIL import Image


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "development",
        "runner_root": tmp_path / "runner",
        "artifact_root": tmp_path / "artifacts",
        "kling_provider_backend": "api",
        "kling_api_enabled": True,
        "kling_api_key": "test-api-key",
        "kling_api_max_retries": 2,
        "kling_api_request_timeout_seconds": 2,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def _image(path: Path, color: str) -> Path:
    Image.new("RGB", (320, 320), color).save(path)
    return path


def _request(first: Path, second: Path | None = None) -> VideoGenerationRequest:
    return VideoGenerationRequest(
        prompt="原样提示词 @image_2",
        model="kling-3.0-omni",
        image_paths=(first,),
        product_reference_paths=(second,) if second else (),
        duration=10,
        aspect_ratio="9:16",
        resolution="1080p",
        audio="off",
        multi_shot=True,
        external_task_id="local-intent-001",
    )


@pytest.mark.asyncio
async def test_request_mapping_preserves_prompt_and_image_order(tmp_path: Path) -> None:
    first = _image(tmp_path / "01-first.png", "red")
    second = _image(tmp_path / "02-product.jpg", "blue")
    adapter = KlingOfficialApiAdapter(_settings(tmp_path))

    payload = await adapter.build_request_payload(_request(first, second))

    assert payload["contents"][0] == {"type": "prompt", "text": "原样提示词 @image_2"}
    assert [(item["type"], item["id"]) for item in payload["contents"][1:]] == [
        ("first_frame", "image_1"),
        ("refer_image", "image_2"),
    ]
    assert base64.b64decode(payload["contents"][1]["url"]) == first.read_bytes()
    assert base64.b64decode(payload["contents"][2]["url"]) == second.read_bytes()
    assert payload["settings"] == {
        "resolution": "1080p",
        "duration": 10,
        "audio": "off",
        "multi_shot": True,
        "aspect_ratio": "9:16",
    }
    assert payload["options"]["external_task_id"] == "local-intent-001"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("submitted", "queued"),
        ("processing", "running"),
        ("succeeded", "succeeded"),
        ("failed", "failed"),
        ("success", "unknown"),
        ("completed", "unknown"),
    ],
)
def test_status_mapping_is_strict(raw: str, expected: str) -> None:
    assert map_kling_api_status(raw) == expected


@pytest.mark.asyncio
async def test_rate_limit_is_retryable_and_honors_retry_after(tmp_path: Path) -> None:
    async def limited(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        request_timeout: float,
    ) -> ApiHttpResponse:
        del method, url, headers, body, request_timeout
        return ApiHttpResponse(
            429,
            {"Retry-After": "7"},
            json.dumps({"code": 1303, "message": "concurrency limited"}).encode(),
        )

    adapter = KlingOfficialApiAdapter(_settings(tmp_path), http_request=limited)
    with pytest.raises(KlingApiError) as caught:
        await adapter.query("task-1")
    assert caught.value.code == "KLING_API_RATE_LIMITED"
    assert caught.value.retryable is True
    assert caught.value.retry_after_seconds == 7
    assert caught.value.uncertain is False


@pytest.mark.asyncio
async def test_timeout_recovers_by_external_task_id_without_second_submit(tmp_path: Path) -> None:
    first = _image(tmp_path / "first.png", "red")
    calls: list[tuple[str, str]] = []

    async def recover(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        request_timeout: float,
    ) -> ApiHttpResponse:
        del headers, body, request_timeout
        calls.append((method, url))
        if method == "POST":
            raise TimeoutError
        return ApiHttpResponse(
            200,
            {},
            json.dumps(
                {
                    "code": 0,
                    "message": "ok",
                    "data": [
                        {
                            "id": "remote-1",
                            "external_id": "local-intent-001",
                            "status": "processing",
                            "outputs": [],
                        }
                    ],
                }
            ).encode(),
        )

    adapter = KlingOfficialApiAdapter(_settings(tmp_path), http_request=recover)
    result = await adapter.submit(_request(first))

    assert result.provider_task_id == "remote-1"
    assert result.raw_response["recoveredByExternalTaskId"] is True
    assert [method for method, _ in calls].count("POST") == 1
    assert "external_task_ids=local-intent-001" in calls[-1][1]


class _KlingMockHandler(BaseHTTPRequestHandler):
    post_bodies: list[dict[str, Any]] = []
    query_count = 0
    video = b"\x00\x00\x00\x18ftypmp42mock-video"

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _json(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers["Content-Length"])
        self.post_bodies.append(json.loads(self.rfile.read(length)))
        self._json(
            {
                "code": 0,
                "message": "ok",
                "data": {
                    "id": "mock-task",
                    "external_id": "local-intent-001",
                    "status": "submitted",
                },
            }
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/video.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(self.video)))
            self.end_headers()
            self.wfile.write(self.video)
            return
        self.__class__.query_count += 1
        status = "processing" if self.query_count < 3 else "succeeded"
        outputs = (
            []
            if status == "processing"
            else [
                {
                    "type": "video",
                    "id": "video-1",
                    "url": f"http://127.0.0.1:{self.server.server_port}/video.mp4",
                    "duration": 10,
                }
            ]
        )
        self._json(
            {
                "code": 0,
                "message": "ok",
                "data": [
                    {
                        "id": "mock-task",
                        "external_id": "local-intent-001",
                        "status": status,
                        "outputs": outputs,
                        "billing": [{"charge_type": "unit", "amount": 8}],
                    }
                ],
            }
        )


@contextmanager
def _mock_server() -> Iterator[ThreadingHTTPServer]:
    _KlingMockHandler.post_bodies = []
    _KlingMockHandler.query_count = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _KlingMockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_mock_http_submit_poll_and_atomic_download(tmp_path: Path) -> None:
    first = _image(tmp_path / "first.png", "green")
    with _mock_server() as server:
        adapter = KlingOfficialApiAdapter(
            _settings(tmp_path, kling_api_base_url=f"http://127.0.0.1:{server.server_port}")
        )
        submission = await adapter.submit(_request(first))
        statuses = []
        for _ in range(3):
            result = await adapter.query(submission.provider_task_id)
            statuses.append(result.status)
        destination = tmp_path / "output" / "video.mp4"
        downloaded = await adapter.download(result.outputs[0], destination)

    assert statuses == ["running", "running", "succeeded"]
    assert result.credits_consumed == 8
    assert downloaded.path.read_bytes() == _KlingMockHandler.video
    assert not destination.with_suffix(".mp4.part").exists()
    assert len(_KlingMockHandler.post_bodies) == 1
    assert _KlingMockHandler.post_bodies[0]["contents"][0]["text"] == "原样提示词 @image_2"


@pytest.mark.asyncio
async def test_submit_retries_429_without_rewriting_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _image(tmp_path / "first.png", "white")
    bodies: list[bytes] = []
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def flaky(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        request_timeout: float,
    ) -> ApiHttpResponse:
        del method, url, headers, request_timeout
        bodies.append(body or b"")
        if len(bodies) == 1:
            return ApiHttpResponse(
                429,
                {"Retry-After": "2"},
                json.dumps({"code": 1302, "message": "rate limited"}).encode(),
            )
        return ApiHttpResponse(
            200,
            {},
            json.dumps(
                {
                    "code": 0,
                    "message": "ok",
                    "data": {"id": "task-2", "status": "submitted"},
                }
            ).encode(),
        )

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    adapter = KlingOfficialApiAdapter(_settings(tmp_path), http_request=flaky)
    result = await adapter.submit(_request(first))

    assert result.provider_task_id == "task-2"
    assert bodies[0] == bodies[1]
    assert sleeps and sleeps[0] >= 2
