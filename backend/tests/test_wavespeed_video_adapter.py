from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from libtv_agent.adapters.video_provider import ProviderOutput, VideoGenerationRequest
from libtv_agent.adapters.wavespeed import (
    WaveSpeedError,
    WaveSpeedPrediction,
    WaveSpeedSubmission,
)
from libtv_agent.adapters.wavespeed_video import WaveSpeedVideoAdapter, WaveSpeedVideoError
from libtv_agent.config import Settings
from libtv_agent.services.media import download_with_retries


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "development",
        "runner_root": tmp_path / "runner",
        "artifact_root": tmp_path / "artifacts",
        "wavespeed_enabled": True,
        "wavespeed_api_key": "test-only-key",
        "wavespeed_video_model": "kwaivgi/kling-video-o3-pro/reference-to-video",
        "wavespeed_video_duration": 10,
        "wavespeed_video_aspect_ratio": "9:16",
        "wavespeed_video_sound": False,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def _image(path: Path, contents: bytes = b"fake-image") -> Path:
    path.write_bytes(contents)
    return path


class FakeWaveSpeedClient:
    def __init__(self) -> None:
        self.uploads: list[Path] = []
        self.submissions: list[tuple[str, dict[str, object], bool]] = []
        self.prediction = WaveSpeedPrediction(
            task_id="prediction-1",
            status="processing",
            outputs=(),
            error=None,
            model_id="kwaivgi/kling-video-o3-pro/reference-to-video",
            raw_response={"data": {"id": "prediction-1", "status": "processing"}},
        )

    async def upload_media(self, source: str | Path | bytes, **kwargs: object) -> str:
        del kwargs
        assert isinstance(source, Path)
        self.uploads.append(source)
        return f"https://cdn.example/{source.name}"

    async def submit_prediction(
        self,
        model_id: str,
        payload: dict[str, object],
        *,
        validate_model: bool = True,
    ) -> WaveSpeedSubmission:
        self.submissions.append((model_id, payload, validate_model))
        return WaveSpeedSubmission(
            task_id="prediction-1",
            status="created",
            model_id=model_id,
            result_url="https://api.wavespeed.ai/api/v3/predictions/prediction-1/result",
            raw_response={"data": {"id": "prediction-1", "status": "created"}},
        )

    async def get_prediction(self, task_id: str) -> WaveSpeedPrediction:
        assert task_id == self.prediction.task_id
        return self.prediction


@pytest.mark.asyncio
async def test_submit_uploads_unique_images_in_order_and_builds_video_payload(
    tmp_path: Path,
) -> None:
    first = _image(tmp_path / "first.png")
    second = _image(tmp_path / "second.jpg")
    third = _image(tmp_path / "product.webp")
    client = FakeWaveSpeedClient()
    adapter = WaveSpeedVideoAdapter(_settings(tmp_path), client=client)  # type: ignore[arg-type]

    result = await adapter.submit(
        VideoGenerationRequest(
            prompt="  keep the subject consistent  ",
            model=None,
            image_paths=(first, second),
            refer_image_paths=(second,),
            product_reference_paths=(third,),
            duration=7,
            aspect_ratio="16:9",
            audio="native",
            multi_shot=False,
        )
    )

    assert client.uploads == [first, second, third]
    assert client.submissions == [
        (
            "kwaivgi/kling-video-o3-pro/reference-to-video",
            {
                "prompt": "keep the subject consistent",
                "images": [
                    "https://cdn.example/first.png",
                    "https://cdn.example/second.jpg",
                    "https://cdn.example/product.webp",
                ],
                "sound": True,
                "aspect_ratio": "16:9",
                "duration": 7,
                "shot_type": "intelligent",
            },
            False,
        )
    ]
    assert result.provider_task_id == "prediction-1"
    assert result.raw_status == "created"
    assert result.provider_model == "kwaivgi/kling-video-o3-pro/reference-to-video"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        ("created", "queued"),
        ("processing", "running"),
        ("completed", "succeeded"),
        ("failed", "failed"),
        ("cancelled", "failed"),
        ("timeout", "failed"),
    ],
)
async def test_query_maps_wavespeed_statuses(
    tmp_path: Path, raw_status: str, expected: str
) -> None:
    client = FakeWaveSpeedClient()
    client.prediction = WaveSpeedPrediction(
        task_id="prediction-1",
        status=raw_status,  # type: ignore[arg-type]
        outputs=("https://cdn.example/video.mp4",) if raw_status == "completed" else (),
        error="provider rejected the request" if raw_status == "failed" else None,
        model_id="kwaivgi/kling-video-o3-pro/reference-to-video",
        raw_response={"data": {"id": "prediction-1", "status": raw_status}},
    )
    adapter = WaveSpeedVideoAdapter(_settings(tmp_path), client=client)  # type: ignore[arg-type]

    result = await adapter.query("prediction-1")

    assert result.status == expected
    assert result.raw_status == raw_status
    assert result.message == ("provider rejected the request" if raw_status == "failed" else None)
    if raw_status == "completed":
        assert result.outputs == (
            ProviderOutput(url="https://cdn.example/video.mp4", content_type="video"),
        )


@pytest.mark.asyncio
async def test_query_rejects_completed_prediction_without_output(tmp_path: Path) -> None:
    client = FakeWaveSpeedClient()
    client.prediction = WaveSpeedPrediction(
        task_id="prediction-1",
        status="completed",
        outputs=(),
        error=None,
        model_id="kwaivgi/kling-video-o3-pro/reference-to-video",
        raw_response={"data": {"id": "prediction-1", "status": "completed"}},
    )
    adapter = WaveSpeedVideoAdapter(_settings(tmp_path), client=client)  # type: ignore[arg-type]

    with pytest.raises(WaveSpeedVideoError) as caught:
        await adapter.query("prediction-1")

    assert caught.value.code == "WAVESPEED_OUTPUT_URL_MISSING"
    assert caught.value.provider_task_id == "prediction-1"
    assert caught.value.raw_status == "completed"


@pytest.mark.asyncio
async def test_submit_translates_wavespeed_failure_without_losing_recovery_metadata(
    tmp_path: Path,
) -> None:
    class FailingClient(FakeWaveSpeedClient):
        async def upload_media(self, source: str | Path | bytes, **kwargs: object) -> str:
            del source, kwargs
            raise WaveSpeedError(
                "WAVESPEED_RATE_LIMITED",
                "submission throttled",
                task_id="possibly-created-task",
                model_id="kwaivgi/kling-video-o3-pro/reference-to-video",
                retryable=True,
                submitted=True,
                uncertain=True,
                details={"status": 429},
            )

    image = _image(tmp_path / "first.png")
    adapter = WaveSpeedVideoAdapter(
        _settings(tmp_path),
        client=FailingClient(),  # type: ignore[arg-type]
    )

    with pytest.raises(WaveSpeedVideoError) as caught:
        await adapter.submit(
            VideoGenerationRequest(prompt="animate", model=None, image_paths=(image,))
        )

    assert caught.value.code == "WAVESPEED_RATE_LIMITED"
    assert caught.value.provider == "wavespeed_video"
    assert caught.value.provider_task_id == "possibly-created-task"
    assert caught.value.retryable is True
    assert caught.value.submitted is True
    assert caught.value.uncertain is True
    assert caught.value.details == {
        "status": 429,
        "modelId": "kwaivgi/kling-video-o3-pro/reference-to-video",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("video_request", "expected_code"),
    [
        (VideoGenerationRequest(prompt="", model=None), "WAVESPEED_INPUT_INVALID"),
        (
            VideoGenerationRequest(prompt="animate", model=None),
            "WAVESPEED_INPUT_INVALID",
        ),
        (
            VideoGenerationRequest(
                prompt="animate",
                model="kwaivgi/kling-video-o3-pro/image-to-video",
                image_paths=(Path("reference.png"),),
            ),
            "WAVESPEED_MODEL_UNSUPPORTED",
        ),
        (
            VideoGenerationRequest(
                prompt="animate",
                model=None,
                image_paths=(Path("reference.png"),),
                duration=16,
            ),
            "WAVESPEED_INPUT_INVALID",
        ),
        (
            VideoGenerationRequest(
                prompt="animate",
                model=None,
                image_paths=(Path("reference.png"),),
                aspect_ratio="4:3",
            ),
            "WAVESPEED_INPUT_INVALID",
        ),
    ],
)
async def test_validate_request_rejects_invalid_inputs_before_upload(
    tmp_path: Path,
    video_request: VideoGenerationRequest,
    expected_code: str,
) -> None:
    adapter = WaveSpeedVideoAdapter(_settings(tmp_path), client=FakeWaveSpeedClient())  # type: ignore[arg-type]

    with pytest.raises(WaveSpeedVideoError) as caught:
        await adapter.validate_request(video_request)

    assert caught.value.code == expected_code


@pytest.mark.asyncio
async def test_validate_request_enforces_image_count_type_and_size(tmp_path: Path) -> None:
    adapter = WaveSpeedVideoAdapter(
        _settings(tmp_path, max_input_image_bytes=1024),
        client=FakeWaveSpeedClient(),  # type: ignore[arg-type]
    )
    too_many = tuple(_image(tmp_path / f"{index}.png", b"x") for index in range(8))

    with pytest.raises(WaveSpeedVideoError) as count_error:
        await adapter.validate_request(
            VideoGenerationRequest(prompt="animate", model=None, image_paths=too_many)
        )
    assert count_error.value.code == "WAVESPEED_IMAGE_INPUT_LIMIT_EXCEEDED"

    unsupported = _image(tmp_path / "reference.gif", b"gif")
    with pytest.raises(WaveSpeedVideoError, match="Unsupported reference image type"):
        await adapter.validate_request(
            VideoGenerationRequest(prompt="animate", model=None, image_paths=(unsupported,))
        )

    oversized = _image(tmp_path / "large.png", b"x" * 1025)
    with pytest.raises(WaveSpeedVideoError, match="configured size limit"):
        await adapter.validate_request(
            VideoGenerationRequest(prompt="animate", model=None, image_paths=(oversized,))
        )


class _MemoryResponse(io.BytesIO):
    status = 200

    def __init__(self, body: bytes, content_type: str = "video/mp4") -> None:
        super().__init__(body)
        self.headers = {"Content-Type": content_type}


@pytest.mark.asyncio
async def test_download_is_atomic_and_reuses_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = b"\x00\x00\x00\x18ftypmp42wavespeed-video"
    calls: list[str] = []

    def fake_urlopen(request: object, *, timeout: float) -> _MemoryResponse:
        del timeout
        calls.append(request.full_url)  # type: ignore[attr-defined]
        return _MemoryResponse(video)

    monkeypatch.setattr("libtv_agent.adapters.wavespeed_video.urlopen", fake_urlopen)
    adapter = WaveSpeedVideoAdapter(_settings(tmp_path), client=FakeWaveSpeedClient())  # type: ignore[arg-type]
    destination = tmp_path / "nested" / "video.mp4"
    output = ProviderOutput(url="https://cdn.example/video.mp4", content_type="video")

    downloaded = await adapter.download(output, destination)
    reused = await adapter.download(output, destination)

    assert downloaded.reused is False
    assert downloaded.size_bytes == len(video)
    assert destination.read_bytes() == video
    assert not destination.with_suffix(".mp4.part").exists()
    assert reused.reused is True
    assert reused.size_bytes == len(video)
    assert calls == ["https://cdn.example/video.mp4"]


@pytest.mark.asyncio
async def test_download_media_is_compatible_with_runner_retry_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = b"\x00\x00\x00\x18ftypmp42wavespeed-video"

    def fake_urlopen(request: object, *, timeout: float) -> _MemoryResponse:
        del request, timeout
        return _MemoryResponse(video)

    monkeypatch.setattr("libtv_agent.adapters.wavespeed_video.urlopen", fake_urlopen)
    adapter = WaveSpeedVideoAdapter(_settings(tmp_path), client=FakeWaveSpeedClient())  # type: ignore[arg-type]
    destination = tmp_path / "runner" / "video.mp4"

    result = await download_with_retries(  # type: ignore[arg-type]
        adapter,
        url="https://cdn.example/video.mp4",
        destination=destination,
    )

    assert result == destination
    assert destination.read_bytes() == video


@pytest.mark.asyncio
async def test_download_replaces_invalid_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = b"\x00\x00\x00\x18ftypmp42wavespeed-video"
    calls: list[str] = []

    def fake_urlopen(request: object, *, timeout: float) -> _MemoryResponse:
        del timeout
        calls.append(request.full_url)  # type: ignore[attr-defined]
        return _MemoryResponse(video)

    monkeypatch.setattr("libtv_agent.adapters.wavespeed_video.urlopen", fake_urlopen)
    adapter = WaveSpeedVideoAdapter(_settings(tmp_path), client=FakeWaveSpeedClient())  # type: ignore[arg-type]
    destination = tmp_path / "video.mp4"
    destination.write_bytes(b"upstream error page")

    downloaded = await adapter.download(
        ProviderOutput(url="https://cdn.example/video.mp4", content_type="video"), destination
    )

    assert downloaded.reused is False
    assert downloaded.size_bytes == len(video)
    assert destination.read_bytes() == video
    assert calls == ["https://cdn.example/video.mp4"]


@pytest.mark.asyncio
async def test_download_rejects_non_video_and_removes_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_urlopen(request: object, *, timeout: float) -> _MemoryResponse:
        del request, timeout
        return _MemoryResponse(b"not-video", "text/html")

    monkeypatch.setattr("libtv_agent.adapters.wavespeed_video.urlopen", fake_urlopen)
    adapter = WaveSpeedVideoAdapter(_settings(tmp_path), client=FakeWaveSpeedClient())  # type: ignore[arg-type]
    destination = tmp_path / "video.mp4"

    with pytest.raises(WaveSpeedVideoError) as caught:
        await adapter.download(
            ProviderOutput(url="https://cdn.example/error", content_type="video"), destination
        )

    assert caught.value.code == "WAVESPEED_DOWNLOAD_FAILED"
    assert caught.value.retryable is True
    assert not destination.exists()
    assert not destination.with_suffix(".mp4.part").exists()
