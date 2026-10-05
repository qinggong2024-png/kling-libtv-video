from datetime import UTC, datetime, timedelta
from uuid import UUID

from libtv_agent.domain.enums import ParentTaskPhase
from libtv_agent.domain.models import ApiIdempotencyRecord, ParentTask
from libtv_agent.services.confirmation_recovery import (
    CONFIRMATION_PROCESS_RESTARTED,
    recover_stale_confirmation_claims,
)
from sqlalchemy import select
from test_workflow_integration import create_analyzed_task, running_app, user_headers


async def test_stale_completed_confirmation_claim_is_replayed(tmp_path):
    async with running_app(tmp_path) as (client, app):
        app.state.settings.auto_run_fake_commands = False
        task = await create_analyzed_task(client, variants=["STABLE"], client_task_id="recovery")
        payload = {"expectedStateVersion": task["stateVersion"], "acceptRisk": True}
        key = "stale-completed-confirm"
        confirmed = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers(key),
            json=payload,
        )
        assert confirmed.status_code == 200, confirmed.text

        async with app.state.database.session_factory() as session:
            record = await session.scalar(
                select(ApiIdempotencyRecord).where(
                    ApiIdempotencyRecord.operation_type == f"CONFIRM_TASK:{task['id']}"
                )
            )
            assert record is not None
            record.response_status = 0
            record.response_body_json = {}
            record.created_at = datetime.now(UTC) - timedelta(hours=1)
            await session.commit()
            result = await recover_stale_confirmation_claims(session, app.state.settings)
            assert result == {"replayed": 1, "reset": 0, "released": 0}

        replay = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers(key),
            json=payload,
        )
        assert replay.status_code == 200
        assert replay.json() == confirmed.json()


async def test_stale_preparing_confirmation_is_recovered_for_manual_retry(tmp_path):
    async with running_app(tmp_path) as (client, app):
        task = await create_analyzed_task(client, variants=["STABLE"], client_task_id="preparing")
        key = "stale-preparing-confirm"

        async with app.state.database.session_factory() as session:
            stored = await session.get(ParentTask, UUID(task["id"]))
            assert stored is not None
            stored.phase = ParentTaskPhase.PREPARING
            stored.state_version += 1
            session.add(
                ApiIdempotencyRecord(
                    tenant_id=str(UUID(task["userId"])),
                    operation_type=f"CONFIRM_TASK:{task['id']}",
                    idempotency_key=key,
                    payload_hash="0" * 64,
                    response_status=0,
                    response_body_json={},
                    created_at=datetime.now(UTC) - timedelta(hours=1),
                    expires_at=datetime.now(UTC) + timedelta(days=90),
                )
            )
            await session.commit()
            result = await recover_stale_confirmation_claims(session, app.state.settings)
            assert result == {"replayed": 0, "reset": 1, "released": 1}
            await session.refresh(stored)
            assert stored.phase == ParentTaskPhase.ACTION_REQUIRED
            assert stored.phase_reason_code == CONFIRMATION_PROCESS_RESTARTED

        async with app.state.database.session_factory() as session:
            assert (
                await session.scalar(
                    select(ApiIdempotencyRecord).where(
                        ApiIdempotencyRecord.idempotency_key == key
                    )
                )
                is None
            )
