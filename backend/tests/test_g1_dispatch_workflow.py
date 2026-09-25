import hashlib

from libtv_agent.domain.enums import LedgerEntryType
from libtv_agent.domain.models import GenerationCommand, PointsLedger, PointsReservation
from libtv_agent.services.media import TechnicalValidation
from sqlalchemy import func, select
from test_workflow_integration import create_analyzed_task, running_app, user_headers


async def test_batch_replay_after_dispatch_does_not_generate_or_charge_again(tmp_path, monkeypatch):
    # Media bytes/validation are synthetic; HTTP, runner and ledger are real code.
    async def create_video(path):
        path.write_bytes(b"g1-synthetic-media")

    async def validate(path, **_kwargs):
        data = path.read_bytes()
        return TechnicalValidation(
            True, (), 10.0, 360, 640, False, hashlib.sha256(data).hexdigest(), len(data)
        )

    monkeypatch.setattr("libtv_agent.adapters.libtv._create_fake_video", create_video)
    monkeypatch.setattr("libtv_agent.runner.supervisor.technical_validate", validate)
    async with running_app(tmp_path.parent / "dispatch") as (client, app):
        task = await create_analyzed_task(client, variants=["STABLE"])
        payload = {"tasks": [{"taskId": task["id"], "expectedStateVersion": task["stateVersion"]}]}
        headers = user_headers("dispatch-replay")
        url = "/api/v1/confirmations/execute"
        response = await client.post(url, headers=headers, json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["succeededCount"] == 1
        result = body["results"][0]["task"]
        assert result["variants"][0]["downloadStatus"] == "READY"
        assert app.state.libtv_adapter.run_count == 1
        assert app.state.libtv_adapter.download_count == 1
        replay = await client.post(url, headers=headers, json=payload)
        assert replay.status_code == 200, replay.text
        assert replay.json() == body
        changed = {"tasks": [{**payload["tasks"][0], "acceptRisk": True}]}
        conflict = await client.post(url, headers=headers, json=changed)
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
        assert app.state.libtv_adapter.run_count == 1
        assert app.state.libtv_adapter.download_count == 1
        async with app.state.database.session_factory() as session:
            for model in (GenerationCommand, PointsReservation):
                assert await session.scalar(select(func.count()).select_from(model)) == 1
            entries = list(await session.scalars(select(PointsLedger)))
            assert sorted(entry.entry_type for entry in entries) == sorted(
                [LedgerEntryType.RESERVE, LedgerEntryType.CONSUME]
            )
