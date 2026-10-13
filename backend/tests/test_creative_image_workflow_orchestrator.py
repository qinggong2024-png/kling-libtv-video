from __future__ import annotations

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
from test_creative_provider_executor import ForbiddenAdapter, _prepared_ticket
from test_creative_provider_requests import workflow as workflow


class CountingTestDouble:
    is_test_double = True

    def __init__(self) -> None:
        self.uploads = 0
        self.submissions = 0

    async def upload_media(self, source, *, filename=None, content_type=None):
        del source, filename, content_type
        self.uploads += 1
        return "https://test.invalid/creative-input.png"

    async def submit_prediction(self, model_id, payload, *, validate_model=True):
        del model_id, payload, validate_model
        self.submissions += 1
        return {"id": "test-double-provider-task", "status": "created"}


async def _run(
    workflow,
    tmp_path,
    *,
    mode="dry-run",
    adapter=None,
    settings=None,
    controls=None,
):
    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path
    )
    async with flow.app.state.database.session_factory() as session:
        result = await execute_creative_image_workflow(
            session,
            task=task,
            request=request,
            ticket=claim.ticket,
            preflight=preflight.result,
            owner_id=inputs["owner_id"],
            object_store=inputs["object_store"],
            settings=settings or inputs["settings"],
            capability=inputs["capability"],
            approval_manifest_path=inputs["approval_manifest_path"],
            controls=controls or CreativeImageWorkflowControls(mode=mode),
            adapter=adapter,
            approval=approval,
            now=inputs["now"],
        )
    return flow, task, request, approval, inputs, preflight, claim, result


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("dry-run", "PREPARED"), ("replay", "REPLAYED")],
)
async def test_durable_ticket_lease_and_executor_chain_is_auditable(
    workflow, tmp_path, mode, expected
):
    flow, task, request, approval, inputs, preflight, claim, result = await _run(
        workflow,
        tmp_path,
        mode=mode,
        adapter=ForbiddenAdapter(),
    )
    del task, approval, preflight
    assert result.status == expected
    assert result.audit.execution_mode == mode
    assert result.audit.ticket_id == claim.ticket.ticket_id
    assert result.audit.lease_id.startswith("pil:")
    assert result.audit.request_hash == request.request_hash
    assert result.audit.evidence_hash == request.evidence_hash
    assert result.actual_submitted is False
    assert result.deliverable_eligible is False
    assert result.audit.qualification_scope == "OFFLINE_SYNTHETIC_ONLY"
    assert len(result.audit.input_manifest) == 1
    assert "/creative-provider-inputs/" in result.audit.input_manifest[0][
        "durable_object_key"
    ]
    assert "path" not in result.audit.input_manifest[0]
    assert [stage["stage"] for stage in result.audit.stage_audit] == [
        "DURABLE_TICKET",
        "DURABLE_INPUT_LEASE",
        "IMAGE_EXECUTOR",
    ]
    assert result.audit.stage_audit[-1]["status"] == expected
    assert result.audit.input_manifest_hash
    assert len(result.audit.summary_hash) == 64

    async with flow.app.state.database.session_factory() as session:
        saved_ticket = await DurableSubmissionTicketStore().get(
            session, claim.ticket.idempotency_key
        )
        assert saved_ticket is not None
        assert saved_ticket.state == "READY_TO_SUBMIT"


async def test_test_double_is_the_only_non_live_adapter_path(workflow, tmp_path):
    adapter = CountingTestDouble()
    _, _, _, _, _, _, _, result = await _run(
        workflow,
        tmp_path,
        mode="test-double",
        adapter=adapter,
    )
    assert result.status == "TEST_DOUBLE"
    assert result.actual_submitted is False
    assert adapter.uploads == 1
    assert adapter.submissions == 1
    assert result.audit.qualification_scope == "OFFLINE_SYNTHETIC_ONLY"
    assert result.audit.deliverable_eligible is False


async def test_live_is_rechecked_then_stopped_before_any_real_adapter_call(
    workflow, tmp_path
):
    adapter = ForbiddenAdapter()
    settings = None
    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path
    )
    settings = inputs["settings"].model_copy(
        update={
            "app_env": "staging",
            "paid_generation_enabled": True,
            "paid_submissions_paused": False,
            "global_paused": False,
        }
    )
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeImageWorkflowRejected) as rejected:
            await execute_creative_image_workflow(
                session,
                task=task,
                request=request,
                ticket=claim.ticket,
                preflight=preflight.result,
                owner_id=inputs["owner_id"],
                object_store=inputs["object_store"],
                settings=settings,
                capability=inputs["capability"],
                approval_manifest_path=inputs["approval_manifest_path"],
                controls=CreativeImageWorkflowControls(
                    mode="live",
                    live_feature_enabled=True,
                    admin_live_enabled=True,
                    human_confirmed=True,
                ),
                adapter=adapter,
                approval=approval,
                now=inputs["now"],
            )
    assert rejected.value.code == "LIVE_EXECUTION_DISABLED_MVP7A"


@pytest.mark.parametrize(
    ("ticket_status", "expected"),
    [
        ("UNKNOWN", "UNKNOWN_RECONCILE_ONLY"),
        ("FAILED", "FAILED_NEW_IDEMPOTENCY_KEY_REQUIRED"),
    ],
)
async def test_unknown_and_failed_ticket_states_are_not_resubmitted(
    workflow, tmp_path, ticket_status, expected
):
    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path
    )
    del approval
    async with flow.app.state.database.session_factory() as session:
        await DurableSubmissionTicketStore().record_provider_result(
            session,
            claim.ticket.idempotency_key,
            provider_submission_result(
                claim.ticket,
                status=ticket_status,
                error_code="synthetic-boundary",
            ),
        )
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
    assert rejected.value.code == expected


async def test_stopped_task_is_rejected_before_durable_lease_or_adapter(
    workflow, tmp_path
):
    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path
    )
    del approval
    task.snapshot_json = {**task.snapshot_json, "stopped": True}
    async with flow.app.state.database.session_factory() as session:
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
    assert rejected.value.code == "USER_STOPPED"


async def test_stopped_ticket_cannot_be_replayed_with_same_idempotency_key(
    workflow, tmp_path
):
    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path
    )
    del approval
    async with flow.app.state.database.session_factory() as session:
        stopped = await DurableSubmissionTicketStore().invalidate(
            session,
            claim.ticket.idempotency_key,
            "USER_STOPPED",
        )
        assert stopped.state == "INVALIDATED"
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
    assert rejected.value.code == "USER_STOPPED"
