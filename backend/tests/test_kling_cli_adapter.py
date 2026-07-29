import json
import time
from pathlib import Path
from typing import Any

import pytest
from libtv_agent.adapters.kling_official_cli import (
    CliProcessResult,
    KlingCliError,
    KlingOfficialCliAdapter,
    map_kling_status,
    parse_cli_json,
)
from libtv_agent.adapters.video_provider import ProviderOutput, VideoGenerationRequest
from libtv_agent.config import Settings


def _envelope(body: dict[str, Any]) -> str:
    return json.dumps({"ok": True, "status": 200, "body": body})


def _identity(*, tail: bool = True) -> dict[str, Any]:
    inputs: list[dict[str, object]] = [{"name": "input", "required": True}]
    if tail:
        inputs.append({"name": "tail_image", "required": False})
    return {
        "user": {"userId": 123},
        "availableModels": {
            "image_to_video": {
                "models": [
                    {
                        "model": "runtime-video-model",
                        "arguments": [
                            {"name": "prompt", "required": True},
                            {"name": "duration", "allowedValues": ["5", "10"]},
                            {"name": "aspect_ratio", "allowedValues": ["9:16", "16:9"]},
                        ],
                        "inputs": inputs,
                    }
                ]
            }
        },
        "authMode": "oauth",
    }


def _settings(tmp_path: Path, **updates: object) -> Settings:
    values: dict[str, object] = {
        "kling_cli_enabled": True,
        "kling_cli_global_qps": 20,
        "kling_cli_capability_cache_seconds": 3600,
        "runner_root": tmp_path / "runner",
        **updates,
    }
    return Settings(_env_file=None, **values)


def _runner(
    calls: list[list[str]],
    *,
    identity: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
):
    identity_body = identity or _identity()
    query_body = query or {
        "generationId": "generation-123",
        "status": "RUNNING",
        "works": [],
    }

    async def run(arguments: list[str], deadline_seconds: float) -> CliProcessResult:
        assert deadline_seconds > 0
        calls.append(arguments)
        if arguments[0] == "--version":
            return CliProcessResult(0, "0.1.3\n", "")
        command = arguments[5]
        body: dict[str, Any]
        if command == "who_am_i":
            body = identity_body
        elif command == "tool_list":
            body = {
                "tools": [
                    {"name": name, "description": "", "inputSchema": {}}
                    for name in (
                        "who_am_i",
                        "image_to_video",
                        "query_tasks",
                        "file_upload",
                    )
                ]
            }
        elif command == "image_to_video":
            body = {
                "generationId": "generation-123",
                "status": "submitted",
                "creditsConsumed": 15,
            }
        elif command == "query_tasks":
            body = query_body
        elif command == "account":
            body = {"membershipType": "VIP", "availableRemainCredits": 100}
        elif command in {"login", "logout"}:
            body = {"authenticated": command == "login"}
        else:
            return CliProcessResult(2, "", "unknown command")
        return CliProcessResult(0, _envelope(body), "")

    return run


def test_parse_cli_json_accepts_last_json_line_and_rejects_invalid() -> None:
    assert parse_cli_json('notice\n{"ok":true,"body":{"value":1}}')["ok"] is True
    with pytest.raises(KlingCliError, match="invalid JSON"):
        parse_cli_json("not json")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("QUEUING", "queued"),
        ("processing", "running"),
        ("COMPLETED", "succeeded"),
        ("PARTIAL_COMPLETED", "partial"),
        ("FAILED", "failed"),
        ("NEW_REMOTE_STATE", "unknown"),
    ],
)
def test_status_mapping(raw: str, expected: str) -> None:
    assert map_kling_status(raw) == expected


@pytest.mark.asyncio
async def test_not_installed_and_not_authenticated_are_explicit(tmp_path: Path) -> None:
    async def missing(arguments: list[str], deadline_seconds: float) -> CliProcessResult:
        del arguments, deadline_seconds
        raise KlingCliError("KLING_CLI_NOT_INSTALLED", "missing")

    adapter = KlingOfficialCliAdapter(_settings(tmp_path), process_runner=missing)
    assert (await adapter.check_availability()).status == "KLING_CLI_NOT_INSTALLED"

    async def logged_out(arguments: list[str], deadline_seconds: float) -> CliProcessResult:
        del deadline_seconds
        if "--version" in arguments:
            return CliProcessResult(0, "0.1.3", "")
        return CliProcessResult(1, "", "Login required")

    adapter = KlingOfficialCliAdapter(_settings(tmp_path), process_runner=logged_out)
    assert (await adapter.check_availability()).status == "KLING_CLI_NOT_AUTHENTICATED"


@pytest.mark.asyncio
async def test_login_and_logout_use_official_cli_and_update_status(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    adapter = KlingOfficialCliAdapter(_settings(tmp_path), process_runner=_runner(calls))

    assert (await adapter.login()).status == "KLING_CLI_READY"
    assert any(len(call) > 5 and call[5] == "login" for call in calls)

    logged_out = await adapter.logout()
    assert logged_out.status == "KLING_CLI_NOT_AUTHENTICATED"
    assert logged_out.authenticated is False
    assert any(len(call) > 5 and call[5] == "logout" for call in calls)


@pytest.mark.asyncio
async def test_submit_uses_argv_and_preserves_special_prompt(tmp_path: Path) -> None:
    image = tmp_path / "含 空格.png"
    image.write_bytes(b"image")
    calls: list[list[str]] = []
    adapter = KlingOfficialCliAdapter(_settings(tmp_path), process_runner=_runner(calls))
    prompt = '中文 "quoted"; $(should-not-run) & more'
    result = await adapter.submit(
        VideoGenerationRequest(
            prompt=prompt,
            model=None,
            image_paths=(image,),
            duration=10,
            aspect_ratio="9:16",
            task_trace_id="a" * 32,
        )
    )
    assert result.provider_task_id == "generation-123"
    submission = next(call for call in calls if "image_to_video" in call)
    assert prompt in submission
    assert submission.count(prompt) == 1
    assert str(image) in submission
    assert result.provider_model == "runtime-video-model"


@pytest.mark.asyncio
async def test_valid_stdout_wins_when_stderr_contains_warning(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    base_runner = _runner(calls)

    async def warning_runner(arguments: list[str], deadline_seconds: float) -> CliProcessResult:
        result = await base_runner(arguments, deadline_seconds)
        if "image_to_video" in arguments:
            return CliProcessResult(result.exit_code, result.stdout, "warning: harmless")
        return result

    image = tmp_path / "one.png"
    image.write_bytes(b"image")
    adapter = KlingOfficialCliAdapter(_settings(tmp_path), process_runner=warning_runner)
    result = await adapter.submit(
        VideoGenerationRequest(
            prompt="animate",
            model=None,
            image_paths=(image,),
            duration=10,
            aspect_ratio="9:16",
        )
    )
    assert result.provider_task_id == "generation-123"


@pytest.mark.asyncio
async def test_multi_storyboard_is_not_silently_dropped(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(b"1")
    second.write_bytes(b"2")
    adapter = KlingOfficialCliAdapter(
        _settings(tmp_path), process_runner=_runner([], identity=_identity(tail=False))
    )
    with pytest.raises(KlingCliError) as captured:
        await adapter.validate_request(
            VideoGenerationRequest(
                prompt="animate",
                model=None,
                image_paths=(first, second),
                duration=10,
                aspect_ratio="9:16",
            )
        )
    assert captured.value.code == "KLING_MULTI_STORYBOARD_UNSUPPORTED"


@pytest.mark.asyncio
async def test_numbered_multi_image_model_passes_every_storyboard(tmp_path: Path) -> None:
    identity = _identity(tail=False)
    model = identity["availableModels"]["image_to_video"]["models"][0]
    model["inputs"] = [{"name": f"image_{index}", "required": index == 1} for index in range(1, 4)]
    paths = tuple(tmp_path / f"{index}.png" for index in range(3))
    for index, path in enumerate(paths):
        path.write_bytes(str(index).encode())
    calls: list[list[str]] = []
    adapter = KlingOfficialCliAdapter(
        _settings(tmp_path), process_runner=_runner(calls, identity=identity)
    )
    await adapter.submit(
        VideoGenerationRequest(
            prompt="依次展示图片1、图片2、图片3",
            model=None,
            image_paths=paths,
            duration=10,
            aspect_ratio="9:16",
        )
    )
    submission = next(call for call in calls if "image_to_video" in call)
    assert submission.count("--image") == 3
    assert "--tailImage" not in submission
    assert all(str(path) in submission for path in paths)


@pytest.mark.asyncio
async def test_query_requires_output_url_on_success(tmp_path: Path) -> None:
    adapter = KlingOfficialCliAdapter(
        _settings(tmp_path),
        process_runner=_runner(
            [],
            query={
                "generationId": "generation-123",
                "status": "COMPLETED",
                "works": [],
            },
        ),
    )
    with pytest.raises(KlingCliError) as captured:
        await adapter.query("generation-123")
    assert captured.value.code == "KLING_OUTPUT_URL_MISSING"


@pytest.mark.asyncio
async def test_download_is_atomic_and_reuses_valid_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        status = 200
        headers = {"Content-Type": "video/mp4"}

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            del size
            if getattr(self, "_read", False):
                return b""
            self._read = True
            return b"video-bytes"

    monkeypatch.setattr(
        "libtv_agent.adapters.kling_official_cli.urlopen",
        lambda request, timeout: Response(),
    )
    adapter = KlingOfficialCliAdapter(_settings(tmp_path), process_runner=_runner([]))
    destination = tmp_path / "output.mp4"
    downloaded = await adapter.download(
        ProviderOutput(url="https://cdn.example/output.mp4"), destination
    )
    assert downloaded.path == destination
    assert destination.read_bytes() == b"video-bytes"
    assert not destination.with_suffix(".mp4.part").exists()
    assert (await adapter.download(ProviderOutput(url="unused"), destination)).reused


@pytest.mark.asyncio
async def test_provider_rate_limit_is_shared_across_calls(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    adapter = KlingOfficialCliAdapter(
        _settings(tmp_path, kling_cli_global_qps=20),
        process_runner=_runner(calls),
    )
    started = time.monotonic()
    await adapter.check_availability()
    elapsed = time.monotonic() - started
    assert elapsed >= 0.045


@pytest.mark.asyncio
async def test_process_error_does_not_expose_stderr_credentials(tmp_path: Path) -> None:
    secret = "ACCESS_TOKEN=should-never-appear"

    async def failure(arguments: list[str], deadline_seconds: float) -> CliProcessResult:
        del deadline_seconds
        if "--version" in arguments:
            return CliProcessResult(0, "0.1.3", "")
        return CliProcessResult(1, "", secret)

    adapter = KlingOfficialCliAdapter(_settings(tmp_path), process_runner=failure)
    availability = await adapter.check_availability()
    assert secret not in (availability.reason or "")
