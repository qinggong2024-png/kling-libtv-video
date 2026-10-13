from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.creative.workflow import Authorization
from libtv_agent.domain.models import Base
from PIL import Image
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
async def workflow(tmp_path: Path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'workflow.db').as_posix()}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    settings = Settings(
        app_env="test", database_url=url, object_store_mode="local",
        artifact_root=tmp_path / "artifacts", runner_root=tmp_path / "runner",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, app, settings


async def create_task(
    client, headers, *, client_key=None, color="red", product_version_id=None, product_id=None,
):
    if product_id is None:
        product = await client.post(
            "/api/v1/products", headers=headers, json={"internalSkuId": str(uuid.uuid4())},
        )
        assert product.status_code == 201, product.text
        product_id = product.json()["id"]
    data = io.BytesIO()
    Image.new("RGB", (64, 96), color).save(data, "PNG")
    response = await client.post(
        "/api/v1/creative-workflow/tasks", headers=headers,
        data={"product_id": product_id, **(
            {"client_key": client_key} if client_key else {}
        ), **(
            {"product_version_id": product_version_id} if product_version_id else {}
        )},
        files={"front": ("front.png", data.getvalue(), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response, product_id


async def command(client, headers, task_id, version, action, **kwargs):
    return await client.post(
        f"/api/v1/creative-workflow/tasks/{task_id}/commands", headers=headers,
        json={"command_key": str(uuid.uuid4()), "expected_version": version,
              "action": action, **kwargs},
    )


async def planned(client, headers):
    response, product_id = await create_task(client, headers)
    task_id = response.json()["id"]
    version = 0
    for action, extra in [
        ("analyze", {}),
        ("select_direction", {"direction_id": "A"}),
    ]:
        response = await command(client, headers, task_id, version, action, **extra)
        assert response.status_code == 200, response.text
        version = response.json()["state_version"]
    return task_id, version, response.json()


@pytest.mark.asyncio
async def test_unknown_reconcile_releases_authorization_and_task_reservations(workflow):
    client, _, settings = workflow
    headers = {"X-User-Id": settings.dev_user_id}
    task_id, version, planned_result = await planned(client, headers)
    package = planned_result["snapshot"]["package"]
    auth = {
        "authorization_id": str(uuid.uuid4()), "package_id": package["package_id"],
        "locks_hash": package["locks_hash"], "expires_at": (
            datetime.now(UTC) + timedelta(hours=1)
        ).isoformat(), "max_calls": 6, "max_cost_micros": 6,
        "total_task_cap_micros": 2,
    }
    response = await command(client, headers, task_id, version, "authorize", authorization=auth)
    version = response.json()["state_version"]
    response = await command(
        client, headers, task_id, version, "generate",
        package_id=package["package_id"], fake_outcome="UNKNOWN",
    )
    version = response.json()["state_version"]
    assert response.json()["snapshot"]["total_cost_micros"] == 2
    response = await command(
        client, headers, task_id, version, "reconcile", reconcile_not_submitted=True,
    )
    assert response.status_code == 200, response.text
    assert response.json()["snapshot"]["cost_micros"] == 0
    assert response.json()["snapshot"]["total_cost_micros"] == 0
    assert response.json()["snapshot"]["execution_state"] == "RECONCILED_NOT_SUBMITTED"
    version = response.json()["state_version"]
    response = await command(
        client, headers, task_id, version, "generate",
        package_id=package["package_id"],
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_zero_task_cap_is_explicit_and_cap_accumulates(workflow):
    client, _, settings = workflow
    headers = {"X-User-Id": settings.dev_user_id}
    task_id, version, planned_result = await planned(client, headers)
    package = planned_result["snapshot"]["package"]
    auth = Authorization(
        authorization_id=str(uuid.uuid4()), package_id=package["package_id"],
        locks_hash=package["locks_hash"],
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        max_calls=6, max_cost_micros=6, total_task_cap_micros=0,
    )
    response = await command(
        client, headers, task_id, version, "authorize", authorization=auth.model_dump(mode="json"),
    )
    assert response.status_code == 200, response.text
    version = response.json()["state_version"]
    response = await command(
        client, headers, task_id, version, "generate", package_id=package["package_id"],
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TASK_BUDGET_EXHAUSTED"


@pytest.mark.asyncio
async def test_stop_survives_reconcile_and_revocation_remains_blocked(workflow):
    client, _, settings = workflow
    headers = {"X-User-Id": settings.dev_user_id}
    task_id, version, planned_result = await planned(client, headers)
    package = planned_result["snapshot"]["package"]
    auth = {
        "authorization_id": str(uuid.uuid4()), "package_id": package["package_id"],
        "locks_hash": package["locks_hash"], "expires_at": (
            datetime.now(UTC) + timedelta(hours=1)
        ).isoformat(), "max_calls": 6, "max_cost_micros": 6,
    }
    response = await command(client, headers, task_id, version, "authorize", authorization=auth)
    version = response.json()["state_version"]
    response = await command(
        client, headers, task_id, version, "generate",
        package_id=package["package_id"], fake_outcome="UNKNOWN",
    )
    version = response.json()["state_version"]
    response = await command(client, headers, task_id, version, "stop")
    version = response.json()["state_version"]
    response = await command(
        client, headers, task_id, version, "revoke_asset",
        reason="withdrawn", impact_scope="all-new-execution",
    )
    assert response.status_code == 200
    version = response.json()["state_version"]
    response = await command(
        client, headers, task_id, version, "reconcile", reconcile_not_submitted=True,
    )
    body = response.json()
    assert body["status"] == "BLOCKED"
    assert body["snapshot"]["stop_reason"] == "USER_STOPPED"
    assert body["snapshot"]["stopped"] is True
    version = body["state_version"]
    response = await command(
        client, headers, task_id, version, "authorize", authorization=auth,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "USER_STOPPED"


@pytest.mark.asyncio
async def test_creation_replay_returns_original_response_after_progress(workflow):
    client, _, settings = workflow
    headers = {"X-User-Id": settings.dev_user_id}
    first, product_id = await create_task(client, headers, client_key="same-create")
    task_id = first.json()["id"]
    response = await command(client, headers, task_id, 0, "analyze")
    assert response.status_code == 200
    data = io.BytesIO()
    Image.new("RGB", (64, 96), "red").save(data, "PNG")
    repeated = await client.post(
        "/api/v1/creative-workflow/tasks", headers=headers,
        data={"product_id": product_id, "client_key": "same-create"},
        files={"front": ("front.png", data.getvalue(), "image/png")},
    )
    assert repeated.status_code == 201
    assert repeated.json() == first.json()


@pytest.mark.asyncio
async def test_plan_uses_product_version_revision_two(workflow):
    client, _, settings = workflow
    headers = {"X-User-Id": settings.dev_user_id}
    first, product_id = await create_task(client, headers)
    version_response = await client.post(
        f"/api/v1/products/{product_id}/versions", headers=headers,
        json={"sourceType": "USER_UPLOAD", "sourceAssetReferences": ["replacement"],
              "truthFields": {"color": "blue"}},
    )
    assert version_response.status_code == 201, version_response.text
    second, _ = await create_task(
        client, headers, product_id=product_id,
        product_version_id=version_response.json()["id"],
    )
    response = await command(client, headers, second.json()["id"], 0, "analyze")
    assert response.status_code == 200, response.text
    plan = response.json()["snapshot"]["plan"]
    assert plan["facts_revision"] == 2
    assert plan["claims"][0]["facts_revision"] == 2
