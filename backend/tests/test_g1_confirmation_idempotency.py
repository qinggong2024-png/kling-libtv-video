import asyncio

from libtv_agent.domain.models import (
    ApiIdempotencyRecord,
    GenerationAttempt,
    GenerationCommand,
    PointsReservation,
)
from sqlalchemy import func, select
from test_workflow_integration import create_analyzed_task, running_app, user_headers


async def test_confirmation_concurrent_replay_conflict_reserves_once(tmp_path):
    async with running_app(tmp_path) as (client, app):
        app.state.settings.auto_run_fake_commands = False
        task = await create_analyzed_task(client, variants=["STABLE"])
        url = f"/api/v1/tasks/{task['id']}/confirm"
        payload = {"expectedStateVersion": task["stateVersion"], "acceptRisk": True}
        headers = user_headers("confirm-concurrent")
        responses = await asyncio.gather(
            *[client.post(url, headers=headers, json=payload) for _ in range(2)]
        )
        assert [r.status_code for r in responses] == [200, 200], [
            r.text for r in responses
        ]
        assert responses[0].json() == responses[1].json()
        replay = await client.post(url, headers=headers, json=payload)
        assert replay.status_code == 200
        assert replay.json() == responses[0].json()
        conflict = await client.post(
            url, headers=headers, json={**payload, "acceptRisk": False}
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
        async with app.state.database.session_factory() as session:
            for model in (GenerationAttempt, GenerationCommand, PointsReservation):
                assert await session.scalar(select(func.count()).select_from(model)) == 1
            count = await session.scalar(
                select(func.count()).select_from(ApiIdempotencyRecord).where(
                    ApiIdempotencyRecord.operation_type == f"CONFIRM_TASK:{task['id']}"
                )
            )
            assert count == 1
        assert app.state.libtv_adapter.run_count == 0
