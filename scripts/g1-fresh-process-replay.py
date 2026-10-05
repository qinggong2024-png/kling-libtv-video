"""Fresh-process replay drills for confirmation and confirmation-to-dispatch.

Each mode is run in a separate Python process by the pytest wrapper. The database,
artifacts and object store are isolated below ROOT; no provider or external network
is used.
"""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
ROOT = Path(sys.argv[1]).resolve()
MODE = sys.argv[2]
if MODE not in {"seed-confirm", "replay-confirm", "seed-dispatch", "replay-dispatch"}:
    raise SystemExit(f"unsupported mode: {MODE}")

sys.path[:0] = [str(SOURCE / "backend/src"), str(SOURCE / "backend/tests")]

from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import (
    ApiIdempotencyRecord,
    DownloadArtifact,
    GenerationAttempt,
    GenerationCommand,
    PointsLedger,
    PointsReservation,
)
from sqlalchemy import func, select
from test_workflow_integration import create_analyzed_task, running_app, user_headers

STATE_FILE = ROOT / f"{MODE.split('-', 1)[1]}.json"


def _settings(database_name: str) -> Settings:
    return Settings(
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{(ROOT / database_name).as_posix()}",
        artifact_root=ROOT / "artifacts",
        runner_root=ROOT / "runner",
        fake_libtv_scenario="success",
        libtv_adapter_mode="fake",
        ai_adapter_mode="fake",
        object_store_mode="local",
        _env_file=None,
    )


async def _counts(app) -> dict[str, int]:
    async with app.state.database.session_factory() as session:
        return {
            "attempts": await session.scalar(select(func.count()).select_from(GenerationAttempt)),
            "commands": await session.scalar(select(func.count()).select_from(GenerationCommand)),
            "reservations": await session.scalar(
                select(func.count()).select_from(PointsReservation)
            ),
            "ledger": await session.scalar(select(func.count()).select_from(PointsLedger)),
            "artifacts": await session.scalar(
                select(func.count()).select_from(DownloadArtifact)
            ),
            "idempotency": await session.scalar(
                select(func.count()).select_from(ApiIdempotencyRecord)
            ),
        }


async def _patch_dispatch() -> None:
    async def create_video(path):
        path.write_bytes(b"g1-fresh-process-media")

    async def validate(path, **_kwargs):
        from libtv_agent.services.media import TechnicalValidation

        data = path.read_bytes()
        return TechnicalValidation(
            True,
            (),
            10.0,
            360,
            640,
            False,
            hashlib.sha256(data).hexdigest(),
            len(data),
        )

    import libtv_agent.adapters.libtv as libtv_module
    import libtv_agent.runner.supervisor as supervisor_module

    libtv_module._create_fake_video = create_video
    supervisor_module.technical_validate = validate


async def seed_confirm() -> None:
    async with running_app(ROOT, scenario="fresh-confirm", libtv_mode="fake") as (client, app):
        app.state.settings.auto_run_fake_commands = False
        task = await create_analyzed_task(
            client, variants=["STABLE"], client_task_id="fresh-confirm"
        )
        payload = {"expectedStateVersion": task["stateVersion"], "acceptRisk": True}
        key = "fresh-process-confirm"
        response = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers(key),
            json=payload,
        )
        assert response.status_code == 200, response.text
        state = {
            "task_id": task["id"],
            "payload": payload,
            "key": key,
            "response": response.json(),
            "counts": await _counts(app),
        }
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


async def replay_confirm() -> None:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    app = create_app(_settings("fresh-confirm.db"))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/tasks/{state['task_id']}/confirm",
                headers=user_headers(state["key"]),
                json=state["payload"],
            )
            assert response.status_code == 200, response.text
            assert response.json() == state["response"]
        assert await _counts(app) == state["counts"]
        assert app.state.libtv_adapter.run_count == 0


async def seed_dispatch() -> None:
    await _patch_dispatch()
    async with running_app(ROOT, scenario="fresh-dispatch", libtv_mode="fake") as (client, app):
        task = await create_analyzed_task(
            client, variants=["STABLE"], client_task_id="fresh-dispatch"
        )
        payload = {
            "tasks": [
                {"taskId": task["id"], "expectedStateVersion": task["stateVersion"]},
            ]
        }
        key = "fresh-process-dispatch"
        response = await client.post(
            "/api/v1/confirmations/execute",
            headers=user_headers(key),
            json=payload,
        )
        assert response.status_code == 200, response.text
        assert response.json()["succeededCount"] == 1
        state = {
            "payload": payload,
            "key": key,
            "response": response.json(),
            "counts": await _counts(app),
        }
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


async def replay_dispatch() -> None:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    app = create_app(_settings("fresh-dispatch.db"))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/confirmations/execute",
                headers=user_headers(state["key"]),
                json=state["payload"],
            )
            assert response.status_code == 200, response.text
            assert response.json() == state["response"]
        assert await _counts(app) == state["counts"]
        assert app.state.libtv_adapter.run_count == 0


async def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    await {
        "seed-confirm": seed_confirm,
        "replay-confirm": replay_confirm,
        "seed-dispatch": seed_dispatch,
        "replay-dispatch": replay_dispatch,
    }[MODE]()


asyncio.run(main())
