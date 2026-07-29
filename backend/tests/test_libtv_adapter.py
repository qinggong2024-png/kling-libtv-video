import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from libtv_agent.adapters import libtv as libtv_module
from libtv_agent.adapters.libtv import (
    FakeLibTVAdapter,
    LibTVError,
    RealLibTVAdapter,
    ReplayLibTVAdapter,
    parse_generation_payload,
    parse_node_snapshot,
)
from libtv_agent.services.generation_safety import PAID_GENERATION_CONFIRMATION
from libtv_agent.services.materialization import _canonicalize_prompt_references, _node_key

FIXTURES = Path(__file__).parent / "fixtures" / "libtv"


def authorized_real_adapter() -> RealLibTVAdapter:
    return RealLibTVAdapter(
        "libtv.exe",
        execution_mode="live",
        paid_generation_enabled=True,
        paid_generation_confirmation=PAID_GENERATION_CONFIRMATION,
        app_env="development",
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"nodeKey": "node-1"}, "node-1"),
        ({"newNodeKey": "node-2"}, "node-2"),
        ({"groupNodeKey": "group-1"}, "group-1"),
    ],
)
def test_materialization_accepts_official_cli_node_identity_shapes(
    payload: dict[str, str],
    expected: str,
) -> None:
    assert _node_key(payload, kind="test") == expected


def test_materialization_compares_cli_canonical_prompt_references() -> None:
    prompt = 'Use {{Node "IMG-task-1-1"}} and {{Node "IMG-task-2-1"}} in order.'

    canonical = _canonicalize_prompt_references(
        prompt,
        [("IMG-task-1-1", "node-1"), ("IMG-task-2-1", "node-2")],
    )

    assert canonical == "Use {{Node node-1}} and {{Node node-2}} in order."


class StubProcess:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout.encode()
        self.stderr = stderr.encode()
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self.stdout, self.stderr


def test_real_adapter_builds_official_blocking_command_without_timeout() -> None:
    adapter = RealLibTVAdapter("libtv.exe")

    command = adapter.build_generation_command(project_uuid="project-1", node="video-node")

    assert command == [
        "libtv.exe",
        "node",
        "video-node",
        "--project",
        "project-1",
        "--run",
    ]
    assert "--timeout" not in command


@pytest.mark.asyncio
async def test_real_adapter_blocks_paid_run_before_starting_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_process = AsyncMock()
    monkeypatch.setattr(libtv_module.asyncio, "create_subprocess_exec", create_process)

    with pytest.raises(LibTVError) as captured:
        await RealLibTVAdapter("libtv.exe").run_generation(
            project_uuid="project-redacted",
            node="video-node-redacted",
            working_directory=tmp_path,
        )

    assert captured.value.code == "PAID_GENERATION_BLOCKED"
    create_process.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_adapter_dry_run_blocks_remote_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_process = AsyncMock()
    monkeypatch.setattr(libtv_module.asyncio, "create_subprocess_exec", create_process)

    with pytest.raises(LibTVError) as captured:
        await RealLibTVAdapter("libtv.exe").create_project("blocked")

    assert captured.value.code == "LIBTV_PREPARATION_BLOCKED"
    create_process.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_only_project_creation_uses_configured_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_process = AsyncMock(return_value=StubProcess(json.dumps({"uuid": "project-created"})))
    monkeypatch.setattr(libtv_module.asyncio, "create_subprocess_exec", create_process)
    adapter = RealLibTVAdapter("libtv.exe", execution_mode="prepare-only", workspace_id="3589110")

    result = await adapter.create_project("中文 画布")

    assert result["uuid"] == "project-created"
    assert create_process.await_args.args == (
        "libtv.exe",
        "project",
        "create",
        "中文 画布",
        "--workspace",
        "3589110",
    )


@pytest.mark.asyncio
async def test_cli_process_uses_hidden_window_creation_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_process = AsyncMock(return_value=StubProcess(json.dumps({"uuid": "project-created"})))
    monkeypatch.setattr(libtv_module.asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(libtv_module, "_hidden_process_creation_flags", lambda: 0x08000000)

    await RealLibTVAdapter(
        "libtv.exe", execution_mode="prepare-only", workspace_id="3589110"
    ).create_project("hidden")

    assert create_process.await_args.kwargs["creationflags"] == 0x08000000


@pytest.mark.asyncio
async def test_prepare_only_project_creation_reuses_matching_remote_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_process = AsyncMock(
        return_value=StubProcess(
            json.dumps({"projectMetaList": [{"uuid": "project-existing", "name": "PROD-existing"}]})
        )
    )
    monkeypatch.setattr(libtv_module.asyncio, "create_subprocess_exec", create_process)
    adapter = RealLibTVAdapter("libtv.exe", execution_mode="prepare-only", workspace_id="3589110")

    result = await adapter.create_project("PROD-existing")

    assert result["uuid"] == "project-existing"
    create_process.assert_awaited_once_with(
        "libtv.exe",
        "project",
        "list",
        "--workspace",
        "3589110",
        cwd=None,
        stdout=libtv_module.asyncio.subprocess.PIPE,
        stderr=libtv_module.asyncio.subprocess.PIPE,
        creationflags=libtv_module._hidden_process_creation_flags(),
    )


@pytest.mark.asyncio
async def test_real_adapter_normalizes_group_node_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_process = AsyncMock(
        return_value=StubProcess(
            json.dumps(
                {
                    "action": "create_empty",
                    "groupNodeKey": "group-node-redacted",
                    "boundNodeKeys": [],
                }
            )
        )
    )
    monkeypatch.setattr(libtv_module.asyncio, "create_subprocess_exec", create_process)
    adapter = RealLibTVAdapter("libtv.exe", execution_mode="prepare-only")

    result = await adapter.create_group(project_uuid="project-redacted", name="group")

    assert result["groupNodeKey"] == "group-node-redacted"
    assert result["nodeKey"] == "group-node-redacted"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["nodeKey", "newNodeKey"])
async def test_real_adapter_normalizes_created_video_node_key(
    field: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_process = AsyncMock(return_value=StubProcess(json.dumps({field: "video-node-redacted"})))
    monkeypatch.setattr(libtv_module.asyncio, "create_subprocess_exec", create_process)
    adapter = RealLibTVAdapter("libtv.exe", execution_mode="prepare-only")

    result = await adapter.create_video_node(
        project_uuid="project-redacted",
        group_node_key="group-redacted",
        name="video",
    )

    assert result["nodeKey"] == "video-node-redacted"


@pytest.mark.asyncio
async def test_fake_adapter_is_offline() -> None:
    result = await FakeLibTVAdapter().run_generation(
        project_uuid="project-1", node="video-node", working_directory=Path(".")
    )
    assert result.status == "SUCCEEDED"


@pytest.mark.asyncio
async def test_replay_adapter_reads_fixture(tmp_path: Path) -> None:
    (tmp_path / "video-node.json").write_text(
        json.dumps({"status": "FAILED", "payload": {"reason": "fixture"}}),
        encoding="utf-8",
    )
    adapter = ReplayLibTVAdapter(tmp_path)

    result = await adapter.run_generation(
        project_uuid="project-1", node="video-node", working_directory=Path(".")
    )

    assert result.status == "FAILED"
    assert result.payload["reason"] == "fixture"


def test_real_node_query_fixture_matches_cli_1_1_1_shape() -> None:
    payload = json.loads((FIXTURES / "node-query-success.json").read_text(encoding="utf-8"))

    node = parse_node_snapshot(payload)
    result = parse_generation_payload(payload)

    assert node["nodeKey"] == "video-node-redacted"
    assert node["inputNodeKeys"] == ["image-node-1", "image-node-2"]
    assert node["taskInfo"]["status"] == 2
    assert node["videoUrl"].endswith("redacted.mp4")
    assert result.status == "SUCCEEDED"
    assert result.payload["taskId"] == "task-redacted"


def test_real_failed_terminal_fixture_is_not_reported_as_unknown() -> None:
    payload = json.loads((FIXTURES / "node-query-failed.json").read_text(encoding="utf-8"))

    result = parse_generation_payload(payload)

    assert result.status == "FAILED"
    assert result.payload["taskId"] == "task-redacted"
    assert result.payload["reason"] == "[REDACTED]"


def test_success_status_without_data_url_is_unknown() -> None:
    payload = json.loads((FIXTURES / "node-query-success.json").read_text(encoding="utf-8"))
    payload["data"]["url"] = []

    assert parse_generation_payload(payload).status == "UNKNOWN"


@pytest.mark.asyncio
async def test_run_generation_parses_blocking_terminal_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout = (FIXTURES / "node-query-success.json").read_text(encoding="utf-8")
    monkeypatch.setattr(
        libtv_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=StubProcess(stdout, "[run] task=task-redacted\n")),
    )

    result = await authorized_real_adapter().run_generation(
        project_uuid="project-redacted", node="video-node-redacted", working_directory=tmp_path
    )

    assert result.status == "SUCCEEDED"
    assert result.payload["videoUrl"].endswith("redacted.mp4")


@pytest.mark.asyncio
async def test_run_generation_returns_terminal_failure_even_with_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout = (FIXTURES / "node-query-failed.json").read_text(encoding="utf-8")
    monkeypatch.setattr(
        libtv_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=StubProcess(stdout, "remote failed", returncode=1)),
    )

    result = await authorized_real_adapter().run_generation(
        project_uuid="project-redacted", node="video-node-redacted", working_directory=tmp_path
    )

    assert result.status == "FAILED"
    assert result.payload["reason"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_json_command_uses_structured_cli_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = {"error": {"code": "NODE_NOT_FOUND", "message": "redacted"}}
    monkeypatch.setattr(
        libtv_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=StubProcess(json.dumps(error), returncode=1)),
    )

    with pytest.raises(LibTVError) as captured:
        await RealLibTVAdapter("libtv.exe").read_node(
            project_uuid="project-redacted", node_key="missing"
        )

    assert captured.value.code == "NODE_NOT_FOUND"
    assert not captured.value.submitted


@pytest.mark.asyncio
async def test_adapter_final_guard_blocks_upper_layer_miscall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_process = AsyncMock()
    monkeypatch.setattr(libtv_module.asyncio, "create_subprocess_exec", create_process)
    adapter = RealLibTVAdapter(
        "libtv.exe",
        execution_mode="live",
        paid_generation_enabled=True,
        paid_generation_confirmation="wrong confirmation",
    )

    with pytest.raises(LibTVError) as captured:
        await adapter.run_generation(
            project_uuid="project", node="node", working_directory=tmp_path
        )

    assert captured.value.code == "PAID_GENERATION_BLOCKED"
    create_process.assert_not_awaited()


@pytest.mark.parametrize("status", [0, 1, "QUEUED", "PROCESSING"])
def test_non_terminal_generation_states_remain_unknown(status: object) -> None:
    result = parse_generation_payload({"data": {"taskInfo": {"status": status}}})

    assert result.status == "UNKNOWN"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (
            {"error": {"code": "LOGIN_REQUIRED", "message": "login expired"}},
            "LIBTV_AUTH_REQUIRED",
        ),
        ({"error": {"code": "PARAM_INVALID", "message": "bad parameter"}}, "PARAM_INVALID"),
    ],
)
async def test_cli_login_and_parameter_errors_are_structured(
    error: dict[str, object],
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        libtv_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=StubProcess(json.dumps(error), returncode=1)),
    )

    with pytest.raises(LibTVError) as captured:
        await RealLibTVAdapter("libtv.exe").read_node(project_uuid="project", node_key="node")

    assert captured.value.code == expected_code
    assert not captured.value.submitted


@pytest.mark.asyncio
async def test_cli_401_stderr_is_normalized_and_uses_shared_config_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_process = AsyncMock(return_value=StubProcess("", "接口错误 [401]: 未登录", returncode=1))
    monkeypatch.setattr(libtv_module.asyncio, "create_subprocess_exec", create_process)
    config_dir = tmp_path / "shared-libtv"

    with pytest.raises(LibTVError) as captured:
        await RealLibTVAdapter("libtv.exe", config_dir=config_dir).check_account()

    assert captured.value.code == "LIBTV_AUTH_REQUIRED"
    assert not captured.value.submitted
    assert create_process.await_args.args == ("libtv.exe", "account", "info")
    assert create_process.await_args.kwargs["env"]["LIBTV_CONFIG_DIR"] == str(config_dir.resolve())
