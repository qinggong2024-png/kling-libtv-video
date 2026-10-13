from __future__ import annotations

from datetime import timedelta

import pytest
from libtv_agent.services.creative_provider_executor import (
    CreativeExecutionControls,
    CreativeProviderExecutionRejected,
    execute_creative_image,
)
from libtv_agent.services.creative_provider_preflight import (
    preflight_creative_provider_request,
)
from libtv_agent.services.creative_provider_submission import provider_submission_result
from libtv_agent.services.creative_provider_submission_persistence import (
    DurableSubmissionTicketStore,
    admit_provider_submission_durable,
)
from test_creative_provider_preflight import _prepared
from test_creative_provider_requests import workflow as workflow


class ForbiddenAdapter:
    async def upload_media(self, *args, **kwargs):
        raise AssertionError("dry-run/replay must not upload")

    async def submit_prediction(self, *args, **kwargs):
        raise AssertionError("dry-run/replay must not POST")


class ExplicitTestDouble:
    is_test_double = True

    async def upload_media(self, source, *, filename=None, content_type=None):
        del source, filename, content_type
        return "https://test.invalid/staged-input.png"

    async def submit_prediction(self, model_id, payload, *, validate_model=True):
        del model_id, payload, validate_model
        return {"id": "test-double-task-1", "status": "created"}


async def _prepared_ticket(workflow, tmp_path):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, "image")
    async with flow.app.state.database.session_factory() as session:
        preflight = await preflight_creative_provider_request(
            session, task, request, **inputs
        )
        claim = await admit_provider_submission_durable(
            session,
            preflight,
            current_preflight=preflight,
            approval=approval,
            store=DurableSubmissionTicketStore(),
            now=inputs["now"],
        )
        await session.commit()
    return flow, task, request, approval, inputs, preflight, claim


@pytest.mark.parametrize("mode", ["dry-run", "replay"])
async def test_dry_run_and_replay_are_read_only_and_never_call_adapter(
    workflow, tmp_path, mode
):
    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path
    )
    del approval
    async with flow.app.state.database.session_factory() as session:
        result = await execute_creative_image(
            session,
            task=task,
            request=request,
            ticket=claim.ticket,
            preflight=preflight.result,
            owner_id=inputs["owner_id"],
            object_store=inputs["object_store"],
            settings=inputs["settings"],
            controls=CreativeExecutionControls(mode=mode),
            adapter=ForbiddenAdapter(),
            now=inputs["now"],
        )
    assert result.status == ("PREPARED" if mode == "dry-run" else "REPLAYED")
    assert result.actual_submitted is False
    assert result.qualification_scope == "OFFLINE_SYNTHETIC_ONLY"
    assert result.deliverable_eligible is False
    assert result.provider_task_id is None


async def test_live_execution_requires_admin_flag_and_human_confirmation_before_adapter(
    workflow, tmp_path
):
    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path
    )
    del approval
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeProviderExecutionRejected) as rejected:
            await execute_creative_image(
                session,
                task=task,
                request=request,
                ticket=claim.ticket,
                preflight=preflight.result,
                owner_id=inputs["owner_id"],
                object_store=inputs["object_store"],
                settings=inputs["settings"],
                controls=CreativeExecutionControls(
                    mode="live",
                    admin_live_enabled=False,
                    human_confirmed=False,
                ),
                adapter=ForbiddenAdapter(),
                now=inputs["now"],
            )
    assert rejected.value.code == "CREATIVE_LIVE_FEATURE_DISABLED"


async def test_live_execution_is_blocked_in_test_environment_even_with_both_controls(
    workflow, tmp_path
):
    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path
    )
    test_settings = inputs["settings"].model_copy(update={"app_env": "test"})
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeProviderExecutionRejected) as rejected:
            await execute_creative_image(
                session,
                task=task,
                request=request,
                ticket=claim.ticket,
                preflight=preflight.result,
                owner_id=inputs["owner_id"],
                object_store=inputs["object_store"],
                settings=test_settings,
                controls=CreativeExecutionControls(
                    mode="live",
                    admin_live_enabled=True,
                    human_confirmed=True,
                ),
                adapter=ForbiddenAdapter(),
                approval=approval,
                capability=inputs["capability"],
                approval_manifest_path=inputs["approval_manifest_path"],
                now=inputs["now"],
            )
    assert rejected.value.code == "LIVE_EXECUTION_BLOCKED_IN_TEST"


async def test_test_double_requires_explicit_marker_and_remains_unqualified(
    workflow, tmp_path
):
    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path
    )
    del approval
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeProviderExecutionRejected) as rejected:
            await execute_creative_image(
                session,
                task=task,
                request=request,
                ticket=claim.ticket,
                preflight=preflight.result,
                owner_id=inputs["owner_id"],
                object_store=inputs["object_store"],
                settings=inputs["settings"],
                controls=CreativeExecutionControls(mode="test-double"),
                adapter=ForbiddenAdapter(),
                now=inputs["now"],
            )
    assert rejected.value.code == "EXPLICIT_TEST_DOUBLE_REQUIRED"

    async with flow.app.state.database.session_factory() as session:
        result = await execute_creative_image(
            session,
            task=task,
            request=request,
            ticket=claim.ticket,
            preflight=preflight.result,
            owner_id=inputs["owner_id"],
            object_store=inputs["object_store"],
            settings=inputs["settings"],
            controls=CreativeExecutionControls(mode="test-double"),
            adapter=ExplicitTestDouble(),
            now=inputs["now"],
        )
    assert result.status == "TEST_DOUBLE"
    assert result.actual_submitted is False
    assert result.qualification_scope == "OFFLINE_SYNTHETIC_ONLY"
    assert result.deliverable_eligible is False


async def test_ticket_terminal_state_cannot_be_executed_again(
    workflow, tmp_path
):
    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path
    )
    del approval
    store = DurableSubmissionTicketStore()
    async with flow.app.state.database.session_factory() as session:
        receipt = await store.record_provider_result(
            session,
            claim.ticket.idempotency_key,
            provider_submission_result(claim.ticket, status="UNKNOWN"),
        )
        assert receipt.state == "UNKNOWN"
        with pytest.raises(CreativeProviderExecutionRejected) as rejected:
            await execute_creative_image(
                session,
                task=task,
                request=request,
                ticket=claim.ticket,
                preflight=preflight.result,
                owner_id=inputs["owner_id"],
                object_store=inputs["object_store"],
                settings=inputs["settings"],
                controls=CreativeExecutionControls(mode="dry-run"),
                adapter=ForbiddenAdapter(),
                now=inputs["now"],
            )
    assert rejected.value.code == "TICKET_NOT_SUBMITTABLE"


async def test_expired_ticket_is_rejected_before_dry_run(
    workflow, tmp_path
):
    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path
    )
    del approval
    expired = inputs["now"] + timedelta(minutes=31)
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeProviderExecutionRejected) as rejected:
            await execute_creative_image(
                session,
                task=task,
                request=request,
                ticket=claim.ticket,
                preflight=preflight.result,
                owner_id=inputs["owner_id"],
                object_store=inputs["object_store"],
                settings=inputs["settings"],
                controls=CreativeExecutionControls(mode="dry-run"),
                adapter=ForbiddenAdapter(),
                now=expired,
            )
    assert rejected.value.code == "TICKET_EXPIRED"
