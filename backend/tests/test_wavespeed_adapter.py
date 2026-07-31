import json
from pathlib import Path

import pytest
from libtv_agent.adapters.wavespeed import (
    WaveSpeedAdapter,
    WaveSpeedError,
    WaveSpeedHttpResponse,
    build_generation_payload,
)
from libtv_agent.config import Settings


def _settings(tmp_path: Path, **updates: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "wavespeed_enabled": True,
        "wavespeed_api_key": "environment-wavespeed-key",
        "wavespeed_api_base_url": "http://127.0.0.1:9876/api/v3",
        "artifact_root": tmp_path / "artifacts",
        "runner_root": tmp_path / "runner",
        "_env_file": None,
    }
    values.update(updates)
    return Settings(**values)


@pytest.mark.parametrize(
    ("provider", "mode", "expected_model", "expected_keys", "forbidden_keys"),
    [
        (
            "gpt-image-2",
            "edit",
            "openai/gpt-image-2/edit",
            {"images", "quality"},
            {"enable_web_search", "enable_image_search"},
        ),
        (
            "gpt-image-2",
            "text-to-image",
            "openai/gpt-image-2/text-to-image",
            {"quality"},
            {"images", "enable_web_search", "enable_image_search"},
        ),
        (
            "nano-banana-2",
            "edit",
            "google/nano-banana-2/edit",
            {"images", "enable_web_search", "enable_image_search"},
            {"quality"},
        ),
        (
            "nano-banana-2",
            "text-to-image",
            "google/nano-banana-2/text-to-image",
            {"enable_web_search", "enable_image_search"},
            {"images", "quality"},
        ),
    ],
)
def test_four_model_payloads_are_strictly_mapped(
    provider: str,
    mode: str,
    expected_model: str,
    expected_keys: set[str],
    forbidden_keys: set[str],
) -> None:
    model_id, payload = build_generation_payload(
        provider=provider,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        prompt="dress the model",
        images=["https://example.test/reference.png"] if mode == "edit" else [],
    )

    assert model_id == expected_model
    assert expected_keys <= payload.keys()
    assert forbidden_keys.isdisjoint(payload)
    if provider == "nano-banana-2":
        assert payload["enable_web_search"] is False
        assert payload["enable_image_search"] is False


@pytest.mark.parametrize(
    ("provider", "limit"),
    [("gpt-image-2", 6), ("nano-banana-2", 4)],
)
def test_edit_reference_limits_match_provider_contract(provider: str, limit: int) -> None:
    images = [f"https://example.test/reference-{index}.png" for index in range(limit)]
    build_generation_payload(
        provider=provider,  # type: ignore[arg-type]
        mode="edit",
        prompt="dress the model",
        images=images,
    )

    with pytest.raises(WaveSpeedError, match=f"at most {limit}"):
        build_generation_payload(
            provider=provider,  # type: ignore[arg-type]
            mode="edit",
            prompt="dress the model",
            images=[*images, "https://example.test/one-too-many.png"],
        )


@pytest.mark.asyncio
async def test_upload_is_multipart_and_submit_post_is_never_retried(tmp_path: Path) -> None:
    calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    async def fake_http(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        request_timeout: float,
    ) -> WaveSpeedHttpResponse:
        del request_timeout
        calls.append((method, url, headers, body))
        if url.endswith("/media/upload/binary"):
            return WaveSpeedHttpResponse(
                200,
                {},
                json.dumps({"data": {"download_url": "https://cdn.test/input.png"}}).encode(),
            )
        return WaveSpeedHttpResponse(
            503, {}, json.dumps({"error": "provider unavailable"}).encode()
        )

    adapter = WaveSpeedAdapter(_settings(tmp_path), http_request=fake_http)
    uploaded = await adapter.upload_media(b"png-data", filename="input.png")
    model_id, payload = build_generation_payload(
        provider="gpt-image-2",
        mode="edit",
        prompt="test",
        images=[uploaded],
    )
    with pytest.raises(WaveSpeedError) as captured:
        await adapter.submit_prediction(model_id, payload)

    assert uploaded == "https://cdn.test/input.png"
    assert calls[0][0] == "POST"
    assert calls[0][2]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="file"' in (calls[0][3] or b"")
    assert [call[0] for call in calls] == ["POST", "POST"]
    assert captured.value.code == "WAVESPEED_SERVICE_UNAVAILABLE"
    assert captured.value.submitted is True
    assert captured.value.uncertain is True


@pytest.mark.asyncio
async def test_upload_uses_portable_content_type_for_webp(tmp_path: Path) -> None:
    captured_body: bytes | None = None

    async def fake_http(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        request_timeout: float,
    ) -> WaveSpeedHttpResponse:
        nonlocal captured_body
        del method, url, headers, request_timeout
        captured_body = body
        return WaveSpeedHttpResponse(
            200,
            {},
            json.dumps({"data": {"download_url": "https://cdn.test/input.webp"}}).encode(),
        )

    adapter = WaveSpeedAdapter(_settings(tmp_path), http_request=fake_http)
    uploaded = await adapter.upload_media(b"webp-data", filename="input.webp")

    assert uploaded == "https://cdn.test/input.webp"
    assert b"Content-Type: image/webp" in (captured_body or b"")


@pytest.mark.asyncio
async def test_get_prediction_retries_only_retryable_statuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def fake_http(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        request_timeout: float,
    ) -> WaveSpeedHttpResponse:
        nonlocal calls
        del url, headers, body, request_timeout
        assert method == "GET"
        calls += 1
        if calls == 1:
            return WaveSpeedHttpResponse(429, {"Retry-After": "2"}, b'{"message":"slow"}')
        return WaveSpeedHttpResponse(
            200,
            {},
            json.dumps(
                {
                    "data": {
                        "id": "task-1",
                        "status": "completed",
                        "outputs": ["https://cdn.test/output.png"],
                    }
                }
            ).encode(),
        )

    monkeypatch.setattr("libtv_agent.adapters.wavespeed.asyncio.sleep", fake_sleep)
    adapter = WaveSpeedAdapter(_settings(tmp_path), http_request=fake_http)
    prediction = await adapter.get_prediction("task-1")

    assert prediction.status == "completed"
    assert prediction.outputs == ("https://cdn.test/output.png",)
    assert calls == 2
    assert sleeps == [2.0]


@pytest.mark.asyncio
async def test_submit_preserves_parsed_raw_response(tmp_path: Path) -> None:
    envelope = {
        "data": {
            "id": "task-2",
            "status": "created",
            "urls": {"get": "https://api.wavespeed.ai/api/v3/predictions/task-2/result"},
        }
    }

    async def fake_http(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        request_timeout: float,
    ) -> WaveSpeedHttpResponse:
        del method, url, headers, body, request_timeout
        return WaveSpeedHttpResponse(200, {}, json.dumps(envelope).encode())

    adapter = WaveSpeedAdapter(_settings(tmp_path), http_request=fake_http)
    model_id, payload = build_generation_payload(
        provider="nano-banana-2", mode="text-to-image", prompt="a garment"
    )
    submission = await adapter.submit_prediction(model_id, payload)

    assert submission.task_id == "task-2"
    assert submission.raw_response == envelope
