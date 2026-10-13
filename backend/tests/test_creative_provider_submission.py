from __future__ import annotations

from datetime import timedelta

import pytest
from libtv_agent.services.creative_provider_preflight import (
    preflight_creative_provider_request,
)
from libtv_agent.services.creative_provider_submission import (
    ProviderSubmissionAdmissionRejected,
    SubmissionTicketStore,
    admit_provider_submission,
    claim_submission,
    invalidate_submission,
    provider_submission_result,
    record_provider_submission_result,
)
from test_creative_provider_preflight import _prepared
from test_creative_provider_requests import workflow as workflow


async def _preflights(workflow, tmp_path, kind):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, kind)
    async with flow.app.state.database.session_factory() as session:
        first = await preflight_creative_provider_request(
            session, task, request, **inputs
        )
        second = await preflight_creative_provider_request(
            session, task, request, **inputs
        )
    return flow, task, approval, inputs, first, second


def _forbid_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("MVP-4A attempted Provider or accounting execution")

    for target in (
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.upload_media",
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.submit_prediction",
        "libtv_agent.adapters.kling_official_api.KlingOfficialApiAdapter.submit",
        "libtv_agent.adapters.kling_official_api.KlingOfficialApiAdapter.validate_request",
        "libtv_agent.adapters.wavespeed_video.WaveSpeedVideoAdapter.submit",
        "libtv_agent.services.fixed_video_tasks.create_fixed_video_task",
        "libtv_agent.services.image_generations.submit_batch",
        "libtv_agent.services.image_quota.reserve_image_quota",
        "libtv_agent.services.points.reserve_points",
        "libtv_agent.services.points.settle_points",
        "libtv_agent.services.creative_workflow.record",
    ):
        monkeypatch.setattr(target, forbidden)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["image", "video"])
async def test_admit_produces_only_an_immutable_branch_specific_ticket(
    workflow, tmp_path, monkeypatch, kind
):
    flow, task, approval, inputs, first, second = await _preflights(
        workflow, tmp_path, kind
    )
    _forbid_execution(monkeypatch)
    store = SubmissionTicketStore()

    with first, second:
        claim = admit_provider_submission(
            first,
            current_preflight=second,
            approval=approval,
            store=store,
            now=inputs["now"],
        )

        assert claim.created is True
        assert claim.state.state == "READY_TO_SUBMIT"
        assert claim.ticket.owner_id == first.owner_id
        assert claim.ticket.creative_task_id == first.creative_task_id
        assert claim.ticket.package_revision_id == first.package_revision_id
        assert claim.ticket.shot_id == first.shot_id
        assert claim.ticket.provider == first.provider
        assert claim.ticket.model == first.model
        assert claim.ticket.request_hash == first.request_hash
        assert claim.ticket.evidence_hash == first.evidence_hash
        assert claim.ticket.preflight_hash == first.preflight_hash
        assert claim.ticket.idempotency_key == first.idempotency_key
        assert claim.ticket.estimated_cost_micros == approval.estimate.estimated_cost_micros
        assert claim.ticket.quota_units == approval.estimate.quota_units
        assert claim.ticket.materialized_inputs
        assert claim.ticket.manifest_hash
        assert claim.ticket.quota_reserved is False
        assert claim.ticket.charge_recorded is False
        assert claim.ticket.ledger_attempt_id is None
        assert claim.ticket.actual_submitted is False
        assert claim.ticket.qualification_scope == "OFFLINE_SYNTHETIC_ONLY"
        if kind == "image":
            assert claim.ticket.execution_mode == "image_edit"
            assert claim.ticket.future_adapter_action == "IMAGE_PROVIDER_ADAPTER_SUBMIT"
        else:
            assert claim.ticket.execution_mode == "director_fixed"
            assert claim.ticket.future_adapter_action == "VIDEO_PROVIDER_ADAPTER_SUBMIT"

        with pytest.raises(ValueError):
            claim.ticket.idempotency_key = "changed"


@pytest.mark.asyncio
async def test_same_idempotency_key_replays_one_ticket_and_conflicts_on_changed_hash(
    workflow, tmp_path
):
    _, _, approval, inputs, first, second = await _preflights(
        workflow, tmp_path, "image"
    )
    store = SubmissionTicketStore()
    with first, second:
        original = admit_provider_submission(
            first,
            current_preflight=second,
            approval=approval,
            store=store,
            now=inputs["now"],
        )
        replay = admit_provider_submission(
            first,
            current_preflight=second,
            approval=approval,
            store=store,
            now=inputs["now"],
        )
        assert replay.created is False
        assert replay.ticket == original.ticket
        assert replay.state == original.state

        conflicting = original.ticket.model_copy(
            update={"evidence_hash": "f" * 64}
        )
        with pytest.raises(ProviderSubmissionAdmissionRejected) as rejected:
            claim_submission(store, conflicting, now=inputs["now"])
        assert rejected.value.code == "IDEMPOTENCY_KEY_CONFLICT"


@pytest.mark.asyncio
async def test_admission_requires_current_preflight_and_invalidates_old_claim(
    workflow, tmp_path
):
    _, _, approval, inputs, first, second = await _preflights(
        workflow, tmp_path, "image"
    )
    store = SubmissionTicketStore()
    with first, second:
        original = admit_provider_submission(
            first,
            current_preflight=second,
            approval=approval,
            store=store,
            now=inputs["now"],
        )
        changed = second.model_copy(update={"evidence_hash": "f" * 64})
        with pytest.raises(ProviderSubmissionAdmissionRejected) as rejected:
            admit_provider_submission(
                first,
                current_preflight=changed,
                approval=approval,
                store=store,
                now=inputs["now"],
            )
        assert rejected.value.code == "PREFLIGHT_STALE"
        assert store.get(original.ticket.idempotency_key).state == "INVALIDATED"
        assert (
            store.get(original.ticket.idempotency_key).invalidation_reason
            == "SOURCE_CHANGED"
        )


@pytest.mark.asyncio
async def test_expired_ready_ticket_is_invalidated_on_reclaim(workflow, tmp_path):
    _, _, approval, inputs, first, second = await _preflights(
        workflow, tmp_path, "image"
    )
    store = SubmissionTicketStore()
    with first, second:
        original = admit_provider_submission(
            first,
            current_preflight=second,
            approval=approval,
            store=store,
            now=inputs["now"],
        )
        expired = claim_submission(
            store,
            original.ticket,
            now=inputs["now"] + timedelta(minutes=31),
        )
        assert expired.created is False
        assert expired.state.state == "INVALIDATED"
        assert expired.state.invalidation_reason == "TICKET_EXPIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("revoked", "PROVIDER_APPROVAL_REVOKED"),
        ("expired", "PREFLIGHT_EXPIRED"),
        ("auth_expired", "HUMAN_PROVIDER_AUTHORIZATION_EXPIRED"),
        ("budget", "BUDGET_EXCEEDED"),
    ],
)
async def test_expiry_revoke_and_budget_changes_reject_admission(
    workflow, tmp_path, mutation, expected
):
    _, _, approval, inputs, first, second = await _preflights(
        workflow, tmp_path, "image"
    )
    if mutation == "revoked":
        approval = approval.model_copy(update={"status": "REVOKED"})
    elif mutation == "auth_expired":
        authorization = approval.authorization.model_copy(
            update={"expires_at": inputs["now"] - timedelta(seconds=1)}
        )
        approval = approval.model_copy(update={"authorization": authorization})
    elif mutation == "budget":
        estimate = approval.estimate.model_copy(update={"estimated_cost_micros": 10_001})
        approval = approval.model_copy(update={"estimate": estimate})
    now = (
        inputs["now"] + timedelta(minutes=31)
        if mutation == "expired"
        else inputs["now"]
    )
    with first, second:
        with pytest.raises(ProviderSubmissionAdmissionRejected) as rejected:
            admit_provider_submission(
                first,
                current_preflight=second,
                approval=approval,
                store=SubmissionTicketStore(),
                now=now,
            )
    assert rejected.value.code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_state", "retry_policy"),
    [
        ("SUBMITTED", "SUBMITTED", "NONE"),
        ("UNKNOWN", "UNKNOWN", "RECONCILE_ONLY"),
        ("FAILED", "FAILED", "EXPLICIT_NEW_IDEMPOTENCY_KEY"),
    ],
)
async def test_provider_outcome_is_a_reconciliation_contract_and_never_reclaims_same_key(
    workflow, tmp_path, status, expected_state, retry_policy
):
    _, _, approval, inputs, first, second = await _preflights(
        workflow, tmp_path, "video"
    )
    store = SubmissionTicketStore()
    with first, second:
        claim = admit_provider_submission(
            first,
            current_preflight=second,
            approval=approval,
            store=store,
            now=inputs["now"],
        )
        result = provider_submission_result(
            claim.ticket,
            status=status,
            provider_task_id="provider-task-1" if status == "SUBMITTED" else None,
            provider_status="submitted" if status == "SUBMITTED" else "unknown",
            error_code="PROVIDER_FAILED" if status == "FAILED" else None,
        )
        state = record_provider_submission_result(store, claim.ticket, result)
        assert state.state == expected_state
        assert state.result.retry_policy == retry_policy
        assert state.ticket.idempotency_key == claim.ticket.idempotency_key

        repeated = claim_submission(store, claim.ticket, now=inputs["now"])
        assert repeated.created is False
        assert repeated.state == state

        if status == "UNKNOWN":
            assert state.result.actual_submitted is None
            assert state.invalidation_reason == "EXECUTION_UNKNOWN"
        elif status == "FAILED":
            assert state.result.actual_submitted is False
            assert state.invalidation_reason == "PROVIDER_SUBMISSION_FAILED"
        else:
            assert state.result.actual_submitted is True
            assert state.invalidation_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        "TICKET_EXPIRED",
        "AUTHORIZATION_REVOKED",
        "SOURCE_CHANGED",
        "EXECUTION_UNKNOWN",
        "USER_STOPPED",
    ],
)
async def test_explicit_invalidation_reasons_close_ticket(
    workflow, tmp_path, reason
):
    _, _, approval, inputs, first, second = await _preflights(
        workflow, tmp_path, "image"
    )
    store = SubmissionTicketStore()
    with first, second:
        claim = admit_provider_submission(
            first,
            current_preflight=second,
            approval=approval,
            store=store,
            now=inputs["now"],
        )
        state = invalidate_submission(store, claim.ticket, reason=reason)
        assert state.state == "INVALIDATED"
        assert state.invalidation_reason == reason
        replay = claim_submission(store, claim.ticket, now=inputs["now"])
        assert replay.created is False
        assert replay.state.state == "INVALIDATED"
