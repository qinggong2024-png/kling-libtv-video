from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from libtv_agent.creative.workflow import digest
from libtv_agent.domain.enums import ProductLicenseStatus, ProductVersionStatus, UserRole
from libtv_agent.domain.models import (
    ImageGenerationOutput,
    ProductVersion,
    RuntimeConfigVersion,
    User,
    UserDailyPointsSummary,
)
from libtv_agent.services import creative_provider_preflight as service
from libtv_agent.services.creative_provider_preflight import (
    CreativeProviderPreflightRejected,
    ProviderApprovalManifest,
    ProviderCapabilityDeclaration,
    ProviderCostEstimate,
    ProviderHumanAuthorization,
    ProviderReferenceLicense,
    assert_creative_provider_preflight_current,
    preflight_creative_provider_request,
)
from libtv_agent.services.creative_provider_requests import VideoProviderOptions
from libtv_agent.services.generation_safety import PAID_GENERATION_CONFIRMATION
from libtv_agent.services.points import business_date
from pydantic import ValidationError
from sqlalchemy import event, select, update
from test_creative_provider_requests import _compile, _counts, _ready
from test_creative_provider_requests import workflow as workflow
from test_creative_video_bridge import _save_task


def _save_approval(path, approval):
    path.write_text(approval.model_dump_json(), encoding="utf-8")


def _capability(request):
    return ProviderCapabilityDeclaration(
        declaration_id="isolated-static-adapter-contract",
        status="VERIFIED",
        request_kind=request.request_kind,
        provider=request.provider,
        model=request.model,
        max_reference_count=7,
        reference_roles=tuple(ref.role for ref in request.references),
        prompt_max_length=3072,
        aspect_ratios=("9:16", "16:9", "1:1"),
        resolutions=("1k", "2k", "4k", "720p", "1080p", None),
        audio_modes=("off",),
        output_formats=("png", "jpeg"),
        qualities=("low", "medium", "high", None),
        duration_min=3,
        duration_max=15,
    )


async def _prepared(workflow, tmp_path, kind, *, run_mode="dry-run", video_options=None):
    flow, task = await _ready(workflow, kind)
    instant = datetime.now(UTC)
    async with flow.app.state.database.session_factory() as session:
        await session.execute(
            update(ProductVersion)
            .where(ProductVersion.product_id == task.product_id)
            .values(
                license_status=ProductLicenseStatus.VERIFIED,
                status=ProductVersionStatus.APPROVED,
                confirmed_at=instant,
            )
        )
        runtime = await session.scalar(
            select(RuntimeConfigVersion).order_by(RuntimeConfigVersion.version.desc()).limit(1)
        )
        if runtime is None:
            runtime = RuntimeConfigVersion(
                version=1,
                config_json={},
                change_reason="isolated preflight fixture",
            )
            session.add(runtime)
            await session.flush()
        config = {**runtime.config_json, "globalPaused": False, "paidSubmissionsPaused": False}
        await session.execute(
            update(RuntimeConfigVersion)
            .where(RuntimeConfigVersion.id == runtime.id)
            .values(config_json=config)
        )
        await session.commit()
        kwargs = {"run_mode": run_mode}
        if kind == "video":
            kwargs["options"] = video_options or VideoProviderOptions(
                provider="kling_official_api", model="kling-3.0-omni", resolution="1080p"
            )
        request = await _compile(session, flow, task, kind, **kwargs)
    expiry = instant + timedelta(minutes=30)
    approval = ProviderApprovalManifest(
        approval_id="isolated-human-approval",
        revision=1,
        status="ACTIVE",
        authorization=ProviderHumanAuthorization(
            authorization_id=str(uuid.uuid4()),
            owner_id=request.owner_id,
            creative_task_id=request.creative_task_id,
            package_revision_id=request.package_revision_id,
            shot_id=request.shot_id,
            provider=request.provider,
            model=request.model,
            request_hash=request.request_hash,
            evidence_hash=request.evidence_hash,
            confirmed_at=instant,
            expires_at=expiry,
            max_cost_micros=1000,
            currency="USD",
            human_confirmed=True,
        ),
        estimate=ProviderCostEstimate(
            quote_id=str(uuid.uuid4()),
            provider=request.provider,
            model=request.model,
            request_hash=request.request_hash,
            evidence_hash=request.evidence_hash,
            estimated_cost_micros=100,
            currency="USD",
            quota_units=flow.settings.generation_estimated_points if kind == "video" else 1,
            quota_remaining_units=(
                flow.settings.daily_user_points_limit
                if kind == "video"
                else flow.settings.daily_user_image_limit
            ),
            expires_at=expiry,
            includes_upload_cost=True,
            submit_retries=0,
        ),
        licenses=tuple(
            ProviderReferenceLicense(
                license_id=str(uuid.uuid4()),
                owner_id=request.owner_id,
                confirmed_by=request.owner_id,
                creative_task_id=request.creative_task_id,
                role=ref.role,
                object_key=ref.object_key,
                sha256=ref.sha256,
                provider=request.provider,
                evidence_id="isolated-synthetic-license-fixture",
                expires_at=expiry,
            )
            for ref in request.references
        ),
    )
    approval_path = tmp_path / "server-owned-approval.json"
    _save_approval(approval_path, approval)
    # This standalone settings object is never attached to app or an adapter.
    # Test environment and network guard remain paid-disabled throughout.
    settings = flow.settings.model_copy(
        update={
            "app_env": "development",
            "libtv_adapter_mode": "real",
            "libtv_execution_mode": "live",
            "paid_generation_enabled": True,
            "paid_generation_confirmation": PAID_GENERATION_CONFIRMATION,
            "paid_submissions_paused": False,
            "wavespeed_enabled": True,
            "wavespeed_api_key": "synthetic-do-not-use",
            "kling_api_enabled": True,
        }
    )
    inputs = {
        "owner_id": uuid.UUID(request.owner_id),
        "object_store": flow.app.state.object_store,
        "settings": settings,
        "capability": _capability(request),
        "approval_manifest_path": approval_path,
        "now": instant,
    }
    return flow, task, request, approval, inputs


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize("run_mode", ["dry-run", "replay"])
async def test_preflight_read_only_stable_manifest_roles_lease_and_offline_boundaries(
    workflow,
    tmp_path,
    monkeypatch,
    kind,
    run_mode,
):
    flow, task, request, approval, inputs = await _prepared(
        workflow,
        tmp_path,
        kind,
        run_mode=run_mode,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("preflight called Provider, billing or production mutation")

    for target in (
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.upload_media",
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.submit_prediction",
        "libtv_agent.adapters.kling_official_api.KlingOfficialApiAdapter.submit",
        "libtv_agent.adapters.kling_official_api.KlingOfficialApiAdapter.validate_request",
        "libtv_agent.adapters.kling_official_api.KlingOfficialApiAdapter.refresh_capabilities",
        "libtv_agent.adapters.kling_official_api.KlingOfficialApiAdapter.check_availability",
        "libtv_agent.adapters.wavespeed_video.WaveSpeedVideoAdapter.submit",
        "libtv_agent.adapters.wavespeed_video.WaveSpeedVideoAdapter.refresh_capabilities",
        "libtv_agent.adapters.bach_provider.BachApiAdapter.submit",
        "libtv_agent.services.fixed_video_tasks.create_fixed_video_task",
        "libtv_agent.services.image_generations.submit_batch",
        "libtv_agent.services.image_quota.reserve_image_quota",
        "libtv_agent.services.points.reserve_points",
        "libtv_agent.services.points.settle_points",
        "libtv_agent.services.prompt_compiler.compile_video_plan",
        "libtv_agent.services.feedback_learning.apply_video_learning",
    ):
        monkeypatch.setattr(target, forbidden)
    statements = []
    async with flow.app.state.database.session_factory() as session:
        before = await _counts(session)
        connection = await session.connection()

        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement.lstrip().split()[0].upper())

        event.listen(connection.sync_connection, "before_cursor_execute", capture)
        try:
            first = await preflight_creative_provider_request(session, task, request, **inputs)
            with first:
                async with await preflight_creative_provider_request(
                    session,
                    task,
                    request,
                    **inputs,
                ) as repeated:
                    assert first.preflight_hash == repeated.preflight_hash
                    assert first.idempotency_key == repeated.idempotency_key
                    assert first.idempotency_key == request.idempotency_key
                    assert first.manifest_path != repeated.manifest_path
                    assert first.status == "READY_FOR_HUMAN_SUBMIT"
                    manifest = json.loads(first.manifest_path.read_text())
                    assert manifest["references"] == [
                        entry.model_dump(mode="json") for entry in first.materialized_inputs
                    ]
                    assert tuple(
                        (entry.role, entry.order, entry.adapter_field)
                        for entry in first.materialized_inputs
                    ) == tuple(
                        (ref.role, ref.order, ref.adapter_field) for ref in request.references
                    )
                    for entry in first.materialized_inputs:
                        assert entry.path.is_absolute()
                        assert entry.path.parent == first.manifest_path.parent
                        assert hashlib.sha256(entry.path.read_bytes()).hexdigest() == entry.sha256
                    if kind == "video":
                        assert len({entry.path for entry in first.materialized_inputs}) == 3
                    assert first.actual_submitted is False
                    assert first.provider_submission_allowed is False
                    assert first.deliverable_eligible is False
                    assert first.ordinary_output_qualified is False
                    assert first.qualification_scope == "OFFLINE_SYNTHETIC_ONLY"
                    assert first.provider_capabilities_verified is False
                    assert first.expires_at == approval.authorization.expires_at
                    assert "fake://" not in first.result.model_dump_json()
                    assert "https://" not in first.result.model_dump_json()
                    saved = first.result
            assert not saved.manifest_path.exists()
            assert all(not entry.path.exists() for entry in saved.materialized_inputs)
            async with await assert_creative_provider_preflight_current(
                session,
                task,
                saved,
                request,
                **inputs,
            ) as replayed:
                assert replayed.preflight_hash == saved.preflight_hash
        finally:
            event.remove(connection.sync_connection, "before_cursor_execute", capture)
        assert before == await _counts(session)
    assert statements and set(statements) == {"SELECT"}
    assert all(
        [await flow.app.state.object_store.exists(ref.object_key) for ref in request.references]
    )


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "revoked",
        "no_auth",
        "expired",
        "owner",
        "task",
        "package",
        "shot",
        "provider",
        "model",
        "request_hash",
        "evidence_hash",
        "future",
        "not_human",
    ],
)
async def test_independent_human_authorization_required_and_bound_to_exact_request(
    workflow,
    tmp_path,
    kind,
    mutation,
):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, kind)
    payload = approval.model_dump(mode="json")
    expected = "HUMAN_PROVIDER_AUTHORIZATION_MISMATCH"
    if mutation == "missing":
        inputs["approval_manifest_path"] = None
        expected = "HUMAN_PROVIDER_AUTHORIZATION_REQUIRED"
    elif mutation == "revoked":
        payload["status"] = "REVOKED"
        expected = "PROVIDER_APPROVAL_REVOKED"
    elif mutation == "no_auth":
        payload["authorization"] = None
        expected = "HUMAN_PROVIDER_AUTHORIZATION_REQUIRED"
    elif mutation == "expired":
        payload["authorization"]["expires_at"] = (inputs["now"] - timedelta(seconds=1)).isoformat()
        expected = "HUMAN_PROVIDER_AUTHORIZATION_EXPIRED"
    elif mutation == "future":
        payload["authorization"]["confirmed_at"] = (
            inputs["now"] + timedelta(minutes=1)
        ).isoformat()
        expected = "HUMAN_PROVIDER_AUTHORIZATION_INVALID"
    elif mutation == "not_human":
        payload["authorization"]["human_confirmed"] = False
        expected = "PROVIDER_APPROVAL_INVALID"
    else:
        field = {
            "owner": "owner_id",
            "task": "creative_task_id",
            "package": "package_revision_id",
            "shot": "shot_id",
        }.get(mutation, mutation)
        payload["authorization"][field] = (
            "f" * 64
            if field.endswith("_hash")
            else ("SHOT_01" if request.shot_id == "FIRST_FRAME" else "FIRST_FRAME")
            if field == "shot_id"
            else "different"
        )
    approval_path = inputs["approval_manifest_path"] or tmp_path / "unused.json"
    approval_path.write_text(json.dumps(payload), encoding="utf-8")
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeProviderPreflightRejected) as rejected:
            await preflight_creative_provider_request(session, task, request, **inputs)
    assert rejected.value.code == expected


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize(
    "mutation",
    [
        "missing_quote",
        "expired_quote",
        "quote_request",
        "quote_model",
        "budget",
        "currency",
        "quota_input",
        "quota_units",
        "implicit_retries",
        "upload_excluded",
    ],
)
async def test_budget_and_quote_inputs_fail_closed(workflow, tmp_path, kind, mutation):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, kind)
    payload = approval.model_dump(mode="json")
    expected = {
        "missing_quote": "COST_ESTIMATE_REQUIRED",
        "expired_quote": "COST_ESTIMATE_EXPIRED",
        "quote_request": "COST_ESTIMATE_MISMATCH",
        "quote_model": "COST_ESTIMATE_MISMATCH",
        "budget": "BUDGET_EXCEEDED",
        "currency": "BUDGET_CURRENCY_MISMATCH",
        "quota_input": "QUOTA_EXCEEDED",
        "quota_units": "COST_ESTIMATE_QUOTA_MISMATCH",
        "implicit_retries": "PROVIDER_APPROVAL_INVALID",
        "upload_excluded": "PROVIDER_APPROVAL_INVALID",
    }[mutation]
    if mutation == "missing_quote":
        payload["estimate"] = None
    elif mutation == "expired_quote":
        payload["estimate"]["expires_at"] = (inputs["now"] - timedelta(seconds=1)).isoformat()
    else:
        field, value = {
            "quote_request": ("request_hash", "a" * 64),
            "quote_model": ("model", "different"),
            "budget": ("estimated_cost_micros", 1001),
            "currency": ("currency", "CNY"),
            "quota_input": ("quota_remaining_units", 0),
            "quota_units": ("quota_units", 2),
            "implicit_retries": ("submit_retries", 1),
            "upload_excluded": ("includes_upload_cost", False),
        }[mutation]
        payload["estimate"][field] = value
    inputs["approval_manifest_path"].write_text(json.dumps(payload), encoding="utf-8")
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeProviderPreflightRejected) as rejected:
            await preflight_creative_provider_request(session, task, request, **inputs)
    assert rejected.value.code == expected


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize(
    "mutation",
    [
        "disabled",
        "phrase",
        "mode",
        "provider_disabled",
        "pause",
        "runtime_pause",
        "quota",
    ],
)
async def test_actual_server_switches_and_database_quota_are_rechecked(
    workflow,
    tmp_path,
    kind,
    mutation,
):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, kind)
    expected = "PAID_GENERATION_BLOCKED"
    settings = inputs["settings"]
    async with flow.app.state.database.session_factory() as session:
        if mutation == "disabled":
            settings.paid_generation_enabled = False
            expected = "PAID_GENERATION_DISABLED"
        elif mutation == "phrase":
            settings.paid_generation_confirmation = ""
        elif mutation == "mode":
            settings.libtv_execution_mode = "dry-run"
        elif mutation == "provider_disabled":
            settings.wavespeed_enabled = settings.kling_api_enabled = False
            expected = "PROVIDER_SUBMISSION_DISABLED"
        elif mutation == "pause":
            settings.paid_submissions_paused = True
            expected = "PAID_SUBMISSIONS_PAUSED"
        elif mutation == "runtime_pause":
            runtime = await session.scalar(
                select(RuntimeConfigVersion).order_by(RuntimeConfigVersion.version.desc()).limit(1)
            )
            runtime.config_json = {**runtime.config_json, "paidSubmissionsPaused": True}
            await session.commit()
            expected = "PAID_SUBMISSIONS_PAUSED"
        else:
            expected = "QUOTA_EXCEEDED"
            if kind == "image":
                settings.daily_user_image_limit = 1
            else:
                session.add(
                    UserDailyPointsSummary(
                        user_id=inputs["owner_id"],
                        business_date=business_date(inputs["now"]),
                        consumed_points=0,
                        reserved_points=settings.daily_user_points_limit // 2,
                        uncertain_points=(
                            settings.daily_user_points_limit
                            - settings.daily_user_points_limit // 2
                        ),
                    )
                )
                await session.commit()
        with pytest.raises(CreativeProviderPreflightRejected) as rejected:
            await preflight_creative_provider_request(session, task, request, **inputs)
    assert rejected.value.code == expected


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize("mutation", ["missing", "owner", "reviewer", "role", "hash", "expired"])
async def test_each_reference_requires_current_scope_and_license_evidence(
    workflow,
    tmp_path,
    kind,
    mutation,
):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, kind)
    payload = approval.model_dump(mode="json")
    if mutation == "missing":
        payload["licenses"] = []
    else:
        field, value = {
            "owner": ("owner_id", "different"),
            "reviewer": ("confirmed_by", "different"),
            "role": ("role", "STORYBOARD" if kind == "image" else "PRODUCT"),
            "hash": ("sha256", "a" * 64),
            "expired": ("expires_at", (inputs["now"] - timedelta(seconds=1)).isoformat()),
        }[mutation]
        payload["licenses"][0][field] = value
    inputs["approval_manifest_path"].write_text(json.dumps(payload), encoding="utf-8")
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeProviderPreflightRejected) as rejected:
            await preflight_creative_provider_request(session, task, request, **inputs)
    assert rejected.value.code == "REFERENCE_LICENSE_UNCONFIRMED"


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize(
    "mutation",
    ["unknown", "model", "roles", "prompt", "aspect", "resolution"],
)
async def test_static_capability_declaration_is_required_and_enforced(
    workflow,
    tmp_path,
    kind,
    mutation,
):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, kind)
    field, value, expected = {
        "unknown": ("status", "UNKNOWN", "CAPABILITY_UNKNOWN"),
        "model": ("model", "unknown-model", "CAPABILITY_MISMATCH"),
        "roles": ("reference_roles", ("IDENTITY",), "REFERENCE_ROLES_UNSUPPORTED"),
        "prompt": ("prompt_max_length", 1, "PROMPT_TOO_LONG"),
        "aspect": ("aspect_ratios", ("1:1",), "ASPECT_RATIO_UNSUPPORTED"),
        "resolution": ("resolutions", ("not-supported",), "RESOLUTION_UNSUPPORTED"),
    }[mutation]
    inputs["capability"] = inputs["capability"].model_copy(update={field: value})
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeProviderPreflightRejected) as rejected:
            await preflight_creative_provider_request(session, task, request, **inputs)
    assert rejected.value.code == expected


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("count", "REFERENCE_COUNT_UNSUPPORTED"),
        ("duration", "DURATION_UNSUPPORTED"),
        ("unknown_duration", "CAPABILITY_UNKNOWN"),
        ("audio", "AUDIO_UNSUPPORTED"),
    ],
)
async def test_video_capacity_duration_and_audio_are_checked(
    workflow,
    tmp_path,
    mutation,
    expected,
):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, "video")
    field, value = {
        "count": ("max_reference_count", 2),
        "duration": ("duration_max", 4),
        "unknown_duration": ("duration_min", None),
        "audio": ("audio_modes", ("native",)),
    }[mutation]
    inputs["capability"] = inputs["capability"].model_copy(update={field: value})
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeProviderPreflightRejected) as rejected:
            await preflight_creative_provider_request(session, task, request, **inputs)
    assert rejected.value.code == expected


@pytest.mark.parametrize(
    "key",
    [
        "../front.png",
        "/front.png",
        "C:/front.png",
        "front\\asset.png",
        "https://test/front.png",
        "assets//front.png",
        "assets/./front.png",
        "assets/\x00front.png",
    ],
)
async def test_unsafe_object_keys_never_reach_object_store(workflow, tmp_path, monkeypatch, key):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, "image")
    references = (request.references[0].model_copy(update={"object_key": key}),)
    forged = request.model_copy(update={"references": references})
    forged = forged.model_copy(
        update={
            "request_hash": digest(forged.model_dump(mode="json", exclude={"request_hash"})),
        }
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("unsafe key reached storage")

    monkeypatch.setattr(inputs["object_store"], "localize", forbidden)
    monkeypatch.setattr(inputs["object_store"], "exists", forbidden)
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises(CreativeProviderPreflightRejected) as rejected:
            await preflight_creative_provider_request(session, task, forged, **inputs)
    assert rejected.value.code == "OBJECT_KEY_UNSAFE"


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize(
    "mutation",
    [
        "request_hash",
        "evidence_hash",
        "revoked",
        "selection",
        "review",
        "unknown",
        "state",
        "metadata",
        "license",
        "owner",
    ],
)
async def test_old_request_rechecks_source_state_license_review_and_owner(
    workflow,
    tmp_path,
    kind,
    mutation,
):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, kind)
    snapshot = deepcopy(task.snapshot_json)
    async with flow.app.state.database.session_factory() as session:
        if mutation in {"request_hash", "evidence_hash"}:
            request = request.model_copy(update={mutation: "f" * 64})
            if mutation == "evidence_hash":
                request = request.model_copy(
                    update={
                        "request_hash": digest(
                            request.model_dump(mode="json", exclude={"request_hash"}),
                        )
                    }
                )
        elif mutation == "revoked":
            snapshot["asset"]["revoked"] = True
        elif mutation == "selection":
            snapshot.pop("selection")
        elif mutation == "review":
            snapshot["latest_review"]["decision"] = "REJECTED"
        elif mutation == "unknown":
            snapshot["execution_state"] = "UNKNOWN"
        elif mutation == "state":
            task.state_version += 1
        elif mutation == "metadata":
            await session.execute(
                update(ImageGenerationOutput)
                .where(ImageGenerationOutput.id == uuid.UUID(request.source_mapping.output_id))
                .values(review_notes="changed independently")
            )
            await session.commit()
        elif mutation == "license":
            await session.execute(
                update(ProductVersion)
                .where(ProductVersion.id == uuid.UUID(request.canonical_product.product_version_id))
                .values(license_status=ProductLicenseStatus.BLOCKED)
            )
            await session.commit()
        else:
            inputs["owner_id"] = uuid.uuid4()
        task.snapshot_json = snapshot
        await _save_task(flow.app, task)
        with pytest.raises(CreativeProviderPreflightRejected):
            await preflight_creative_provider_request(session, task, request, **inputs)


@pytest.mark.parametrize("mutation", ["approval", "capability", "quota", "result"])
async def test_old_preflight_invalidates_when_approval_capability_quota_or_result_changes(
    workflow,
    tmp_path,
    mutation,
):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, "video")
    async with flow.app.state.database.session_factory() as session:
        with await preflight_creative_provider_request(session, task, request, **inputs) as first:
            saved = first.result
        if mutation == "approval":
            _save_approval(
                inputs["approval_manifest_path"],
                approval.model_copy(
                    update={"revision": 2},
                ),
            )
        elif mutation == "capability":
            inputs["capability"] = inputs["capability"].model_copy(
                update={"prompt_max_length": 4000},
            )
        elif mutation == "quota":
            session.add(
                UserDailyPointsSummary(
                    user_id=inputs["owner_id"],
                    business_date=business_date(inputs["now"]),
                    consumed_points=1,
                    reserved_points=0,
                    uncertain_points=0,
                )
            )
            await session.commit()
        else:
            saved = saved.model_copy(update={"provider": "different"})
        with pytest.raises(CreativeProviderPreflightRejected) as rejected:
            await assert_creative_provider_preflight_current(
                session,
                task,
                saved,
                request,
                **inputs,
            )
        assert rejected.value.code == "PREFLIGHT_STALE"


@pytest.mark.parametrize("mutation", ["local_bytes", "materialize_failure", "approval", "source"])
async def test_materialization_failure_or_midflight_change_cleans_temporary_files(
    workflow,
    tmp_path,
    monkeypatch,
    mutation,
):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, "image")
    temporary_paths = []
    factory = service.TemporaryDirectory

    def tracked_directory(*args, **kwargs):
        directory = factory(*args, **kwargs)
        temporary_paths.append(Path(directory.name))
        return directory

    monkeypatch.setattr(service, "TemporaryDirectory", tracked_directory)
    if mutation in {"local_bytes", "materialize_failure"}:
        original_localize = inputs["object_store"].localize

        async def localize(key, destination):
            source = await original_localize(key, destination)
            if destination.parent.name.startswith("creative-provider-preflight-"):
                if mutation == "materialize_failure":
                    raise OSError("isolated object-store failure")
                destination.write_bytes(b"tampered temporary copy")
                return destination
            return source

        monkeypatch.setattr(inputs["object_store"], "localize", localize)
    else:
        original_materialize = service._materialize

        async def materialize(*args):
            result = await original_materialize(*args)
            if mutation == "approval":
                _save_approval(
                    inputs["approval_manifest_path"],
                    approval.model_copy(
                        update={"status": "REVOKED"},
                    ),
                )
            else:
                task.state_version += 1
                await _save_task(flow.app, task)
            return result

        monkeypatch.setattr(service, "_materialize", materialize)
    async with flow.app.state.database.session_factory() as session:
        with pytest.raises((CreativeProviderPreflightRejected, OSError)):
            await preflight_creative_provider_request(session, task, request, **inputs)
    assert temporary_paths and all(not path.exists() for path in temporary_paths)
    assert await inputs["object_store"].exists(request.canonical_product.object_key)


async def test_remote_style_localize_returns_destination_and_does_not_copy_onto_itself(
    workflow,
    tmp_path,
    monkeypatch,
):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, "image")
    original_localize = inputs["object_store"].localize

    async def localize(key, destination):
        source = await original_localize(key, destination)
        shutil.copyfile(source, destination)
        return destination

    monkeypatch.setattr(inputs["object_store"], "localize", localize)
    async with flow.app.state.database.session_factory() as session:
        with await preflight_creative_provider_request(session, task, request, **inputs) as result:
            assert result.materialized_inputs[0].path.is_file()


async def test_auditor_and_unconfirmed_product_license_cannot_preflight(workflow, tmp_path):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, "image")
    async with flow.app.state.database.session_factory() as session:
        await session.execute(
            update(User)
            .where(User.id == inputs["owner_id"])
            .values(
                role=UserRole.AUDITOR,
            )
        )
        await session.commit()
        request = await _compile(session, flow, task, "image")
        approval = approval.model_copy(
            update={
                "authorization": approval.authorization.model_copy(
                    update={
                        "request_hash": request.request_hash,
                        "evidence_hash": request.evidence_hash,
                    }
                ),
                "estimate": approval.estimate.model_copy(
                    update={
                        "request_hash": request.request_hash,
                        "evidence_hash": request.evidence_hash,
                    }
                ),
            }
        )
        _save_approval(inputs["approval_manifest_path"], approval)
        with pytest.raises(CreativeProviderPreflightRejected) as auditor:
            await preflight_creative_provider_request(session, task, request, **inputs)
        assert auditor.value.code == "OWNER_PERMISSION_DENIED"
        await session.execute(
            update(ProductVersion)
            .where(ProductVersion.id == uuid.UUID(request.canonical_product.product_version_id))
            .values(license_status=ProductLicenseStatus.UNKNOWN)
        )
        await session.commit()
        request = await _compile(session, flow, task, "image")
        with pytest.raises(CreativeProviderPreflightRejected) as unconfirmed:
            await preflight_creative_provider_request(session, task, request, **inputs)
        assert unconfirmed.value.code == "PRODUCT_LICENSE_UNCONFIRMED"


@pytest.mark.parametrize(
    "provider,model,resolution,audio,expected",
    [
        ("kling_official_api", "kling-v3-omni", "1080p", "off", "MODEL_UNSUPPORTED"),
        ("kling_official_api", "kling-3.0-omni", None, "off", "ADAPTER_OPTIONS_UNSUPPORTED"),
        ("kling_official_api", "kling-3.0-omni", "1080p", "on", "ADAPTER_OPTIONS_UNSUPPORTED"),
        ("wavespeed_video", "kwaivgi/kling-video-o3-pro/reference-to-video", None, "off", None),
        ("wavespeed_video", "unknown-model", None, "off", "MODEL_UNSUPPORTED"),
        (
            "wavespeed_video",
            "kwaivgi/kling-video-o3-pro/reference-to-video",
            "1080p",
            "off",
            "ADAPTER_OPTIONS_UNSUPPORTED",
        ),
        ("bach", "bach-1.0", "720p", "off", "REFERENCE_ROLES_UNSUPPORTED"),
    ],
)
async def test_declarations_cannot_override_existing_adapter_model_or_parameter_limits(
    workflow,
    tmp_path,
    provider,
    model,
    resolution,
    audio,
    expected,
):
    flow, task, request, approval, inputs = await _prepared(
        workflow,
        tmp_path,
        "video",
        video_options=VideoProviderOptions(
            provider=provider,
            model=model,
            resolution=resolution,
            audio=audio,
        ),
    )
    inputs["capability"] = inputs["capability"].model_copy(
        update={"audio_modes": ("off", "on")},
    )
    async with flow.app.state.database.session_factory() as session:
        if expected is None:
            with await preflight_creative_provider_request(
                session,
                task,
                request,
                **inputs,
            ) as result:
                assert len(result.materialized_inputs) == 3
        else:
            with pytest.raises(CreativeProviderPreflightRejected) as rejected:
                await preflight_creative_provider_request(session, task, request, **inputs)
            assert rejected.value.code == expected


async def test_unknown_capability_and_missing_runtime_never_initialize_or_submit(
    workflow,
    tmp_path,
):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, "image")
    async with flow.app.state.database.session_factory() as session:
        inputs["capability"] = None
        with pytest.raises(CreativeProviderPreflightRejected) as unknown:
            await preflight_creative_provider_request(session, task, request, **inputs)
        assert unknown.value.code == "CAPABILITY_UNKNOWN"
        inputs["capability"] = _capability(request)
        # Empty config is treated as unknown, even if settings enable the provider.
        runtime = await session.scalar(select(RuntimeConfigVersion))
        runtime.config_json = {}
        await session.commit()
        before = await _counts(session)
        with pytest.raises(CreativeProviderPreflightRejected) as missing:
            await preflight_creative_provider_request(session, task, request, **inputs)
        assert missing.value.code == "PAID_SUBMISSIONS_PAUSED"
        assert before == await _counts(session)


async def test_preflight_does_not_autoflush_an_unrelated_pending_record(workflow, tmp_path):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, "image")
    async with flow.app.state.database.session_factory() as session:
        pending = User(
            id=uuid.uuid4(),
            username=str(uuid.uuid4()),
            password_hash="isolated-pending",
        )
        session.add(pending)
        statements = []
        connection = await session.connection()

        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement.lstrip().split()[0].upper())

        event.listen(connection.sync_connection, "before_cursor_execute", capture)
        try:
            with await preflight_creative_provider_request(session, task, request, **inputs):
                assert pending in session.new
        finally:
            event.remove(connection.sync_connection, "before_cursor_execute", capture)
            await session.rollback()
        assert set(statements) == {"SELECT"}


async def test_product_requires_separate_approval_even_with_verified_license(workflow, tmp_path):
    flow, task, request, approval, inputs = await _prepared(workflow, tmp_path, "image")
    async with flow.app.state.database.session_factory() as session:
        await session.execute(
            update(ProductVersion)
            .where(ProductVersion.id == uuid.UUID(request.canonical_product.product_version_id))
            .values(status=ProductVersionStatus.DRAFT, confirmed_at=None)
        )
        await session.commit()
        request = await _compile(session, flow, task, "image")
        with pytest.raises(CreativeProviderPreflightRejected) as rejected:
            await preflight_creative_provider_request(session, task, request, **inputs)
        assert rejected.value.code == "PRODUCT_VERSION_UNAPPROVED"


def test_contracts_reject_mutation_unknown_fields_and_unbounded_or_implicit_costs():
    with pytest.raises(ValidationError):
        ProviderCapabilityDeclaration(
            declaration_id="invalid",
            status="VERIFIED",
            request_kind="video",
            provider="kling_official_api",
            model="kling-3.0-omni",
            max_reference_count=7,
            reference_roles=("FIRST_FRAME",),
            prompt_max_length=3072,
            aspect_ratios=("9:16",),
            resolutions=("1080p",),
            duration_min=15,
            duration_max=3,
        )
