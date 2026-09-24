import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.models import (
    ApiIdempotencyRecord,
    AuditEvent,
    Base,
    ImageGenerationBatch,
    ParentTask,
    User,
)
from sqlalchemy import func, select


@pytest.fixture
async def recovery_app():
    app = create_app(Settings(
        app_env="test", database_url="sqlite+aiosqlite:///:memory:", _env_file=None
    ))
    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with app.state.database.session_factory() as session:
            session.add_all([
                User(id=uuid.UUID(app.state.settings.dev_user_id), username="owner",
                     password_hash="disabled"),
                User(id=uuid.UUID(app.state.settings.dev_admin_id), username="other",
                     password_hash="disabled"),
            ])
            await session.commit()
        yield app


async def query(app, payload, user_id=None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/api/v1/submission-recovery/query", json=payload,
            headers={"X-User-Id": user_id or app.state.settings.dev_user_id},
        )


@pytest.mark.asyncio
async def test_unknown_lookup_is_audited_and_never_allows_retry(recovery_app):
    response = await query(recovery_app, {"kind": "video", "clientId": "lost-response"})
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "not_found"
    assert body["retryAllowed"] is False
    assert body["requiresAdminReview"] is True
    async with recovery_app.state.database.session_factory() as session:
        audit = await session.get(AuditEvent, uuid.UUID(body["auditId"]))
        assert audit.action == "SUBMISSION_RECOVERY_QUERY"
        assert audit.entity_id != "lost-response"
        assert await session.scalar(select(func.count()).select_from(ParentTask)) == 0
        assert await session.scalar(select(func.count()).select_from(ApiIdempotencyRecord)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("settled", [False, True])
async def test_video_recovery_is_owner_scoped_and_redacted(recovery_app, settled):
    app = recovery_app
    task_id = uuid.uuid4()
    async with app.state.database.session_factory() as session:
        if settled:
            session.add(ParentTask(
                id=task_id, user_id=uuid.UUID(app.state.settings.dev_user_id),
                client_task_id="client-group", title="secret title", asset_count=0,
                state_version=7,
            ))
        session.add(ApiIdempotencyRecord(
            tenant_id=app.state.settings.dev_user_id, operation_type="CREATE_FIXED_VIDEO_TASK",
            idempotency_key="stable-key", payload_hash="a" * 64,
            response_status=201 if settled else 0,
            response_body_json={"id": str(task_id), "secret": "https://secret.example/token"},
            expires_at=datetime.now(UTC) + timedelta(days=90),
        ))
        await session.commit()
    payload = {"kind": "video", "idempotencyKey": "stable-key"}
    response = await query(app, payload)
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == ("submitted" if settled else "in_progress")
    assert body["stateVersion"] == (7 if settled else None)
    assert "secret" not in response.text
    assert "stable-key" not in response.text
    other = await query(app, payload, app.state.settings.dev_admin_id)
    assert other.json()["state"] == "not_found"
    assert other.json()["resourceId"] is None


@pytest.mark.asyncio
async def test_image_recovery_requires_unambiguous_identity(recovery_app):
    app = recovery_app
    batch_ids = [uuid.uuid4(), uuid.uuid4()]
    async with app.state.database.session_factory() as session:
        for index, batch_id in enumerate(batch_ids):
            session.add(ImageGenerationBatch(
                id=batch_id, user_id=uuid.UUID(app.state.settings.dev_user_id),
                client_batch_id="same-client-id", idempotency_key=f"key-{index}",
                request_hash="b" * 64, name="private name", provider="gpt",
                expected_generation_count=1, paid_submission_consent_at=datetime.now(UTC),
                request_json={"prompt": "private prompt"},
            ))
        await session.commit()
    payload = {"kind": "image", "clientId": "same-client-id"}
    ambiguous = await query(app, payload)
    assert ambiguous.json()["state"] == "unknown"
    found = await query(app, {**payload, "idempotencyKey": "key-0"})
    assert found.json()["state"] == "submitted"
    assert found.json()["resourceId"] == str(batch_ids[0])
    assert "private" not in found.text
    other = await query(app, payload, app.state.settings.dev_admin_id)
    assert other.json()["state"] == "not_found"


@pytest.mark.asyncio
async def test_recovery_requires_authentication_and_an_identity(recovery_app):
    app = recovery_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthenticated = await client.post(
            "/api/v1/submission-recovery/query", json={"kind": "video", "clientId": "x"}
        )
    assert unauthenticated.status_code == 401
    invalid = await query(app, {"kind": "video"})
    assert invalid.status_code == 422
