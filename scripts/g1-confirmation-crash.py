# ruff: noqa: E402

"""Fresh-process confirmation interruption drill.

The first worker persists PREPARING and then stops before materialization and the
confirmation version can commit.  A fresh worker must make the task explicitly
actionable and release the abandoned idempotency claim without starting work.
"""

import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path
from uuid import UUID

SOURCE = Path(__file__).resolve().parents[1]
ROOT = Path(sys.argv[1]).resolve()
MODE = sys.argv[2]
if MODE not in {"seed", "recover"}:
    raise SystemExit("expected seed or recover")
ROOT.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(SOURCE / "backend/src"), str(SOURCE / "backend/tests")]

from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import ParentTaskPhase
from libtv_agent.domain.models import ApiIdempotencyRecord, ParentTask
from libtv_agent.services.confirmation import confirm_task
from libtv_agent.services.confirmation_recovery import recover_stale_confirmation_claims
from libtv_agent.services.idempotency import load_idempotent_response
from sqlalchemy import select
from test_workflow_integration import create_analyzed_task, running_app

USER_ID = "00000000-0000-0000-0000-000000000001"
KEY = "g1-confirmation-crash"
DATABASE_NAME = "confirmation-crash.db"


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
    async with running_app(ROOT, scenario="confirmation-crash") as (client, app):
        task_json = await create_analyzed_task(
            client, variants=["STABLE"], client_task_id="confirmation-crash"
        )
        payload = {"expectedStateVersion": task_json["stateVersion"], "acceptRisk": True}
        async with app.state.database.session_factory() as session:
            await load_idempotent_response(
                session,
                tenant_id=USER_ID,
                operation_type=f"CONFIRM_TASK:{task_json['id']}",
                key=KEY,
                payload=payload,
            )
            await session.commit()
            task = await session.get(ParentTask, UUID(task_json["id"]))
            assert task is not None

            def reached_preparing() -> None:
                (ROOT / "preparing").write_text(
                    json.dumps({"task_id": task_json["id"]}), encoding="utf-8"
                )

            await confirm_task(
                session,
                app.state.libtv_adapter,
                app.state.object_store,
                task,
                task.user_id,
                app.state.settings,
                accept_risk=True,
                expected_state_version=task.state_version,
                on_preparing=reached_preparing,
            )


async def recover() -> None:
    app = create_app(_settings())
    async with app.router.lifespan_context(app):
        async with app.state.database.session_factory() as session:
            result = await recover_stale_confirmation_claims(
                session, app.state.settings, older_than=timedelta(seconds=0)
            )
            assert result == {"replayed": 0, "reset": 1, "released": 1}
            task = await session.scalar(select(ParentTask))
            assert task is not None
            assert task.phase == ParentTaskPhase.ACTION_REQUIRED
            assert task.phase_reason_code == "CONFIRMATION_PROCESS_RESTARTED"
            task_id = task.id
            claim = await session.scalar(
                select(ApiIdempotencyRecord).where(
                    ApiIdempotencyRecord.operation_type == f"CONFIRM_TASK:{task_id}"
                )
            )
            assert claim is None
            (ROOT / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


asyncio.run(seed() if MODE == "seed" else recover())
