"""Synthetic HTTP acceptance only; neither product understanding nor real production."""
from __future__ import annotations

import hashlib
import io
import json
import uuid
from copy import deepcopy

import pytest
from libtv_agent.creative.package_contract import (
    render_creative_package_text,
    serialize_creative_package,
)
from libtv_agent.domain.enums import QualityDecisionStatus
from libtv_agent.domain.models import (
    AuditEvent,
    CreativeRecord,
    CreativeTask,
    GenerationAttempt,
    ImageGenerationBatch,
    ImageGenerationItem,
    ImageGenerationOutput,
    ImageQuotaReservation,
    ParentTask,
    PointsLedger,
    PointsReservation,
)
from libtv_agent.services.creative_video_bridge import plan_creative_video_bridge
from PIL import Image, ImageDraw
from sqlalchemy import func, select
from test_creative_brand_dna_integration import profile_for
from test_creative_package_export_api import FIELDS
from test_creative_video_bridge import Flow as VideoFlow
from test_creative_video_bridge import _task
from test_creative_workflow import Flow
from test_creative_workflow import workflow as workflow  # noqa: F401
from test_human_production_reviews import payload, query

REAL_EXECUTION_MODELS = (
    GenerationAttempt, ParentTask, ImageQuotaReservation, PointsReservation, PointsLedger,
)


async def row_counts(session, models):
    return {
        model.__name__: await session.scalar(select(func.count()).select_from(model))
        for model in models
    }


async def create_synthetic_jersey(flow):
    image = Image.new("RGB", (96, 128), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [(28, 12), (38, 8), (58, 8), (68, 12), (88, 34), (72, 48),
         (66, 38), (66, 116), (30, 116), (30, 38), (24, 48), (8, 34)],
        fill="red", outline="black",
    )
    draw.rectangle((42, 42, 48, 77), fill="white")
    draw.rectangle((53, 42, 59, 77), fill="white")
    front = io.BytesIO()
    image.save(front, "PNG")
    source_hash = hashlib.sha256(front.getvalue()).hexdigest()

    profile = await profile_for(flow)
    scenes = ["bedroom mirror", "vintage bookstore", "night street"]
    profile.update(
        audience="Synthetic test configuration: adult jersey audience",
        preferredEnvironment=scenes,
    )
    saved = await flow.client.put(
        "/api/v1/site-style-profiles/geeksoutfit", headers=flow.headers, json=profile,
    )
    assert saved.status_code == 200, saved.text
    brand = saved.json()
    product = await flow.client.post(
        "/api/v1/products", headers=flow.headers,
        json={"internalSkuId": f"synthetic-jersey-{uuid.uuid4()}"},
    )
    assert product.status_code == 201, product.text
    flow.product_id = product.json()["id"]
    created = await flow.client.post(
        "/api/v1/creative-workflow/tasks", headers=flow.headers,
        data={
            "product_id": flow.product_id, "brand_profile_id": brand["id"],
            "brand_profile_version": brand["version"],
        },
        files={"front": ("synthetic-jersey-front.png", front.getvalue(), "image/png")},
    )
    assert created.status_code == 201, created.text
    flow.task_id, flow.version = created.json()["id"], 0
    read = await flow.client.get(
        f"/api/v1/creative-workflow/tasks/{flow.task_id}", headers=flow.headers,
    )
    assert read.status_code == 200, read.text
    assert read.json()["snapshot"]["asset"]["sha256"] == source_hash
    assert read.json()["creative_packages"] == {}
    return source_hash, brand, scenes


@pytest.mark.asyncio
@pytest.mark.parametrize("subject_type", ["DIRECTOR_CANDIDATE", "IMAGE_OUTPUT"])
async def test_synthetic_jersey_package_fake_output_and_human_history(workflow, subject_type):
    flow = Flow(*workflow)
    assert flow.settings.app_env == "test"
    assert flow.settings.ai_adapter_mode == "fake"
    assert flow.settings.paid_generation_enabled is False
    source_hash, brand, scenes = await create_synthetic_jersey(flow)
    await flow.command("analyze")
    plan = flow.result["snapshot"]["plan"]
    assert plan["evidence"] == "FAKE_NOT_IMAGE_ANALYSIS"
    assert [direction["id"] for direction in plan["directions"]] == ["A", "B", "C"]
    assert [direction["scene"] for direction in plan["directions"]] == scenes
    assert flow.result["creative_packages"] == {}

    await flow.command("select_direction", direction_id="B")
    flow.package = flow.result["snapshot"]["package"]
    package_id = flow.package["package_id"]
    projection = deepcopy(flow.result["creative_packages"][package_id])
    assert set(projection) == FIELDS | {"provenance", "fieldStatus"}
    assert projection["direction"]["id"] == "B"
    assert projection["imagePrompt"] == flow.package["prompt"]
    assert projection["audience"] == brand["audience"]
    assert projection["fieldStatus"]["audience"] == "PROPOSED"
    assert set(projection["fieldStatus"]) == FIELDS
    assert all(
        item["status"] == "UNVERIFIED" for item in projection["qualityChecklist"]
    )
    provenance = projection["provenance"]
    assert provenance["sourceHash"] == source_hash
    assert provenance["sourcePackage"] == flow.package
    assert provenance["locksHash"] == flow.package["locks_hash"]
    assert provenance["preservationHash"] == flow.package["preservation_hash"]
    assert provenance["brandDNA"] == flow.result["snapshot"]["plan"]["brand_dna"]
    assert provenance["brandDNA"]["profileVersion"] == brand["version"]
    assert provenance["originEvidence"]["planEvidence"] == "FAKE_NOT_IMAGE_ANALYSIS"
    assert provenance["synthetic"] is True
    assert provenance["qualificationScope"] == "OFFLINE_SYNTHETIC_ONLY"
    assert provenance["qualified"] is provenance["deliverable"] is False
    assert provenance["providerSubmissionAllowed"] is False
    assert [shot["shotId"] for shot in projection["shotPlan"]] == ["FIRST_FRAME"]
    assert json.loads(serialize_creative_package(projection)) == projection
    exported_text = render_creative_package_text(projection)
    assert flow.package["prompt"] in exported_text
    assert "OFFLINE_SYNTHETIC_ONLY" in exported_text
    # A copyable video draft may be proposed, but must never claim executed analysis.
    if projection["videoPrompt"] is None:
        assert projection["fieldStatus"]["videoPrompt"] == "UNRESOLVED"
    else:
        assert projection["fieldStatus"]["videoPrompt"] == "PROPOSED"
        assert "FAKE SOURCE" in projection["videoPrompt"]
        assert "requires human confirmation" in projection["videoPrompt"]

    await flow.authorize()
    await flow.generate()
    snapshot = deepcopy(flow.result["snapshot"])
    candidate = snapshot["candidates"][0]
    assert len(snapshot["candidates"]) == 1
    assert candidate["purpose"] == candidate["shot_id"] == "FIRST_FRAME"
    assert candidate["package_id"] == package_id
    assert candidate["sha256"] == source_hash
    assert candidate["synthetic"] is True
    assert candidate["qualified"] is False
    assert candidate["media_evidence"] == "CANONICAL_COPY_PLACEHOLDER_NOT_GENERATED"
    async with flow.app.state.database.session_factory() as session:
        batch = await session.get(ImageGenerationBatch, uuid.UUID(candidate["batch_id"]))
        item = await session.get(ImageGenerationItem, uuid.UUID(candidate["item_id"]))
        output = await session.get(ImageGenerationOutput, uuid.UUID(candidate["output_id"]))
        assert item.batch_id == batch.id
        assert output.item_id == item.id
        assert batch.provider == "fake"
        assert item.kind == "CREATIVE_FIRST_FRAME"
        assert item.prompt == flow.package["prompt"]
        assert output.remote_url.startswith("fake://")
        assert output.sha256 == source_hash
        assert output.object_key == candidate["object_key"] == snapshot["asset"]["object_key"]
        for source in (batch.request_json, item.request_json):
            assert source["creativeTaskId"] == flow.task_id
            assert source["packageId"] == package_id
            assert source["packageRevision"] == flow.package["revision"]
            assert source["sourceHash"] == source_hash
            assert source["synthetic"] is True
        quality_before = deepcopy(output.quality_gates_json)
        assert quality_before["deliverableEligible"] is False
        assert quality_before["qualified"] is False

    subject_id = (
        candidate["candidate_id"] if subject_type == "DIRECTOR_CANDIDATE"
        else candidate["output_id"]
    )
    task_id = flow.task_id if subject_type == "DIRECTOR_CANDIDATE" else candidate["batch_id"]
    body = payload(
        subject_type, subject_id, taskId=task_id, expectedOutputHash=source_hash,
    )
    records = []
    for verdict, reasons in (("PASS", []), ("REWORK", ["GARMENT"]), ("FAIL", ["REALISM"])):
        review_body = {
            **body, "reviewKey": f"synthetic-{verdict}", "verdict": verdict,
            "reasonCodes": reasons, "note": "Synthetic fixture observation only",
        }
        response = await flow.client.post(
            "/api/v1/human-reviews", headers=flow.headers, json=review_body,
        )
        assert response.status_code == 201, response.text
        record = response.json()
        assert record["verdict"] == verdict
        assert record["reasonCodes"] == reasons
        assert record["reviewerId"] == flow.settings.dev_user_id
        subject = record["subject"]
        assert subject["subjectId"] == subject_id
        assert subject["taskId"] == task_id
        assert subject["synthetic"] is True
        assert subject["outputHash"] == subject["inputHash"] == source_hash
        assert subject["packageId"] == package_id
        assert subject["packageRevision"] == flow.package["revision"]
        assert subject["promptHash"] == hashlib.sha256(flow.package["prompt"].encode()).hexdigest()
        records.append(record)
        history = await flow.client.get(
            "/api/v1/human-reviews", headers=flow.headers, params=query(body),
        )
        assert history.status_code == 200, history.text
        assert history.json()["reviews"] == records
    replay = await flow.client.post(
        "/api/v1/human-reviews", headers=flow.headers, json=review_body,
    )
    assert replay.status_code == 201, replay.text
    assert replay.json() == records[-1]
    assert len({record["id"] for record in records}) == 3

    exported = await flow.client.get(
        "/api/v1/human-reviews/export", headers=flow.headers, params=query(body),
    )
    assert exported.status_code == 200, exported.text
    assert exported.json() == {
        "schemaVersion": "human-production-review-export.v1",
        "records": [], "excludedSyntheticCount": 3,
    }
    diagnostic = await flow.client.get(
        "/api/v1/human-reviews/export", headers=flow.headers,
        params={**query(body), "includeSynthetic": "true"},
    )
    assert diagnostic.status_code == 200, diagnostic.text
    assert diagnostic.json()["records"] == records
    assert diagnostic.json()["excludedSyntheticCount"] == 0
    read = await flow.client.get(
        f"/api/v1/creative-workflow/tasks/{flow.task_id}", headers=flow.headers,
    )
    assert read.status_code == 200, read.text
    assert read.json()["snapshot"] == snapshot
    assert read.json()["creative_packages"][package_id] == projection
    async with flow.app.state.database.session_factory() as session:
        output = await session.get(ImageGenerationOutput, uuid.UUID(candidate["output_id"]))
        task = await session.get(CreativeTask, uuid.UUID(flow.task_id))
        assert task.snapshot_json == snapshot
        assert output.qualification_status == QualityDecisionStatus.PENDING
        assert output.quality_gates_json == quality_before
        assert output.reviewed_at is None
        events = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.action == "HUMAN_PRODUCTION_REVIEW_V1",
        )))
        assert {str(event.id) for event in events} == {record["id"] for record in records}
        real_counts = await row_counts(session, REAL_EXECUTION_MODELS)
        assert all(count == 0 for count in real_counts.values())


@pytest.mark.asyncio
async def test_existing_offline_video_preflight_keeps_fake_submission_blocked(
    workflow, monkeypatch,
):
    flow = VideoFlow(*workflow)
    # Reuse existing offline review/selection gates without asserting real qualification.
    await flow.ready()
    task = await _task(flow.app, flow.task_id)
    frozen_snapshot = deepcopy(task.snapshot_json)

    def forbidden_legacy_planner(*args, **kwargs):
        pytest.fail("Director video preflight must not run legacy planning or learning")

    monkeypatch.setattr(
        "libtv_agent.services.prompt_compiler.compile_video_plan", forbidden_legacy_planner,
    )
    monkeypatch.setattr(
        "libtv_agent.services.feedback_learning.apply_video_learning", forbidden_legacy_planner,
    )
    async with flow.app.state.database.session_factory() as session:
        models = (
            CreativeRecord, ImageGenerationBatch, ImageGenerationItem,
            ImageGenerationOutput, AuditEvent, *REAL_EXECUTION_MODELS,
        )
        before = await row_counts(session, models)
        plan = await plan_creative_video_bridge(
            session, task, owner_id=uuid.UUID(flow.settings.dev_user_id),
            object_store=flow.app.state.object_store,
        )
        assert await row_counts(session, models) == before
        assert all(before[model.__name__] == 0 for model in REAL_EXECUTION_MODELS)
        outputs = list(await session.scalars(select(ImageGenerationOutput)))
        assert len(outputs) == 2
        assert all(
            output.qualification_status == QualityDecisionStatus.PENDING for output in outputs
        )
        assert all(output.quality_gates_json["deliverableEligible"] is False for output in outputs)
    assert task.snapshot_json == frozen_snapshot
    assert plan.execution_mode == "director_fixed"
    assert plan.shot_id == "SHOT_01"
    assert plan.first_frame.purpose == "FIRST_FRAME"
    assert plan.storyboard.purpose == "VIDEO_STORYBOARD"
    assert plan.offline_synthetic_only is True
    assert plan.provider_submission_allowed is False
    assert plan.deliverable_eligible is False
    assert set(plan.next_steps) == {
        "REAL_VIDEO_PROVIDER_ADAPTER_REQUIRED", "HUMAN_PROVIDER_AUTHORIZATION_REQUIRED",
    }
    assert plan.locked_prompt_preservation.prompt
    assert plan.locked_prompt_preservation.preservation_hash
