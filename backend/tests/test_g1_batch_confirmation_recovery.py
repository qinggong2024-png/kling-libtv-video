import hashlib
from datetime import UTC, datetime, timedelta

from libtv_agent.domain.models import ApiIdempotencyRecord
from libtv_agent.services.confirmation_recovery import (
    recover_stale_batch_confirmation_claims,
)
from libtv_agent.services.media import TechnicalValidation
from sqlalchemy import select
from test_workflow_integration import create_analyzed_task, running_app, user_headers


async def test_stale_batch_confirmation_claim_reconstructs_response(tmp_path, monkeypatch):
    async def create_video(path):
        path.write_bytes(b"batch-confirmation-recovery")

    async def validate(path, **_kwargs):
        data = path.read_bytes()
        return TechnicalValidation(
            True, (), 10.0, 360, 640, False, hashlib.sha256(data).hexdigest(), len(data)
        )

    monkeypatch.setattr("libtv_agent.adapters.libtv._create_fake_video", create_video)
    monkeypatch.setattr("libtv_agent.runner.supervisor.technical_validate", validate)
    async with running_app(tmp_path / "batch-recovery") as (client, app):
        task = await create_analyzed_task(client, variants=["STABLE"])
        payload = {
            "tasks": [
                {"taskId": task["id"], "expectedStateVersion": task["stateVersion"]},
            ]
        }
        key = "batch-confirmation-recovery"
        original = await client.post(
            "/api/v1/confirmations/execute",
            headers=user_headers(key),
            json=payload,
        )
        assert original.status_code == 200

        async with app.state.database.session_factory() as session:
            record = await session.scalar(
                select(ApiIdempotencyRecord).where(
                    ApiIdempotencyRecord.operation_type == "BATCH_CONFIRM",
                    ApiIdempotencyRecord.idempotency_key == key,
                )
            )
            assert record is not None
            record.response_status = 0
            record.response_body_json = {"_requestPayload": payload}
            record.created_at = datetime.now(UTC) - timedelta(hours=1)
            await session.commit()
            recovered = await recover_stale_batch_confirmation_claims(
                session, app.state.settings
            )
            assert recovered == {"replayed": 1, "released": 0}
            await session.refresh(record)
            assert record.response_status == 200
            assert record.response_body_json == original.json()

        replay = await client.post(
            "/api/v1/confirmations/execute",
            headers=user_headers(key),
            json=payload,
        )
        assert replay.status_code == 200
        assert replay.json() == original.json()
