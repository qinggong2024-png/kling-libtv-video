from __future__ import annotations

import builtins
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from libtv_agent.api import controlled_image_bridge as api
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.models import User
from libtv_agent.services import creative_provider_preflight as preflight_service
from libtv_agent.services.controlled_image_bridge import (
    ControlledImageBridgeBinding,
    ControlledImageBridgePolicy,
    ControlledImageBridgeRejected,
    preflight_controlled_image_bridge,
)
from sqlalchemy import update
from test_creative_provider_preflight import _prepared, _save_approval
from test_creative_provider_requests import _counts
from test_creative_provider_requests import workflow as workflow


@pytest.fixture
async def bridge(workflow, tmp_path):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, "image")
    binding = ControlledImageBridgeBinding(
        options=request.options,
        capability=inputs["capability"],
        approval_manifest_path=inputs["approval_manifest_path"],
    )
    policy = ControlledImageBridgePolicy(enabled=True, bindings={task.id: binding})
    return flow, task, request, approval, inputs, policy


async def _preflight(bridge, **overrides):
    flow, task, _, _, inputs, policy = bridge
    kwargs = {
        "task_id": task.id,
        "owner_id": inputs["owner_id"],
        "expected_version": task.state_version,
        "policy": policy,
        "object_store": inputs["object_store"],
        "settings": inputs["settings"],
    }
    kwargs.update(overrides)
    async with flow.app.state.database.session_factory() as session:
        return await preflight_controlled_image_bridge(session, **kwargs)


def _url(task):
    return f"/api/v1/creative-production-bridge/tasks/{task.id}/preflight"


@pytest.mark.parametrize("policy", [None, ControlledImageBridgePolicy()])
async def test_policy_is_closed_by_default(bridge, policy):
    with pytest.raises(ControlledImageBridgeRejected, match="CONTROLLED_BRIDGE_DISABLED"):
        await _preflight(bridge, policy=policy)


async def test_policy_copies_bindings_and_requires_explicit_task_binding(bridge):
    _, task, _, _, _, policy = bridge
    bindings = dict(policy.bindings)
    copied = ControlledImageBridgePolicy(enabled=True, bindings=bindings)
    bindings.clear()
    assert task.id in copied.bindings
    with pytest.raises(TypeError):
        copied.bindings[task.id] = policy.bindings[task.id]
    with pytest.raises(ControlledImageBridgeRejected, match="CONTROLLED_BRIDGE_BINDING_REQUIRED"):
        await _preflight(bridge, policy=ControlledImageBridgePolicy(enabled=True))


async def test_owner_and_version_are_checked_before_reading_approval(bridge):
    with pytest.raises(ControlledImageBridgeRejected, match="CREATIVE_TASK_NOT_FOUND"):
        await _preflight(bridge, owner_id=uuid.uuid4())
    with pytest.raises(ControlledImageBridgeRejected, match="STALE_VERSION"):
        await _preflight(bridge, expected_version=0)


async def test_preflight_reuses_production_validation_without_mutations_or_provider(
    bridge, monkeypatch
):
    flow, task, request, _, _, _ = bridge

    def forbidden(*args, **kwargs):
        raise AssertionError("preflight must not submit, reserve, admit or execute")

    for target in (
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.upload_media",
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.submit_prediction",
        "libtv_agent.services.image_generations.submit_batch",
        "libtv_agent.services.image_quota.reserve_image_quota",
        "libtv_agent.services.points.reserve_points",
        "libtv_agent.services.points.settle_points",
        "libtv_agent.services.creative_provider_submission_persistence."
        "admit_provider_submission_durable",
        "libtv_agent.services.creative_image_workflow_orchestrator.execute_creative_image_workflow",
    ):
        monkeypatch.setattr(target, forbidden)
    leases = []
    original = preflight_service.preflight_creative_provider_request

    async def capture(*args, **kwargs):
        lease = await original(*args, **kwargs)
        leases.append(lease)
        assert lease.result.manifest_path.exists()
        return lease

    monkeypatch.setattr(preflight_service, "preflight_creative_provider_request", capture)
    async with flow.app.state.database.session_factory() as session:
        before = await _counts(session)
    result = await _preflight(bridge)
    repeated = await _preflight(bridge)
    async with flow.app.state.database.session_factory() as session:
        assert await _counts(session) == before
    assert result == repeated
    assert result.state_version == task.state_version
    assert result.request_hash == request.request_hash
    assert result.provider == request.provider and result.model == request.model
    assert result.reference_count == 1
    assert result.provider_submission_allowed is False
    assert result.actual_submitted is False
    assert result.deliverable_eligible is False
    assert result.provider_capabilities_verified is False
    assert result.qualification_scope == "OFFLINE_SYNTHETIC_ONLY"
    assert leases and all(not lease.result.manifest_path.exists() for lease in leases)
    serialized = result.model_dump_json()
    assert "object_key" not in serialized and "manifest_path" not in serialized
    assert request.locked_prompt.prompt not in serialized


@pytest.mark.parametrize("change", ["revoked", "expired", "budget"])
async def test_current_approval_expiry_and_budget_remain_authoritative(bridge, change):
    _, _, _, approval, inputs, _ = bridge
    if change == "revoked":
        approval = approval.model_copy(update={"status": "REVOKED"})
    elif change == "expired":
        approval = approval.model_copy(update={
            "authorization": approval.authorization.model_copy(update={
                "expires_at": datetime.now(UTC) - timedelta(seconds=1),
            }),
        })
    else:
        approval = approval.model_copy(update={
            "authorization": approval.authorization.model_copy(update={"max_cost_micros": 0}),
        })
    _save_approval(inputs["approval_manifest_path"], approval)
    with pytest.raises(ControlledImageBridgeRejected):
        await _preflight(bridge)


async def test_paid_and_runtime_gates_are_not_bypassed_by_bridge_policy(bridge):
    _, _, _, _, inputs, _ = bridge
    disabled = inputs["settings"].model_copy(update={"paid_generation_enabled": False})
    with pytest.raises(ControlledImageBridgeRejected, match="PAID_GENERATION_DISABLED"):
        await _preflight(bridge, settings=disabled)


async def test_missing_preparation_package_fails_closed_without_breaking_disabled_route(
    bridge, monkeypatch
):
    original = builtins.__import__

    def without_preparation(name, *args, **kwargs):
        if name == "libtv_agent.services.creative_provider_preflight":
            raise ModuleNotFoundError(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_preparation)
    with pytest.raises(ControlledImageBridgeRejected) as rejected:
        await _preflight(bridge)
    assert rejected.value.code == "CONTROLLED_BRIDGE_DEPENDENCIES_UNAVAILABLE"
    assert rejected.value.status_code == 503
    with pytest.raises(ControlledImageBridgeRejected, match="CONTROLLED_BRIDGE_DISABLED"):
        await _preflight(bridge, policy=None)


async def test_api_is_authenticated_default_closed_and_inherits_csrf(bridge, monkeypatch):
    flow, task, _, _, _, _ = bridge
    response = await flow.client.post(_url(task), json={"expected_version": task.state_version})
    assert response.status_code == 401
    response = await flow.client.post(
        _url(task), headers=flow.headers, json={"expected_version": task.state_version},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CONTROLLED_BRIDGE_DISABLED"
    monkeypatch.setattr(flow.settings, "shared_authentication_enabled", True)
    response = await flow.client.post(
        _url(task), headers=flow.headers, json={"expected_version": task.state_version},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CSRF_REJECTED"


@pytest.mark.parametrize("override", [
    {"provider": "nanobanana"}, {"mode": "live"}, {"human_confirmed": True},
    {"approval_manifest_path": "client-selected"}, {"expected_version": True},
    {"expected_version": "1"}, {"expected_version": -1}, {"expected_version": None},
])
async def test_api_does_not_accept_client_authority_or_version_coercion(bridge, override):
    flow, task, _, _, _, _ = bridge
    response = await flow.client.post(
        _url(task), headers=flow.headers,
        json={"expected_version": task.state_version, **override},
    )
    assert response.status_code == 422


async def test_api_maps_real_preflight_evidence_and_errors(bridge, monkeypatch):
    flow, task, _, _, inputs, policy = bridge
    flow.app.state.controlled_image_bridge_policy = policy
    original = preflight_controlled_image_bridge

    async def with_isolated_settings(*args, **kwargs):
        # Keep the application/adapter settings Fake and paid-disabled. Only
        # the read-only validator receives the standalone synthetic quote config.
        kwargs["settings"] = inputs["settings"]
        return await original(*args, **kwargs)

    monkeypatch.setattr(api, "preflight_controlled_image_bridge", with_isolated_settings)
    response = await flow.client.post(
        _url(task), headers=flow.headers, json={"expected_version": task.state_version},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["execution_mode"] == "PREFLIGHT_ONLY"
    assert response.json()["provider_submission_allowed"] is False
    assert flow.app.state.settings.paid_generation_enabled is False
    response = await flow.client.post(
        _url(task), headers=flow.headers, json={"expected_version": 0},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "STALE_VERSION"
    _save_approval(inputs["approval_manifest_path"], bridge[3].model_copy(
        update={"status": "REVOKED"},
    ))
    response = await flow.client.post(
        _url(task), headers=flow.headers, json={"expected_version": task.state_version},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROVIDER_APPROVAL_REVOKED"


async def test_api_keeps_auditors_read_only_and_admins_owner_scoped(bridge):
    flow, task, _, _, inputs, policy = bridge
    flow.app.state.controlled_image_bridge_policy = policy
    response = await flow.client.post(
        _url(task), headers={"X-User-Id": flow.settings.dev_admin_id},
        json={"expected_version": task.state_version},
    )
    assert response.status_code == 404
    async with flow.app.state.database.session_factory() as session:
        await session.execute(update(User).where(User.id == inputs["owner_id"]).values(
            role=UserRole.AUDITOR,
        ))
        await session.commit()
    response = await flow.client.post(
        _url(task), headers=flow.headers, json={"expected_version": task.state_version},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PERMISSION_DENIED"


async def test_openapi_is_additive_and_has_no_submit_operation(bridge):
    flow, _, _, _, _, _ = bridge
    schema = flow.app.openapi()
    path = "/api/v1/creative-production-bridge/tasks/{task_id}/preflight"
    assert set(schema["paths"][path]) == {"post"}
    assert "/api/v1/creative-workflow/tasks" in schema["paths"]
    assert "/api/v1/image-generation-batches" in schema["paths"]
    new_paths = [key for key in schema["paths"] if "/creative-production-bridge/" in key]
    assert new_paths == [path]
    request_schema = schema["components"]["schemas"]["ControlledImageBridgePreflightRequest"]
    assert set(request_schema["properties"]) == {"expected_version"}
    assert request_schema["additionalProperties"] is False
    result_schema = schema["components"]["schemas"]["ControlledImageBridgePreflight"]
    assert result_schema["properties"]["provider_submission_allowed"]["const"] is False
    assert "manifest_path" not in json.dumps(result_schema)
