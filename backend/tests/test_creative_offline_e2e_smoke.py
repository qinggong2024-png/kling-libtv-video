from __future__ import annotations

import uuid

import pytest
from libtv_agent.services.creative_image_workflow_orchestrator import (
    CreativeImageWorkflowControls,
    CreativeImageWorkflowRejected,
    execute_creative_image_workflow,
)
from libtv_agent.services.creative_provider_submission import provider_submission_result
from libtv_agent.services.creative_provider_submission_persistence import (
    DurableSubmissionTicketStore,
)
from libtv_agent.services.creative_video_bridge import plan_creative_video_bridge
from test_creative_image_workflow_orchestrator import CountingTestDouble
from test_creative_provider_executor import ForbiddenAdapter, _prepared_ticket
from test_creative_provider_requests import workflow as workflow
from test_creative_video_bridge import Flow as VideoFlow
from test_creative_video_bridge import _task as video_task


def _forbid_real_provider_paths(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("offline smoke test reached a real Provider path")

    for target in (
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.upload_media",
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.submit_prediction",
        "libtv_agent.adapters.kling_official_api.KlingOfficialApiAdapter.submit",
        "libtv_agent.adapters.wavespeed_video.WaveSpeedVideoAdapter.submit",
        "libtv_agent.adapters.bach_provider.BachApiAdapter.submit",
        "libtv_agent.services.image_generations.submit_batch",
    ):
        monkeypatch.setattr(target, forbidden)


@pytest.mark.parametrize(
    ("mode", "expected_status"),
    [
        ("dry-run", "PREPARED"),
        ("replay", "REPLAYED"),
        ("test-double", "TEST_DOUBLE"),
    ],
)
async def test_offline_image_chain_is_provider_free_and_stays_synthetic(
    workflow,
    tmp_path,
    monkeypatch,
    mode,
    expected_status,
):
    _forbid_real_provider_paths(monkeypatch)
    (
        flow,
        task,
        request,
        approval,
        inputs,
        preflight,
        claim,
    ) = await _prepared_ticket(workflow, tmp_path)
    del approval
    adapter = CountingTestDouble() if mode == "test-double" else ForbiddenAdapter()

    async with flow.app.state.database.session_factory() as session:
        result = await execute_creative_image_workflow(
            session,
            task=task,
            request=request,
            ticket=claim.ticket,
            preflight=preflight.result,
            owner_id=inputs["owner_id"],
            object_store=inputs["object_store"],
            settings=inputs["settings"],
            capability=inputs["capability"],
            approval_manifest_path=inputs["approval_manifest_path"],
            controls=CreativeImageWorkflowControls(mode=mode),
            adapter=adapter,
            now=inputs["now"],
        )

    assert result.status == expected_status
    assert result.actual_submitted is False
    assert result.deliverable_eligible is False
    assert result.execution.qualification_scope == "OFFLINE_SYNTHETIC_ONLY"
    assert result.execution.deliverable_eligible is False
    assert result.audit.qualification_scope == "OFFLINE_SYNTHETIC_ONLY"
    assert result.audit.deliverable_eligible is False
    assert request.ordinary_output_qualified is False
    assert request.deliverable_eligible is False
    assert preflight.result.ordinary_output_qualified is False
    assert preflight.result.deliverable_eligible is False
    assert claim.ticket.ordinary_output_qualified is False
    assert claim.ticket.deliverable_eligible is False

    if mode == "test-double":
        assert adapter.uploads == 1
        assert adapter.submissions == 1


async def test_unknown_submission_is_reconciliation_only_and_never_replayed(
    workflow,
    tmp_path,
):
    (
        flow,
        task,
        request,
        approval,
        inputs,
        preflight,
        claim,
    ) = await _prepared_ticket(workflow, tmp_path)
    del approval
    store = DurableSubmissionTicketStore()

    async with flow.app.state.database.session_factory() as session:
        receipt = await store.record_provider_result(
            session,
            claim.ticket.idempotency_key,
            provider_submission_result(
                claim.ticket,
                status="UNKNOWN",
                error_code="offline-smoke-unknown",
            ),
        )
        assert receipt.state == "UNKNOWN"
        assert receipt.result is not None
        assert receipt.result.retry_policy == "RECONCILE_ONLY"
        with pytest.raises(CreativeImageWorkflowRejected) as rejected:
            await execute_creative_image_workflow(
                session,
                task=task,
                request=request,
                ticket=claim.ticket,
                preflight=preflight.result,
                owner_id=inputs["owner_id"],
                object_store=inputs["object_store"],
                settings=inputs["settings"],
                capability=inputs["capability"],
                approval_manifest_path=inputs["approval_manifest_path"],
                controls=CreativeImageWorkflowControls(mode="dry-run"),
                adapter=ForbiddenAdapter(),
                now=inputs["now"],
            )

    assert rejected.value.code == "UNKNOWN_RECONCILE_ONLY"


async def test_director_fixed_offline_bridge_only_plans_and_skips_legacy_video_planning(
    workflow,
    monkeypatch,
):
    flow = VideoFlow(*workflow)
    await flow.ready()
    task = await video_task(flow.app, flow.task_id)
    called: list[str] = []

    def forbidden(*args, **kwargs):
        del args, kwargs
        called.append("legacy-video-planner")
        raise AssertionError("director_fixed called the legacy video planner")

    monkeypatch.setattr("libtv_agent.services.prompt_compiler.compile_video_plan", forbidden)
    monkeypatch.setattr("libtv_agent.services.feedback_learning.apply_video_learning", forbidden)

    async with flow.app.state.database.session_factory() as session:
        plan = await plan_creative_video_bridge(
            session,
            task,
            owner_id=uuid.UUID(flow.settings.dev_user_id),
            object_store=flow.app.state.object_store,
        )

    assert plan.execution_mode == "director_fixed"
    assert plan.offline_synthetic_only is True
    assert plan.provider_submission_allowed is False
    assert plan.deliverable_eligible is False
    assert plan.next_steps == [
        "REAL_VIDEO_PROVIDER_ADAPTER_REQUIRED",
        "HUMAN_PROVIDER_AUTHORIZATION_REQUIRED",
    ]
    assert called == []
