"""Fresh-process batch confirmation/dispatch crash drill."""

# ruff: noqa: E402

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
ROOT = Path(sys.argv[1]).resolve()
MODE = sys.argv[2]
if MODE not in {"seed", "recover"}:
    raise SystemExit("expected seed or recover")
ROOT.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(SOURCE / "backend/src"), str(SOURCE / "backend/tests")]

from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import ApiIdempotencyRecord, GenerationCommand
from libtv_agent.runner.supervisor import RunnerSupervisor
from sqlalchemy import func, select
from test_workflow_integration import create_analyzed_task, running_app, user_headers

DATABASE_NAME = "batch-dispatch-crash.db"
KEY = "g1-batch-dispatch-crash"


def _settings() -> Settings:
    return Settings(
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{(ROOT / DATABASE_NAME).as_posix()}",
        artifact_root=ROOT / "artifacts",
        runner_root=ROOT / "runner",
        fake_libtv_scenario="success",
        libtv_adapter_mode="fake",
        ai_adapter_mode="fake",
        object_store_mode="local",
        _env_file=None,
    )


async def seed() -> None:
    original = RunnerSupervisor.run_ready

    async def interrupted(self, session):
        record = await session.scalar(
            select(ApiIdempotencyRecord).where(
                ApiIdempotencyRecord.operation_type == "BATCH_CONFIRM",
                ApiIdempotencyRecord.idempotency_key == KEY,
            )
        )
        assert record is not None
        record.created_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()
        (ROOT / "dispatch-entered").write_text("1", encoding="utf-8")
        await asyncio.Event().wait()
        return await original(self, session)

    RunnerSupervisor.run_ready = interrupted
    async with running_app(ROOT, scenario="batch-dispatch-crash") as (client, _app):
        task = await create_analyzed_task(
            client, variants=["STABLE"], client_task_id="batch-dispatch-crash"
        )
        payload = {
            "tasks": [
                {"taskId": task["id"], "expectedStateVersion": task["stateVersion"]},
            ]
        }
        (ROOT / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
        response = await client.post(
            "/api/v1/confirmations/execute",
            headers=user_headers(KEY),
            json=payload,
        )
        assert response.status_code == 200


async def recover() -> None:
    app = create_app(_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            record_count = await client.get("/api/v1/health/live")
            assert record_count.status_code == 200
            async with app.state.database.session_factory() as session:
                command_count = await session.scalar(
                    select(func.count()).select_from(GenerationCommand)
                )
                assert command_count == 1
            payload = json.loads((ROOT / "payload.json").read_text(encoding="utf-8"))
            replay = await client.post(
                "/api/v1/confirmations/execute",
                headers=user_headers(KEY),
                json=payload,
            )
            assert replay.status_code == 200, replay.text
            assert replay.json()["succeededCount"] == 1
            assert app.state.libtv_adapter.run_count == 0
            (ROOT / "result.json").write_text(
                json.dumps(replay.json(), indent=2), encoding="utf-8"
            )


async def main() -> None:
    if MODE == "seed":
        # The payload is written before the worker blocks so the recovery process
        # never needs to infer request identity from unrelated audit rows.
        await seed()
    else:
        await recover()


asyncio.run(main())
