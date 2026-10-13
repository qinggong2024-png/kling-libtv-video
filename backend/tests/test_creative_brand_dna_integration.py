from __future__ import annotations

import io
import uuid
from copy import deepcopy

import pytest
from libtv_agent.domain.models import CreativeTask
from PIL import Image
from sqlalchemy import select
from test_creative_workflow_text_contract_integration import Flow
from test_creative_workflow_text_contract_integration import workflow as workflow  # noqa: F401


async def create_branded(flow: Flow, **fields):
    data = io.BytesIO()
    Image.new("RGB", (64, 96), "red").save(data, "PNG")
    return await flow.client.post(
        "/api/v1/creative-workflow/tasks", headers=flow.headers,
        data={"product_id": flow.product_id, **fields},
        files={"front": ("front.png", data.getvalue(), "image/png")},
    )


async def profile_for(flow: Flow, profile_id="geeksoutfit"):
    response = await flow.client.get("/api/v1/site-style-profiles", headers=flow.headers)
    assert response.status_code == 200
    return next(item for item in response.json() if item["id"] == profile_id)


@pytest.mark.asyncio
async def test_brand_configuration_is_bound_before_analysis_and_old_packages_do_not_drift(workflow):
    flow = Flow(*workflow)
    await flow.create()
    profile = await profile_for(flow)
    profile.update(
        preferredEnvironment=["bedroom mirror", "vintage bookstore", "night street"],
        audience="Original configured audience",
    )
    saved = await flow.client.put(
        "/api/v1/site-style-profiles/geeksoutfit", headers=flow.headers, json=profile,
    )
    assert saved.status_code == 200, saved.text
    version = saved.json()["version"]
    request = {
        "brand_profile_id": "geeksoutfit", "brand_profile_version": version,
        "client_key": str(uuid.uuid4()),
    }
    created = await create_branded(flow, **request)
    assert created.status_code == 201, created.text
    flow.task_id, flow.version = created.json()["id"], 0
    await flow.command("analyze")
    assert [item["scene"] for item in flow.result["snapshot"]["plan"]["directions"]] == [
        "bedroom mirror", "vintage bookstore", "night street",
    ]
    assert flow.result["snapshot"]["plan"]["evidence"] == "FAKE_NOT_IMAGE_ANALYSIS"
    await flow.command("select_direction", direction_id="B")
    data = deepcopy(flow.result)
    package_id = data["snapshot"]["package"]["package_id"]
    exported = data["creative_packages"][package_id]
    assert exported["audience"] == "Original configured audience"
    assert exported["fieldStatus"]["audience"] == "PROPOSED"
    assert exported["provenance"]["brandDNA"]["profileVersion"] == version
    assert exported["provenance"]["qualified"] is False

    profile = saved.json()
    profile["audience"] = "Changed audience for future tasks"
    profile["status"] = "retired"
    changed = await flow.client.put(
        "/api/v1/site-style-profiles/geeksoutfit", headers=flow.headers, json=profile,
    )
    assert changed.status_code == 200, changed.text
    read = await flow.client.get(
        f"/api/v1/creative-workflow/tasks/{flow.task_id}", headers=flow.headers,
    )
    assert read.json()["creative_packages"] == data["creative_packages"]
    replay = await create_branded(flow, **request)
    assert replay.json()["id"] == flow.task_id
    fresh = await create_branded(flow, brand_profile_id="geeksoutfit")
    assert fresh.status_code == 422


@pytest.mark.asyncio
async def test_unknown_stale_and_unselectable_brand_rejected_before_task_creation(workflow):
    flow = Flow(*workflow)
    await flow.create()
    response = await create_branded(flow, brand_profile_id="does-not-exist")
    assert response.status_code == 422
    response = await create_branded(
        flow, brand_profile_id="geeksoutfit", brand_profile_version="old",
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BRAND_PROFILE_STALE"
    response = await create_branded(flow, brand_profile_version="1.0.0")
    assert response.status_code == 422
    profile = await profile_for(flow)
    profile["status"] = "draft"
    response = await flow.client.put(
        "/api/v1/site-style-profiles/geeksoutfit", headers=flow.headers, json=profile,
    )
    assert response.status_code == 200
    assert (await create_branded(flow, brand_profile_id="geeksoutfit")).status_code == 422


@pytest.mark.asyncio
async def test_brand_hash_tampering_blocks_analysis_and_generic_tasks_remain_supported(workflow):
    flow = Flow(*workflow)
    await flow.create()
    await flow.command("analyze")
    assert flow.result["snapshot"]["plan"]["brand_dna"] is None
    created = await create_branded(flow, brand_profile_id="geeksoutfit")
    flow.task_id, flow.version = created.json()["id"], 0
    async with flow.app.state.database.session_factory() as session:
        task = await session.scalar(select(CreativeTask).where(
            CreativeTask.id == uuid.UUID(flow.task_id),
        ))
        snapshot = deepcopy(task.snapshot_json)
        snapshot["brand_dna"]["audience"] = "tampered"
        task.snapshot_json = snapshot
        await session.commit()
    response = await flow.command("analyze", expected_status=409)
    assert response.json()["detail"]["code"] == "BRAND_DNA_HASH_MISMATCH"
