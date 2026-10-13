from __future__ import annotations

import uuid
from copy import deepcopy

import pytest
from libtv_agent.domain.models import CreativeTask
from libtv_agent.services.creative_package_export import with_creative_package_exports
from sqlalchemy import select
from test_creative_workflow_text_contract_integration import Flow, tamper_snapshot
from test_creative_workflow_text_contract_integration import workflow as workflow  # noqa: F401

FIELDS = {
    "direction", "audience", "characterDNA", "sceneDNA", "cameraDNA",
    "imagePrompt", "videoPrompt", "shotPlan", "qualityChecklist",
}


async def read(flow: Flow):
    response = await flow.client.get(
        f"/api/v1/creative-workflow/tasks/{flow.task_id}", headers=flow.headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_exports_require_selection_and_survive_reload_and_command_replay(workflow):
    flow = Flow(*workflow)
    await flow.create()
    assert (await read(flow))["creative_packages"] == {}
    await flow.command("analyze")
    assert flow.result["creative_packages"] == {}
    command = {
        "command_key": str(uuid.uuid4()),
        "expected_version": flow.version,
        "action": "select_direction",
        "direction_id": "B",
    }
    url = f"/api/v1/creative-workflow/tasks/{flow.task_id}/commands"
    first = await flow.client.post(url, headers=flow.headers, json=command)
    replay = await flow.client.post(url, headers=flow.headers, json=command)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    data = first.json()
    package = data["snapshot"]["package"]
    exported = data["creative_packages"][package["package_id"]]
    assert FIELDS <= exported.keys()
    assert exported["imagePrompt"] == package["prompt"]
    assert (await read(flow))["creative_packages"] == data["creative_packages"]
    assert "creative_packages" not in data["snapshot"]
    async with flow.app.state.database.session_factory() as session:
        task = await session.scalar(select(CreativeTask).where(
            CreativeTask.id == uuid.UUID(flow.task_id),
        ))
        assert "creative_packages" not in task.snapshot_json
        assert task.snapshot_json["calls"] == 0


@pytest.mark.asyncio
async def test_export_does_not_modify_snapshot_or_execution_and_preserves_owner_gate(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    before = deepcopy(flow.result)
    decorated = with_creative_package_exports(flow.result)
    assert decorated["snapshot"] == before["snapshot"]
    assert flow.result == before
    assert decorated["creative_package_errors"] == {}
    denied = await flow.client.get(
        f"/api/v1/creative-workflow/tasks/{flow.task_id}",
        headers={"X-User-Id": str(uuid.uuid4())},
    )
    assert denied.status_code in {401, 403, 404}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["prompt", "facts", "locks", "registry", "reality"])
async def test_corrupted_snapshot_never_exports_as_current_valid_package(workflow, kind):
    flow = Flow(*workflow)
    await flow.plan()
    snapshot = await tamper_snapshot(flow, kind)
    data = await read(flow)
    package_id = flow.package["package_id"]
    assert package_id not in data["creative_packages"]
    assert data["creative_package_errors"][package_id] == "CREATIVE_PACKAGE_EXPORT_UNAVAILABLE"
    assert data["snapshot"] == snapshot


def test_legacy_missing_contract_is_readable_but_cannot_export():
    result = {"snapshot": {"package": {"package_id": "legacy-package"}}}
    decorated = with_creative_package_exports(result)
    assert decorated["snapshot"] == result["snapshot"]
    assert decorated["creative_packages"] == {}
    assert decorated["creative_package_errors"]["legacy-package"]
