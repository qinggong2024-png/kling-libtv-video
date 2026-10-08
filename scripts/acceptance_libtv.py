from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import os
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))

from libtv_agent.app import create_app  # noqa: E402
from libtv_agent.config import Settings  # noqa: E402
from libtv_agent.domain.enums import CommandStatus  # noqa: E402
from libtv_agent.domain.models import (  # noqa: E402
    Base,
    GenerationAttempt,
    GenerationCommand,
    GenerationVariant,
)
from libtv_agent.runner.supervisor import RunnerSupervisor  # noqa: E402
from libtv_agent.services.generation_safety import (  # noqa: E402
    PAID_GENERATION_CONFIRMATION,
)
from libtv_agent.services.runtime_control import (  # noqa: E402
    get_runtime_config,
    update_runtime_config,
)
from sqlalchemy import select  # noqa: E402

STATE_ROOT = PROJECT_ROOT / "var" / "acceptance"
STATE_PATH = STATE_ROOT / "state.json"
LOCK_PATH = STATE_ROOT / "operation.lock"
DATABASE_PATH = STATE_ROOT / "acceptance.sqlite3"
USER_ID = "00000000-0000-0000-0000-000000000001"
WORKSPACE_ID = "3744766"
OUTPUT_ROOT = Path("F:/LibTV-Outputs/20260727-libtv-acceptance")


def _try_lock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _exclusive_acceptance_lock() -> Iterator[None]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        try:
            _try_lock(handle)
        except OSError as exc:
            raise RuntimeError(
                "another LibTV acceptance process is active; wait for it to finish"
            ) from exc
        try:
            yield
        finally:
            _unlock(handle)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _settings(*, live: bool, set_id: str, offline: bool = False) -> Settings:
    return Settings(
        app_env="development",
        database_url=f"sqlite+aiosqlite:///{DATABASE_PATH.as_posix()}",
        object_store_mode="local",
        artifact_root=STATE_ROOT / "artifacts",
        runner_root=(
            STATE_ROOT / "offline-outputs" / f"set-{set_id}"
            if offline
            else OUTPUT_ROOT / f"set-{set_id}"
        ),
        libtv_adapter_mode="replay" if offline else "real",
        libtv_execution_mode="dry-run" if offline else ("live" if live else "prepare-only"),
        paid_generation_enabled=live,
        paid_generation_confirmation=PAID_GENERATION_CONFIRMATION if live else "",
        paid_submissions_paused=not live,
        global_paused=False,
        generation_same_project=2,
        generation_per_user=2,
        generation_global=2,
        prepared_queue_low_watermark=2,
        prepared_queue_high_watermark=4,
        libtv_workspace_id=WORKSPACE_ID,
        ai_adapter_mode="fake",
        auto_run_fake_commands=False,
        _env_file=None,
    )


async def _read_state() -> dict[str, Any]:
    if not await asyncio.to_thread(STATE_PATH.is_file):
        return {"schemaVersion": "1.0", "paidTestsUsed": 0, "sets": {}}
    text = await asyncio.to_thread(STATE_PATH.read_text, encoding="utf-8")
    return json.loads(text)


async def _write_state(state: dict[str, Any]) -> None:
    await asyncio.to_thread(STATE_ROOT.mkdir, parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(f".json.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)
    await asyncio.to_thread(temporary.write_text, payload, encoding="utf-8")
    await asyncio.to_thread(temporary.replace, STATE_PATH)


async def _ensure_schema(app: Any) -> None:
    await asyncio.to_thread(STATE_ROOT.mkdir, parents=True, exist_ok=True)
    async with app.state.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _headers(key: str | None = None) -> dict[str, str]:
    headers = {"X-User-Id": USER_ID}
    if key:
        headers["Idempotency-Key"] = key
    return headers


async def prepare(args: argparse.Namespace) -> int:
    state = await _read_state()
    existing = state["sets"].get(args.set_id)
    if existing:
        print(json.dumps(existing, ensure_ascii=False, indent=2))
        return 0
    input_paths = [await asyncio.to_thread(Path(value).resolve) for value in args.image]
    missing = [str(path) for path in input_paths if not await asyncio.to_thread(path.is_file)]
    if missing:
        raise ValueError(f"input files are missing: {missing}")
    settings = _settings(live=False, set_id=args.set_id, offline=args.offline)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        await _ensure_schema(app)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://acceptance"
        ) as client:
            uploads = []
            for index, path in enumerate(input_paths, start=1):
                content = await asyncio.to_thread(path.read_bytes)
                media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                response = await client.post(
                    "/api/v1/uploads",
                    headers=_headers(f"acceptance-{args.set_id}-upload-{index}"),
                    files={"file": (path.name, content, media_type)},
                )
                response.raise_for_status()
                uploads.append(response.json())
            created = await client.post(
                "/api/v1/tasks",
                headers=_headers(f"acceptance-{args.set_id}-create"),
                json={
                    "clientTaskId": f"paid-acceptance-{args.set_id}",
                    "title": args.title,
                    "storyboards": [
                        {"uploadId": item["id"], "order": index, "required": True}
                        for index, item in enumerate(uploads, start=1)
                    ],
                    "userRequirement": args.requirement,
                    "variants": ["STABLE", "DYNAMIC"],
                },
            )
            created.raise_for_status()
            task = created.json()
            analyzed = await client.post(
                f"/api/v1/tasks/{task['id']}/analyze",
                headers=_headers(f"acceptance-{args.set_id}-analyze"),
                json={"expectedStateVersion": task["stateVersion"]},
            )
            analyzed.raise_for_status()
            task = analyzed.json()
            confirmed = await client.post(
                f"/api/v1/tasks/{task['id']}/confirm",
                headers=_headers(f"acceptance-{args.set_id}-prepare"),
                json={"expectedStateVersion": task["stateVersion"]},
            )
            confirmed.raise_for_status()
            task = confirmed.json()
            preview = await client.get(
                f"/api/v1/tasks/{task['id']}/generation-preview", headers=_headers()
            )
            preview.raise_for_status()
    commands = preview.json()["commands"]
    if task["phase"] != "WAITING_FOR_SEAL" or len(commands) != 2:
        raise RuntimeError("prepare-only did not stop with exactly two reviewed commands")
    record = {
        "setId": args.set_id,
        "taskId": task["id"],
        "title": args.title,
        "inputFiles": [str(path) for path in input_paths],
        "preparedAt": _now(),
        "phase": task["phase"],
        "previewFile": preview.json()["previewFile"],
        "outputRoot": str(settings.runner_root),
        "commands": commands,
        "paidExecutionStarted": False,
        "offline": args.offline,
    }
    state["sets"][args.set_id] = record
    await _write_state(state)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


async def _pause_submissions(app: Any, reason: str) -> None:
    async with app.state.database.session_factory() as session:
        current = await get_runtime_config(session, app.state.settings)
        if current is None or current.config_json["paidSubmissionsPaused"]:
            return
        config = deepcopy(current.config_json)
        config["paidSubmissionsPaused"] = True
        await update_runtime_config(
            session,
            app.state.settings,
            config=config,
            actor_id=None,
            reason=reason,
            expected_version=current.version,
        )
        await session.commit()


async def execute(args: argparse.Namespace) -> int:
    if not args.execute_paid or args.confirmation != PAID_GENERATION_CONFIRMATION:
        raise ValueError("paid execution requires --execute-paid and the exact confirmation phrase")
    state = await _read_state()
    record = state["sets"].get(args.set_id)
    if not record:
        raise ValueError("the requested set has not completed prepare-only")
    if record.get("paidExecutionStarted"):
        raise ValueError("this product set has already consumed its one allowed paid test")
    if int(state.get("paidTestsUsed", 0)) >= 2:
        raise ValueError("the two-test paid acceptance budget is exhausted")
    settings = _settings(live=True, set_id=args.set_id)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        await _ensure_schema(app)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://acceptance"
        ) as client:
            task_response = await client.get(
                f"/api/v1/tasks/{record['taskId']}", headers=_headers()
            )
            task_response.raise_for_status()
            task = task_response.json()
            confirmed = await client.post(
                f"/api/v1/tasks/{task['id']}/confirm",
                headers=_headers(f"acceptance-{args.set_id}-paid-dispatch"),
                json={"expectedStateVersion": task["stateVersion"]},
            )
            confirmed.raise_for_status()

        record["paidExecutionStarted"] = True
        record["paidExecutionStartedAt"] = _now()
        record["phase"] = confirmed.json()["phase"]
        state["paidTestsUsed"] = int(state.get("paidTestsUsed", 0)) + 1
        await _write_state(state)

        supervisor = RunnerSupervisor(
            app.state.libtv_adapter,
            app.state.object_store,
            settings,
            owner=f"acceptance-set-{args.set_id}",
        )
        try:
            async with app.state.database.session_factory() as session:
                launched = await supervisor.run_ready(session)
            print(json.dumps({"event": "paid-boundary-launched", "commands": launched}))
            if launched != 2:
                raise RuntimeError(f"expected two A/B launches, observed {launched}")
            while True:
                async with app.state.database.session_factory() as session:
                    await supervisor.observe_command_hosts(session)
                    rows = list(
                        await session.execute(
                            select(GenerationCommand, GenerationAttempt, GenerationVariant)
                            .join(
                                GenerationAttempt,
                                GenerationAttempt.id == GenerationCommand.attempt_id,
                            )
                            .join(
                                GenerationVariant,
                                GenerationVariant.id == GenerationAttempt.variant_id,
                            )
                            .where(GenerationVariant.parent_task_id == uuid.UUID(record["taskId"]))
                        )
                    )
                progress = [
                    {
                        "variant": variant.variant_type.value,
                        "commandStatus": command.status.value,
                        "attemptStatus": attempt.status.value,
                        "taskId": attempt.task_id,
                        "errorCode": attempt.last_error_code,
                    }
                    for command, attempt, variant in rows
                ]
                print(json.dumps({"event": "progress", "items": progress}), flush=True)
                terminal = {
                    CommandStatus.TERMINAL.value,
                    CommandStatus.UNCERTAIN.value,
                    CommandStatus.CANCELLED.value,
                }
                if len(progress) == 2 and all(
                    item["commandStatus"] in terminal for item in progress
                ):
                    record["completedAt"] = _now()
                    record["results"] = progress
                    record["phase"] = "TERMINAL"
                    await _write_state(state)
                    return (
                        0 if all(item["attemptStatus"] == "SUCCEEDED" for item in progress) else 1
                    )
                await asyncio.sleep(10)
        finally:
            await _pause_submissions(app, f"acceptance set {args.set_id} completed or stopped")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Two-stage LibTV paid acceptance harness")
    subparsers = parser.add_subparsers(dest="action", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--set-id", choices=["1", "2"], required=True)
    prepare_parser.add_argument("--title", required=True)
    prepare_parser.add_argument("--requirement", default="")
    prepare_parser.add_argument("--image", action="append", required=True)
    prepare_parser.add_argument(
        "--offline",
        action="store_true",
        help="use Replay/Fake and local isolated paths; never contact LibTV",
    )
    execute_parser = subparsers.add_parser("execute")
    execute_parser.add_argument("--set-id", choices=["1", "2"], required=True)
    execute_parser.add_argument("--execute-paid", action="store_true")
    execute_parser.add_argument("--confirmation", default="")
    return parser


async def async_main() -> int:
    args = build_parser().parse_args()
    with _exclusive_acceptance_lock():
        return await (prepare(args) if args.action == "prepare" else execute(args))


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(async_main()))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc
