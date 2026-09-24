import json

from httpx import ASGITransport, AsyncClient
from libtv_agent.domain.models import AuditEvent
from libtv_agent.services.observability import operations_snapshot
from sqlalchemy import select
from test_image_quota_concurrency import post, world  # noqa: F401


async def test_quota_rejection_is_durable_private_and_not_a_replay(world):  # noqa: F811
    app, factory, provider, users = world
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await post(client, users[0], "accepted")).status_code == 201
        assert (await post(client, users[0], "accepted")).status_code == 201
        assert (await post(client, users[0], "private-idempotency-key")).status_code == 429
    async with factory() as session:
        rows = list(await session.scalars(select(AuditEvent)))
        rejected = [row for row in rows if row.action == "IMAGE_QUOTA_REJECTED"]
        assert len(rejected) == 1
        assert rejected[0].actor_id == users[0]
        assert rejected[0].correlation_id != "private-idempotency-key"
        snapshot = await operations_snapshot(session, app.state.settings)
        assert snapshot["metrics"]["imageQuotaRejectionCount"] == 1
        evidence = snapshot["metricEvidence"]["imageQuotaRejectionCount"]
        assert evidence["windowDays"] == 7
        public_metrics = json.dumps({"metrics": snapshot["metrics"], "evidence": evidence})
        assert str(users[0]) not in public_metrics
        assert "private-idempotency-key" not in public_metrics
    assert len(provider.submissions) == 1
