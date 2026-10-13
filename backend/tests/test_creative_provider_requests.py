from __future__ import annotations

import json
import uuid
from copy import deepcopy
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from libtv_agent.adapters.video_provider import VideoGenerationRequest
from libtv_agent.creative.workflow import digest
from libtv_agent.domain.enums import ProductLicenseStatus, QualityDecisionStatus
from libtv_agent.domain.models import (
    Base,
    ImageGenerationItem,
    ImageGenerationOutput,
    Product,
    ProductVersion,
    User,
)
from libtv_agent.services.creative_provider_requests import (
    CreativeImageProviderRequest,
    CreativeProviderRequestRejected,
    CreativeVideoProviderRequest,
    ImageProviderOptions,
    VideoProviderOptions,
    assert_creative_provider_request_current,
    compile_creative_image_request,
    compile_creative_video_request,
)
from libtv_agent.services.image_generations import build_prediction_payload
from pydantic import ValidationError
from sqlalchemy import event, func, select, update
from test_creative_image_bridge import Flow as ImageFlow
from test_creative_video_bridge import Flow as VideoFlow
from test_creative_video_bridge import _save_task, _task
from test_creative_video_bridge import workflow as workflow

VIDEO_OPTIONS = VideoProviderOptions(provider="kling_official_api", model="kling-v3-omni")


async def _ready(workflow, kind):
    flow = (ImageFlow if kind == "image" else VideoFlow)(*workflow)
    await flow.ready()
    return flow, await _task(flow.app, flow.task_id)


async def _compile(session, flow, task, kind, **kwargs):
    compiler = compile_creative_image_request if kind == "image" else compile_creative_video_request
    if kind == "video":
        kwargs.setdefault("options", VIDEO_OPTIONS)
    return await compiler(
        session, task, owner_id=uuid.UUID(flow.settings.dev_user_id),
        object_store=flow.app.state.object_store, **kwargs,
    )


async def _counts(session):
    return {
        table.name: await session.scalar(select(func.count()).select_from(table))
        for table in Base.metadata.sorted_tables
    }


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize("run_mode", ["dry-run", "replay"])
async def test_compile_and_replay_are_stable_read_only_and_never_submit(
    workflow, monkeypatch, kind, run_mode
):
    flow, task = await _ready(workflow, kind)

    def forbidden(*args, **kwargs):
        raise AssertionError("Provider/planning/production submission was called")

    for name in (
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.upload_media",
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.submit_prediction",
        "libtv_agent.adapters.kling_official_api.KlingOfficialApiAdapter.submit",
        "libtv_agent.adapters.kling_official_api.KlingOfficialApiAdapter.validate_request",
        "libtv_agent.adapters.wavespeed_video.WaveSpeedVideoAdapter.submit",
        "libtv_agent.adapters.bach_provider.BachApiAdapter.submit",
        "libtv_agent.services.fixed_video_tasks.create_fixed_video_task",
        "libtv_agent.services.image_generations.submit_batch",
        "libtv_agent.services.prompt_compiler.compile_video_plan",
        "libtv_agent.services.feedback_learning.apply_video_learning",
    ):
        monkeypatch.setattr(name, forbidden)

    statements = []
    async with flow.app.state.database.session_factory() as session:
        before = await _counts(session)

        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement.lstrip().split()[0].upper())

        connection = await session.connection()
        event.listen(connection.sync_connection, "before_cursor_execute", capture)
        try:
            request = await _compile(session, flow, task, kind, run_mode=run_mode)
            repeated = await _compile(session, flow, task, kind, run_mode=run_mode)
            replayed = await assert_creative_provider_request_current(
                session, task, request, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=flow.app.state.object_store,
            )
        finally:
            event.remove(connection.sync_connection, "before_cursor_execute", capture)
        assert before == await _counts(session)
        outputs = list(await session.scalars(select(ImageGenerationOutput)))
    assert statements and set(statements) == {"SELECT"}
    assert request == repeated == replayed
    assert request.request_hash == digest(
        request.model_dump(mode="json", exclude={"request_hash"})
    )
    assert request.run_mode == run_mode
    assert request.actual_submitted is False
    assert request.provider_submission_allowed is False
    assert request.ordinary_output_qualified is False
    assert request.deliverable_eligible is False
    assert request.qualification_scope == "OFFLINE_SYNTHETIC_ONLY"
    assert request.provider_capabilities_verified is False
    assert all(output.qualification_status is QualityDecisionStatus.PENDING for output in outputs)
    assert all(not reference.actual_submitted for reference in request.references)
    assert all(not reference.provider_accepted for reference in request.references)
    assert "fake://" not in request.model_dump_json()
    assert "https://" not in request.model_dump_json()
    assert "http://" not in request.model_dump_json()
    assert uuid.UUID(request.source_mapping.output_id)
    restored = type(request).model_validate_json(request.model_dump_json())
    assert restored == request


@pytest.mark.parametrize("provider", ["gpt", "nanobanana"])
async def test_image_contract_reuses_prediction_payload_without_inventing_urls(workflow, provider):
    flow, task = await _ready(workflow, "image")
    options = ImageProviderOptions(provider=provider)
    async with flow.app.state.database.session_factory() as session:
        request = await _compile(session, flow, task, "image", options=options)
    prompt = task.snapshot_json["package"]["prompt"]
    model, expected = build_prediction_payload(
        provider=provider, prompt=prompt, image_urls=[request.canonical_product.object_key],
        aspect_ratio="9:16", resolution="2k", quality=None, output_format="png",
    )
    expected.pop("images")
    assert request.model == model
    assert request.mode == "edit"
    assert request.locked_prompt.prompt == request.adapter_parameters.prompt == prompt
    assert request.locked_prompt.prompt_hash == digest(prompt)
    assert request.adapter_parameters.model_dump(exclude_none=True) == expected
    assert len(request.references) == 1
    reference = request.references[0]
    assert (reference.role, reference.order, reference.adapter_field) == ("PRODUCT", 1, "images")
    assert reference.object_key == request.canonical_product.object_key
    assert reference.sha256 == request.canonical_product.sha256
    assert reference.source_mapping is None  # Generated Fake is not the canonical product.
    candidate = task.snapshot_json["candidates"][0]
    assert request.source_mapping.candidate_id == candidate["candidate_id"]
    assert request.source_mapping.package_revision_id == request.package_revision_id
    assert request.source_mapping.shot_id == "FIRST_FRAME"


async def test_video_contract_preserves_locked_storyboard_and_adapter_binding_order(workflow):
    flow, task = await _ready(workflow, "video")
    async with flow.app.state.database.session_factory() as session:
        request = await _compile(session, flow, task, "video")
    package = task.snapshot_json["storyboard"]["packages"]["SHOT_01"]
    assert request.execution_mode == "director_fixed"
    assert request.shot_id == "SHOT_01"
    assert request.locked_prompt.prompt == request.adapter_parameters.prompt == package["prompt"]
    assert request.locked_prompt.prompt_hash == digest(package["prompt"])
    assert request.locked_prompt.preservation_hash == package["preservation_hash"]
    frozen = json.loads(request.locked_prompt.text_contract_json)
    assert frozen["package"] == package
    assert frozen["contract_hash"] == request.locked_prompt.text_contract_hash
    assert [
        (reference.role, reference.order, reference.adapter_field)
        for reference in request.references
    ] == [
        ("FIRST_FRAME", 1, "first_frame_path"),
        ("STORYBOARD", 2, "refer_image_paths"),
        ("PRODUCT", 3, "product_reference_paths"),
    ]
    first, storyboard, product = request.references
    assert first.source_mapping.candidate_id == task.snapshot_json["selection"]["candidate_id"]
    assert storyboard.source_mapping == request.source_mapping
    assert storyboard.source_mapping.package_revision_id == package["package_id"]
    assert product.source_mapping is None
    assert product.sha256 == request.canonical_product.sha256
    assert all(reference.sha256 == product.sha256 for reference in request.references)
    assert len({first.source_mapping.output_id, storyboard.source_mapping.output_id}) == 2
    assert set(request.adapter_parameters.model_dump()) <= {
        field.name for field in fields(VideoGenerationRequest)
    }
    assert request.adapter_parameters.external_task_id.startswith("creative-")
    assert request.adapter_parameters.fallback_mode == "disabled"


@pytest.mark.parametrize("kind", ["image", "video"])
async def test_contract_is_deeply_frozen_and_serialized_copies_cannot_change_it(workflow, kind):
    flow, task = await _ready(workflow, kind)
    async with flow.app.state.database.session_factory() as session:
        request = await _compile(session, flow, task, kind)
    for target, field, value in (
        (request, "actual_submitted", True),
        (request.locked_prompt, "prompt", "rewritten"),
        (request.canonical_product, "object_key", "replacement"),
        (request.source_mapping, "candidate_id", "replacement"),
        (request.references[0], "sha256", "a" * 64),
        (request.adapter_parameters, "prompt", "rewritten"),
        (request.options, "provider", "replacement"),
    ):
        with pytest.raises(ValidationError):
            setattr(target, field, value)
    assert isinstance(request.references, tuple)
    detached = request.model_dump(mode="json")
    detached["references"][0]["object_key"] = "replacement"
    assert request.references[0].object_key != "replacement"
    changed = request.model_dump(mode="json")
    changed["provider_submission_allowed"] = True
    with pytest.raises(ValidationError):
        type(request).model_validate(changed)


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize(
    "mutation",
    [
        "prompt", "preservation", "owner", "product_owner", "review", "selection",
        "revoked", "materialized", "unknown", "stopped", "expired", "authorization",
        "source_hash", "source_status", "source_mapping", "ordinary_qualification",
    ],
)
async def test_locked_inputs_permissions_review_and_media_changes_invalidate_old_request(
    workflow, kind, mutation
):
    flow, task = await _ready(workflow, kind)
    owner_id = uuid.UUID(flow.settings.dev_user_id)
    async with flow.app.state.database.session_factory() as session:
        request = await _compile(session, flow, task, kind)
        snapshot = deepcopy(task.snapshot_json)
        package = snapshot["package"] if kind == "image" else (
            snapshot["storyboard"]["packages"]["SHOT_01"]
        )
        review = snapshot["latest_review"] if kind == "image" else (
            snapshot["storyboard"]["latest_reviews"]["SHOT_01"]
        )
        if mutation == "prompt":
            package["prompt"] += " rewritten"
        elif mutation == "preservation":
            package["preservation_hash"] = "a" * 64
        elif mutation == "owner":
            snapshot["asset"]["owner_id"] = str(uuid.uuid4())
        elif mutation == "product_owner":
            await session.execute(
                update(Product).where(Product.id == task.product_id).values(user_id=uuid.uuid4())
            )
            await session.commit()
        elif mutation == "review":
            review["decision"] = "REJECTED"
        elif mutation == "selection":
            if kind == "image":
                snapshot.pop("selection")
            else:
                snapshot["storyboard"]["selections"].pop("SHOT_01")
        elif mutation == "revoked":
            snapshot["asset"]["revoked"] = True
        elif mutation == "materialized":
            snapshot["asset"]["materialized"] = False
        elif mutation == "unknown":
            snapshot["execution_state"] = "UNKNOWN"
        elif mutation == "stopped":
            snapshot["stopped"] = True
        elif mutation == "expired":
            package["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        elif mutation == "authorization":
            snapshot["authorization"]["locks_hash"] = "a" * 64
        elif mutation == "source_hash":
            await session.execute(update(ImageGenerationOutput).where(
                ImageGenerationOutput.id == uuid.UUID(request.source_mapping.output_id)
            ).values(sha256="a" * 64))
            await session.commit()
        elif mutation == "source_status":
            await session.execute(update(ImageGenerationItem).where(
                ImageGenerationItem.id == uuid.UUID(request.source_mapping.item_id)
            ).values(status="UNKNOWN"))
            await session.commit()
        elif mutation == "source_mapping":
            candidate = snapshot["candidates"][0] if kind == "image" else (
                snapshot["storyboard"]["candidates"][0]
            )
            candidate["output_id"] = str(uuid.uuid4())
        else:
            await session.execute(update(ImageGenerationOutput).where(
                ImageGenerationOutput.id == uuid.UUID(request.source_mapping.output_id)
            ).values(qualification_status=QualityDecisionStatus.QUALIFIED))
            await session.commit()
        task.snapshot_json = snapshot
        await _save_task(flow.app, task)
        with pytest.raises(CreativeProviderRequestRejected):
            await assert_creative_provider_request_current(
                session, task, request, owner_id=owner_id,
                object_store=flow.app.state.object_store,
            )


@pytest.mark.parametrize("kind", ["image", "video"])
async def test_valid_metadata_change_recompiles_same_identity_but_invalidates_old_hash(
    workflow, kind
):
    flow, task = await _ready(workflow, kind)
    async with flow.app.state.database.session_factory() as session:
        request = await _compile(session, flow, task, kind)
        await session.execute(update(ImageGenerationOutput).where(
            ImageGenerationOutput.id == uuid.UUID(request.source_mapping.output_id)
        ).values(review_notes="changed without a CreativeTask version bump"))
        await session.commit()
        current = await _compile(session, flow, task, kind)
        assert current.idempotency_key == request.idempotency_key
        assert current.request_hash != request.request_hash
        assert current.evidence_hash != request.evidence_hash
        with pytest.raises(CreativeProviderRequestRejected) as rejected:
            await assert_creative_provider_request_current(
                session, task, request, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=flow.app.state.object_store,
            )
        assert rejected.value.code == "PROVIDER_REQUEST_STALE"


@pytest.mark.parametrize("kind", ["image", "video"])
async def test_expired_authorization_and_wrong_caller_reject_replay(workflow, kind):
    flow, task = await _ready(workflow, kind)
    async with flow.app.state.database.session_factory() as session:
        request = await _compile(session, flow, task, kind)
        with pytest.raises(CreativeProviderRequestRejected) as expired:
            await assert_creative_provider_request_current(
                session, task, request, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=flow.app.state.object_store,
                now=datetime.now(UTC) + timedelta(hours=2),
            )
        assert expired.value.code == (
            "AUTH_EXPIRED" if kind == "image" else "AUTHORIZATION_SCOPE_INVALID"
        )
        with pytest.raises(CreativeProviderRequestRejected) as denied:
            await assert_creative_provider_request_current(
                session, task, request, owner_id=uuid.uuid4(),
                object_store=flow.app.state.object_store,
            )
        assert denied.value.code == "PROVIDER_REQUEST_STALE"


@pytest.mark.parametrize("kind", ["image", "video"])
async def test_missing_or_changed_bytes_reject_replay(workflow, kind):
    flow, task = await _ready(workflow, kind)
    async with flow.app.state.database.session_factory() as session:
        request = await _compile(session, flow, task, kind)
        key = request.canonical_product.object_key
        path = await flow.app.state.object_store.localize(key, Path(flow.settings.artifact_root))
        original = path.read_bytes()
        path.write_bytes(b"changed bytes")
        with pytest.raises(CreativeProviderRequestRejected) as changed:
            await assert_creative_provider_request_current(
                session, task, request, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=flow.app.state.object_store,
            )
        assert changed.value.code == "ASSET_HASH_MISMATCH"
        path.write_bytes(original)
        path.unlink()
        with pytest.raises(CreativeProviderRequestRejected) as missing:
            await assert_creative_provider_request_current(
                session, task, request, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=flow.app.state.object_store,
            )
        assert missing.value.code == "ASSET_MISSING"


async def test_adapter_options_change_request_hash_and_hash_tampering_cannot_replay(workflow):
    flow, task = await _ready(workflow, "image")
    async with flow.app.state.database.session_factory() as session:
        request = await _compile(session, flow, task, "image")
        changed = await _compile(session, flow, task, "image", options=ImageProviderOptions(
            provider="nanobanana", resolution="4k"
        ))
        assert changed.idempotency_key == request.idempotency_key
        assert changed.request_hash != request.request_hash
        forged = request.model_copy(update={"request_hash": "f" * 64})
        with pytest.raises(CreativeProviderRequestRejected) as rejected:
            await assert_creative_provider_request_current(
                session, task, forged, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=flow.app.state.object_store,
            )
        assert rejected.value.code == "PROVIDER_REQUEST_STALE"
    assert isinstance(request, CreativeImageProviderRequest)


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize("mutation", ["state_version", "version_license", "owner_inactive"])
async def test_version_or_account_state_is_rechecked_from_database(workflow, kind, mutation):
    flow, task = await _ready(workflow, kind)
    async with flow.app.state.database.session_factory() as session:
        request = await _compile(session, flow, task, kind)
        if mutation == "state_version":
            task.state_version += 1
            await _save_task(flow.app, task)
        elif mutation == "version_license":
            await session.execute(update(ProductVersion).where(
                ProductVersion.id == uuid.UUID(request.canonical_product.product_version_id)
            ).values(license_status=ProductLicenseStatus.VERIFIED))
            await session.commit()
        else:
            await session.execute(update(User).where(
                User.id == uuid.UUID(flow.settings.dev_user_id)
            ).values(is_active=False))
            await session.commit()
        with pytest.raises(CreativeProviderRequestRejected) as rejected:
            await assert_creative_provider_request_current(
                session, task, request, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=flow.app.state.object_store,
            )
        assert rejected.value.code == (
            "OWNER_INACTIVE" if mutation == "owner_inactive" else "PROVIDER_REQUEST_STALE"
        )


async def test_image_stored_contract_cannot_replace_the_active_locked_prompt(workflow):
    flow, task = await _ready(workflow, "image")
    async with flow.app.state.database.session_factory() as session:
        request = await _compile(session, flow, task, "image")
        snapshot = deepcopy(task.snapshot_json)
        frozen = snapshot["package_contracts"][request.package_revision_id]["text_contract"]
        frozen["package"]["prompt"] = "Forged Provider prompt"
        frozen["contract_hash"] = digest({
            key: value for key, value in frozen.items() if key != "contract_hash"
        })
        task.snapshot_json = snapshot
        await _save_task(flow.app, task)
        with pytest.raises(CreativeProviderRequestRejected) as rejected:
            await _compile(session, flow, task, "image")
        assert rejected.value.code == "TEXT_CONTRACT_REJECTED"


@pytest.mark.parametrize("mutation", ["missing", "bytes"])
async def test_video_checks_storyboard_object_bytes_separately_from_canonical_product(
    workflow, mutation
):
    flow, task = await _ready(workflow, "video")
    store = flow.app.state.object_store
    canonical_key = task.snapshot_json["asset"]["object_key"]
    original = await store.localize(canonical_key, flow.settings.artifact_root / "unused")
    new_key = await store.put_file(original, "isolated/storyboard.png", "image/png")
    snapshot = deepcopy(task.snapshot_json)
    candidate = snapshot["storyboard"]["candidates"][0]
    candidate["object_key"] = new_key
    task.snapshot_json = snapshot
    await _save_task(flow.app, task)
    async with flow.app.state.database.session_factory() as session:
        await session.execute(update(ImageGenerationOutput).where(
            ImageGenerationOutput.id == uuid.UUID(candidate["output_id"])
        ).values(object_key=new_key))
        await session.commit()
        request = await _compile(session, flow, task, "video")
        assert request.references[1].object_key == new_key
        assert request.canonical_product.object_key == canonical_key
        if mutation == "missing":
            await store.delete(new_key)
        else:
            path = await store.localize(new_key, flow.settings.artifact_root / "unused")
            path.write_bytes(b"wrong storyboard bytes")
        with pytest.raises(CreativeProviderRequestRejected) as rejected:
            await assert_creative_provider_request_current(
                session, task, request, owner_id=uuid.UUID(flow.settings.dev_user_id),
                object_store=store,
            )
        assert rejected.value.code == (
            "REFERENCE_MISSING" if mutation == "missing" else "REFERENCE_HASH_MISMATCH"
        )
        assert await store.exists(canonical_key)


def test_provider_options_reject_fake_replay_and_unbounded_or_unknown_fields():
    for value in (
        {"provider": "fake"}, {"provider": "replay"},
        {"provider": "nanobanana", "quality": "high"},
        {"provider": "gpt", "prompt": "overwrite locked content"},
    ):
        with pytest.raises(ValidationError):
            ImageProviderOptions.model_validate(value)
    for value in (
        {"provider": "fake", "model": "fake"},
        {"provider": "kling_official_api", "model": "", "duration": 5},
        {"provider": "kling_official_api", "model": "kling-v3-omni", "duration": 100},
        {"provider": "kling_official_api", "model": "kling-v3-omni", "multi_shot": True},
    ):
        with pytest.raises(ValidationError):
            VideoProviderOptions.model_validate(value)
    assert CreativeVideoProviderRequest.model_fields["execution_mode"].default == "director_fixed"
