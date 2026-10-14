from __future__ import annotations

import hashlib
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import test_creative_provider_preflight as preflight_tests
from libtv_agent.adapters.kling_official_api import KlingOfficialApiAdapter
from libtv_agent.creative.visual_plan import (
    VisualPlan,
    compile_visual_video_prompt,
    storyboard_keyframes,
)
from libtv_agent.domain.models import StagedUpload
from libtv_agent.services.creative_provider_executor import (
    CreativeExecutionControls,
    CreativeProviderExecutionRejected,
    _assert_image_contract,
    execute_creative_image,
)
from libtv_agent.services.creative_provider_preflight import (
    CreativeProviderPreflightRejected,
    _assert_capability,
    _materialize,
    preflight_creative_provider_request,
)
from libtv_agent.services.creative_provider_requests import (
    CreativeProviderRequestRejected,
    VideoProviderOptions,
    assert_creative_provider_request_current,
    compile_creative_image_request,
    compile_creative_video_request,
)
from libtv_agent.services.creative_provider_submission_persistence import (
    DurableSubmissionTicketStore,
    admit_provider_submission_durable,
)
from libtv_agent.services.creative_video_provider_adapter import bind_creative_video_adapter_request
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import update
from test_creative_provider_preflight import _capability
from test_creative_provider_requests import _counts
from test_creative_video_bridge import Flow, _task
from test_creative_video_bridge import workflow as workflow  # noqa: F401
from test_director_visual_plan import beat, moment, visual


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline keyframe tests must not access a Provider or network")

    for target in (
        "libtv_agent.adapters.kling_official_api.KlingOfficialApiAdapter.submit",
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.upload_media",
        "libtv_agent.adapters.wavespeed.WaveSpeedAdapter.submit_prediction",
    ):
        monkeypatch.setattr(target, forbidden)


def image_bytes(color):
    buffer = io.BytesIO()
    Image.new("RGB", (320, 480), color).save(buffer, "PNG")
    return buffer.getvalue()


class KeyframeFlow(Flow):
    async def start(self, beats, *, views=()):
        response = await self.client.post(
            "/api/v1/products", headers=self.headers,
            json={"internalSkuId": str(uuid.uuid4())},
        )
        assert response.status_code == 201, response.text
        product_id = response.json()["id"]
        front = image_bytes("red")
        sources = [
            f"creative-offline/{self.settings.dev_user_id}/{hashlib.sha256(front).hexdigest()}",
        ]
        uploads = {}
        for view in views:
            response = await self.client.post(
                "/api/v1/uploads",
                headers={**self.headers, "Idempotency-Key": str(uuid.uuid4())},
                files={"file": (f"{view}.png", image_bytes("green"), "image/png")},
            )
            assert response.status_code == 201, response.text
            upload_id = uuid.UUID(response.json()["id"])
            async with self.app.state.database.session_factory() as session:
                upload = await session.get(StagedUpload, upload_id)
                sources.append(upload.object_key)
            uploads[view] = str(upload_id)
        response = await self.client.post(
            f"/api/v1/products/{product_id}/versions", headers=self.headers,
            json={"sourceType": "USER_UPLOAD", "sourceAssetReferences": sources,
                  "truthFields": {"product_view_uploads": uploads}},
        )
        assert response.status_code == 201, response.text
        response = await self.client.post(
            "/api/v1/creative-workflow/tasks", headers=self.headers,
            data={"product_id": product_id, "product_version_id": response.json()["id"]},
            files={"front": ("front.png", front, "image/png")},
        )
        assert response.status_code == 201, response.text
        self.task_id = response.json()["id"]
        await self.command("analyze")
        await self.command("select_direction", direction_id="A", script_beats=beats)
        self.first_package = self.result["snapshot"]["package"]

    async def materialize(self, slot="FIRST_FRAME"):
        snapshot = self.result["snapshot"]
        parent = snapshot.get("authorization", {}).get("authorization_id")
        auth = {
            "authorization_id": str(uuid.uuid4()),
            "package_id": self.first_package["package_id"],
            "locks_hash": self.first_package["locks_hash"],
            "scope": "FIRST_FRAME" if slot == "FIRST_FRAME" else "VIDEO_STORYBOARD",
            "shot_ids": [slot],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "max_calls": 6, "max_cost_micros": 100, "total_task_cap_micros": 100,
            **({"parent_authorization_id": parent} if parent else {}),
        }
        await self.command("authorize", authorization=auth)
        package = (
            self.first_package if slot == "FIRST_FRAME" else
            self.result["snapshot"]["storyboard"]["packages"][slot]
        )
        await self.command("generate", package_id=package["package_id"], shot_id=slot)
        snapshot = self.result["snapshot"]
        candidate = (
            snapshot["candidates"][-1] if slot == "FIRST_FRAME" else
            snapshot["storyboard"]["candidates"][-1]
        )
        await self.command(
            "review", candidate_id=candidate["candidate_id"], decision="QUALIFIED", shot_id=slot,
        )
        await self.command("select", candidate_id=candidate["candidate_id"], shot_id=slot)
        return candidate

    async def ready_script(self, beats, *, views=()):
        await self.start(beats, views=views)
        await self.materialize()
        slots = storyboard_keyframes(VisualPlan.model_validate(self.first_package["visual_plan"]))
        for slot in slots:
            await self.materialize(slot)

    async def compile_video(self, **overrides):
        task = await _task(self.app, self.task_id)
        plan = VisualPlan.model_validate(self.first_package["visual_plan"])
        options = VideoProviderOptions(
            provider="kling_official_api", model="kling-3.0-omni", resolution="1080p",
            **{"duration": int(sum(b.duration_seconds for b in plan.beats)),
               "multi_shot": len(plan.shots) > 1, **overrides},
        )
        async with self.app.state.database.session_factory() as session:
            counts = await _counts(session)
            request = await compile_creative_video_request(
                session, task, owner_id=task.user_id, object_store=self.app.state.object_store,
                options=options,
            )
            assert counts == await _counts(session)
            repeated = await assert_creative_provider_request_current(
                session, task, request, owner_id=task.user_id,
                object_store=self.app.state.object_store,
            )
            assert repeated == request
        return request


def three_key_script():
    return [
        beat("B01", moment(), duration_seconds=4),
        beat("B02", moment(framing="print closeup"), duration_seconds=4, cut_before=True),
        beat("B03", moment(scene="street"), duration_seconds=4, cut_before=True),
    ]


async def test_three_keyframes_have_individual_prompts_review_lineage_and_real_wire_order(
    workflow, tmp_path,
):
    flow = KeyframeFlow(*workflow)
    await flow.ready_script(three_key_script())
    snapshot = flow.result["snapshot"]
    assert snapshot["storyboard"]["packages"]["SHOT_01"]["keyframe_id"] == "K02"
    assert snapshot["storyboard"]["packages"]["SHOT_02"]["keyframe_id"] == "K03"
    assert "print closeup" in snapshot["storyboard"]["packages"]["SHOT_01"]["prompt"]
    assert "street" in snapshot["storyboard"]["packages"]["SHOT_02"]["prompt"]
    assert "bookshop" not in snapshot["storyboard"]["packages"]["SHOT_02"]["prompt"]
    assert "plain studio" not in flow.first_package["prompt"]
    request = await flow.compile_video()
    assert [r.keyframe_id for r in request.references] == ["K01", "K02", "K03", None]
    assert [r.order for r in request.references] == [1, 2, 3, 4]
    assert "S03 8-12s" in request.adapter_parameters.prompt
    assert "@image_3" in request.adapter_parameters.prompt
    assert request.adapter_parameters.multi_shot
    cap = _capability(request)
    with pytest.raises(CreativeProviderPreflightRejected, match="MULTI_SHOT_CAPABILITY_REQUIRED"):
        _assert_capability(request, cap)
    _assert_capability(request, cap.model_copy(update={"supports_multi_shot": True}))
    lease, inputs, _ = await _materialize(request, flow.app.state.object_store)
    try:
        assert all(entry.path.suffix == ".png" for entry in inputs)
        adapter_request = bind_creative_video_adapter_request(request, inputs)
        adapter = KlingOfficialApiAdapter(flow.settings)
        payload = await adapter.build_request_payload(adapter_request)
        assert payload["settings"]["multi_shot"] is True
        assert [c["id"] for c in payload["contents"][1:]] == [
            "image_1", "image_2", "image_3", "image_4",
        ]
        assert [c["type"] for c in payload["contents"][1:]] == [
            "first_frame", "refer_image", "refer_image", "refer_image",
        ]
        with pytest.raises(CreativeProviderRequestRejected, match="REFERENCE_BINDINGS_INVALID"):
            bind_creative_video_adapter_request(request, (inputs[1], inputs[0], *inputs[2:]))
        with pytest.raises(CreativeProviderRequestRejected, match="REFERENCE_BINDINGS_INVALID"):
            bind_creative_video_adapter_request(request, inputs[:-1])
        inputs[1].path.write_bytes(b"altered")
        with pytest.raises(CreativeProviderRequestRejected, match="REFERENCE_HASH_MISMATCH"):
            bind_creative_video_adapter_request(request, inputs)
    finally:
        lease.cleanup()


async def test_single_keyframe_does_not_require_redundant_storyboard_generation(workflow):
    flow = KeyframeFlow(*workflow)
    await flow.ready_script([beat(duration_seconds=12)])
    assert flow.result["snapshot"]["storyboard"]["candidates"] == []
    request = await flow.compile_video()
    assert [r.role for r in request.references] == ["FIRST_FRAME", "PRODUCT"]
    assert request.adapter_parameters.multi_shot is False


async def test_side_to_front_one_shot_binds_original_side_and_timed_print_lock(workflow):
    flow = KeyframeFlow(*workflow)
    await flow.ready_script([beat(
        "B01", moment(garment_view="side"), moment(), duration_seconds=12,
        action="turn from side to front", moment_offsets_seconds=[0, 6],
    )], views=("side",))
    request = await flow.compile_video()
    assert request.adapter_parameters.multi_shot is False
    assert [r.role for r in request.references] == [
        "FIRST_FRAME", "STORYBOARD", "PRODUCT", "PRODUCT",
    ]
    assert "product_lock=@image_2 at 6s" in request.adapter_parameters.prompt
    assert "original side product design" in request.adapter_parameters.prompt
    assert [r.product_view for r in request.references] == [None, None, "front", "side"]
    task = await _task(flow.app, flow.task_id)
    async with flow.app.state.database.session_factory() as session:
        image = await compile_creative_image_request(
            session, task, owner_id=task.user_id, object_store=flow.app.state.object_store,
            shot_id="SHOT_01",
        )
    assert [r.role for r in image.references] == ["PRODUCT", "PRODUCT", "FIRST_FRAME"]
    assert "Reference image 2 is original side garment design" in image.locked_prompt.prompt
    assert "Reference image 3 is the approved person/outfit" in image.locked_prompt.prompt
    _assert_capability(image, _capability(image))
    assert image.adapter_parameters.prompt == image.locked_prompt.prompt


async def test_missing_keyframe_review_and_wrong_slot_cannot_reach_video(workflow):
    flow = KeyframeFlow(*workflow)
    await flow.start(three_key_script())
    await flow.materialize()
    await flow.materialize("SHOT_01")
    with pytest.raises(CreativeProviderRequestRejected, match="PACKAGE_REQUIRED"):
        await flow.compile_video()
    candidate = await flow.materialize("SHOT_02")
    await flow.command(
        "review", candidate_id=candidate["candidate_id"], decision="REJECTED",
        reason="print is unreadable", shot_id="SHOT_02",
    )
    with pytest.raises(CreativeProviderRequestRejected, match="SELECTION_REQUIRED"):
        await flow.compile_video()
    response = await flow.command(
        "authorize", expected_status=422,
        authorization={
            **flow.result["snapshot"]["authorization"],
            "authorization_id": str(uuid.uuid4()), "shot_ids": ["SHOT_03"],
        },
    )
    assert response.json()["detail"]["code"] == "SHOT_ID_UNSUPPORTED"


async def test_timing_and_multishot_mode_cannot_be_silently_reinterpreted(workflow):
    flow = KeyframeFlow(*workflow)
    await flow.ready_script(three_key_script())
    with pytest.raises(CreativeProviderRequestRejected, match="VIDEO_DURATION_MISMATCH"):
        await flow.compile_video(duration=5)
    with pytest.raises(CreativeProviderRequestRejected, match="VIDEO_SHOT_MODE_MISMATCH"):
        await flow.compile_video(multi_shot=False)


async def test_multi_keyframe_full_preflight_is_read_only_and_preserves_all_inputs(
    workflow, tmp_path, monkeypatch,
):
    flow = KeyframeFlow(*workflow)
    await flow.ready_script(three_key_script())

    async def ready(*args, **kwargs):
        return flow, await _task(flow.app, flow.task_id)

    monkeypatch.setattr(preflight_tests, "_ready", ready)
    _, task, request, _, inputs = await preflight_tests._prepared(
        workflow, tmp_path, "video", video_options=VideoProviderOptions(
            provider="kling_official_api", model="kling-3.0-omni", resolution="1080p",
            duration=12, multi_shot=True,
        ),
    )
    inputs["capability"] = inputs["capability"].model_copy(update={"supports_multi_shot": True})
    async with flow.app.state.database.session_factory() as session:
        before = await _counts(session)
        prepared = await preflight_creative_provider_request(session, task, request, **inputs)
        async with prepared as lease:
            assert len(lease.materialized_inputs) == 4
            assert lease.actual_submitted is False
            assert lease.provider_submission_allowed is False
            adapter_request = bind_creative_video_adapter_request(
                request, lease.materialized_inputs,
            )
            assert len(adapter_request.refer_image_paths) == 2
        assert before == await _counts(session)
    assert all(not entry.path.exists() for entry in lease.materialized_inputs)


async def test_supplemental_image_executor_preserves_slot_ticket_and_reference_order(
    workflow, tmp_path, monkeypatch,
):
    flow = KeyframeFlow(*workflow)
    await flow.ready_script(three_key_script())

    async def ready(*args, **kwargs):
        return flow, await _task(flow.app, flow.task_id)

    async def compile_image(session, current_flow, task, kind, **kwargs):
        assert kind == "image"
        return await compile_creative_image_request(
            session, task, owner_id=task.user_id, object_store=flow.app.state.object_store,
            shot_id="SHOT_02", **kwargs,
        )

    monkeypatch.setattr(preflight_tests, "_ready", ready)
    monkeypatch.setattr(preflight_tests, "_compile", compile_image)
    _, task, request, approval, inputs = await preflight_tests._prepared(
        workflow, tmp_path, "image",
    )
    uploaded, submitted = [], []

    class LocalAdapter:
        is_test_double = True

        async def upload_media(self, source, **kwargs):
            uploaded.append(hashlib.sha256(source.read_bytes()).hexdigest())
            return f"https://test.invalid/{len(uploaded)}.png"

        async def submit_prediction(self, model, payload, **kwargs):
            submitted.append(payload)
            return {"id": "local-test-only"}

    async with flow.app.state.database.session_factory() as session:
        prepared = await preflight_creative_provider_request(session, task, request, **inputs)
        async with prepared:
            claim = await admit_provider_submission_durable(
                session, prepared, current_preflight=prepared,
                approval=approval, store=DurableSubmissionTicketStore(), now=inputs["now"],
            )
            await session.commit()
            with pytest.raises(CreativeProviderExecutionRejected, match="IMAGE_SLOT_MISMATCH"):
                _assert_image_contract(
                    claim.ticket.model_copy(update={"shot_id": "SHOT_01"}),
                    request, prepared.result, now=inputs["now"],
                )
            before = await _counts(session)
            result = await execute_creative_image(
                session, task=task, request=request, ticket=claim.ticket,
                preflight=prepared.result, owner_id=task.user_id,
                object_store=flow.app.state.object_store, settings=inputs["settings"],
                controls=CreativeExecutionControls(mode="test-double"),
                adapter=LocalAdapter(), now=inputs["now"],
            )
            assert before == await _counts(session)
    assert request.shot_id == claim.ticket.shot_id == "SHOT_02"
    assert result.ticket_id == claim.ticket.ticket_id
    assert result.status == "TEST_DOUBLE" and result.actual_submitted is False
    assert uploaded == [ref.sha256 for ref in request.references]
    assert submitted[0]["prompt"] == request.locked_prompt.prompt
    assert submitted[0]["images"] == ["https://test.invalid/1.png", "https://test.invalid/2.png"]


@pytest.mark.parametrize("mutation", ["owner", "generated", "unregistered"])
async def test_original_product_view_evidence_cannot_be_replaced(workflow, mutation):
    flow = KeyframeFlow(*workflow)
    await flow.ready_script([beat(
        "B01", moment(), moment(garment_view="back"), duration_seconds=12,
        moment_offsets_seconds=[0, 6],
    )], views=("back",))
    asset = flow.result["snapshot"]["plan"]["product_reference_assets"]["back"]
    upload_id = uuid.UUID(asset["upload_id"])
    async with flow.app.state.database.session_factory() as session:
        upload = await session.get(StagedUpload, upload_id)
        if mutation == "owner":
            values = {"user_id": uuid.uuid4()}
        elif mutation == "generated":
            candidate = flow.result["snapshot"]["candidates"][0]
            values = {"source_image_output_id": uuid.UUID(candidate["output_id"])}
        else:
            values = {"object_key": "not-registered.png"}
        await session.execute(
            update(StagedUpload).where(StagedUpload.id == upload.id).values(**values),
        )
        await session.commit()
    with pytest.raises(CreativeProviderRequestRejected, match="PRODUCT_VIEW_REFERENCE_STALE"):
        await flow.compile_video()


def test_moment_timing_is_validated_and_required_at_submission():
    from libtv_agent.creative.visual_plan import VisualPlanRejected, assert_visual_inputs

    for offsets in ([1, 3], [0], [0, -1], [0, 8], [0, float("nan")]):
        with pytest.raises(ValidationError):
            visual(beat("B01", moment(), moment(hands=["book"]), moment_offsets_seconds=offsets))
    result = visual(beat("B01", moment(), moment(hands=["book"])))
    with pytest.raises(VisualPlanRejected, match="KEYFRAME_TIMING_REQUIRED"):
        assert_visual_inputs(
            result, {"K01": 1, "K02": 2}, actual_slot_count=3, profile="kling",
        )


def test_expressions_do_not_force_images_and_split_reasons_remain_auditable():
    result = visual(beat(), beat("B02", moment(expression="small smile")))
    assert len(result.keyframes) == 1
    assert all(b.reason == "motion_start" for b in result.bindings)
    assert "expression: small smile" in compile_visual_video_prompt(result, duration_seconds=8)
    result = visual(beat(), beat("B02", moment(framing="closeup"), cut_before=True))
    assert result.shots[1].split_reasons == ("explicit_cut", "framing")
