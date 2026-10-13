from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from libtv_agent.api.human_reviews import router
from libtv_agent.creative.human_review import HumanReviewRequest
from libtv_agent.db import Database
from libtv_agent.domain.contracts import canonical_json
from libtv_agent.domain.enums import (
    AttemptStatus,
    DownloadStatus,
    GenerationStatus,
    ParentTaskPhase,
    QualityDecisionStatus,
    UserRole,
    ValidationStatus,
    VariantKind,
)
from libtv_agent.domain.models import (
    ApiIdempotencyRecord,
    AuditEvent,
    Base,
    CreativeTask,
    DownloadArtifact,
    GenerationAttempt,
    GenerationFeedback,
    GenerationVariant,
    ImageGenerationBatch,
    ImageGenerationItem,
    ImageGenerationOutput,
    ImageQuotaReservation,
    ParentTask,
    PointsLedger,
    PointsReservation,
    Product,
    User,
    UserSession,
)
from libtv_agent.services import human_reviews
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

OUTPUT_HASH = "a" * 64
NEW_HASH = "b" * 64
INPUT_HASH = "c" * 64
PROMPT_HASH = "d" * 64


def payload(subject_type="IMAGE_OUTPUT", subject_id=None, **changes):
    return {
        "subjectType": subject_type,
        "subjectId": subject_id or str(uuid.uuid4()),
        "reviewKey": "review-1",
        "expectedOutputHash": OUTPUT_HASH,
        "verdict": "PASS",
        "reasonCodes": [],
        "note": None,
        **changes,
    }


@pytest.mark.parametrize("changes", [
    {"subjectType": "UNKNOWN"}, {"subjectId": ""}, {"subjectId": "x" * 151},
    {"subjectId": "  "}, {"reviewKey": ""}, {"reviewKey": "x" * 121},
    {"expectedOutputHash": "not-a-hash"}, {"expectedOutputHash": "z" * 64},
    {"verdict": "APPROVED"}, {"reasonCodes": ["UNSUPPORTED"]},
    {"reasonCodes": ["FACE"]}, {"verdict": "FAIL"}, {"verdict": "REWORK"},
    {"verdict": "FAIL", "reasonCodes": ["OTHER"], "note": "  "},
    {"note": "x" * 256}, {"synthetic": False}, {"reviewerId": str(uuid.uuid4())},
    {"subjectType": "DIRECTOR_CANDIDATE"},
    {"subjectType": "VIDEO_VARIANT", "verdict": "REWORK", "reasonCodes": ["MOTION"]},
    {"subjectType": "VIDEO_VARIANT", "verdict": "FAIL", "reasonCodes": ["FACE"]},
    {"verdict": "FAIL", "reasonCodes": ["MOTION"]},
])
def test_invalid_contract(changes):
    with pytest.raises(ValidationError):
        HumanReviewRequest.model_validate(payload(**changes))


def test_contract_normalization_and_storyboard_is_image():
    request = HumanReviewRequest.model_validate(payload(
        "DIRECTOR_CANDIDATE", "candidate:SHOT_01", taskId=str(uuid.uuid4()),
        expectedOutputHash=OUTPUT_HASH.upper(), verdict="REWORK",
        reasonCodes=["REALISM", "FACE", "FACE"], note="  improve face  ",
    ))
    assert request.expected_output_hash == OUTPUT_HASH
    assert request.reason_codes == ["FACE", "REALISM"]
    assert request.note == "improve face"
    assert request.model_dump(by_alias=True)["subjectType"] == "DIRECTOR_CANDIDATE"


@pytest.mark.parametrize("subject_type,codes", [
    ("IMAGE_OUTPUT", ["FACE", "GARMENT", "REALISM", "SPACE", "LIGHTING", "OTHER"]),
    ("DIRECTOR_CANDIDATE", ["FACE", "GARMENT", "REALISM", "SPACE", "LIGHTING", "OTHER"]),
    ("VIDEO_VARIANT", ["MOTION", "DEFORMATION", "CAMERA", "OTHER"]),
])
def test_complete_reason_sets(subject_type, codes):
    request = HumanReviewRequest.model_validate(payload(
        subject_type, taskId=str(uuid.uuid4()) if subject_type == "DIRECTOR_CANDIDATE" else None,
        verdict="FAIL", reasonCodes=codes, note="human observation",
    ))
    assert request.reason_codes == sorted(codes)


@pytest.fixture
async def review_env(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'reviews.db').as_posix()}")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    ids = {name: uuid.uuid4() for name in (
        "owner", "other", "admin", "auditor", "product", "batch", "item", "image",
        "parent", "variant", "attempt", "artifact", "director", "director2",
    )}
    now = datetime.now(UTC)
    async with database.session_factory() as session:
        for name, role in (
            ("owner", UserRole.USER), ("other", UserRole.USER),
            ("admin", UserRole.ADMIN), ("auditor", UserRole.AUDITOR),
        ):
            session.add(User(
                id=ids[name], username=name, password_hash="unused", role=role,
            ))
        await session.flush()
        session.add(Product(id=ids["product"], user_id=ids["owner"], internal_sku_id="jersey"))
        session.add(ParentTask(
            id=ids["parent"], user_id=ids["owner"], client_task_id="video-task",
            title="video", asset_count=1, phase=ParentTaskPhase.AWAITING_FINAL_APPROVAL,
        ))
        session.add(ImageGenerationBatch(
            id=ids["batch"], user_id=ids["owner"], client_batch_id="batch",
            idempotency_key="batch-key", request_hash=INPUT_HASH, name="image",
            provider="wavespeed", status="COMPLETED", expected_generation_count=1,
            paid_submission_consent_at=now, request_json={
                "packageId": "package-1", "packageRevision": 2, "sourceHash": INPUT_HASH,
            },
        ))
        await session.flush()
        session.add(ImageGenerationItem(
            id=ids["item"], batch_id=ids["batch"], order_no=1, client_task_id="item",
            outfit_id="jersey", outfit_name="jersey", kind="CREATIVE_FIRST_FRAME",
            view="front", label="FIRST_FRAME", prompt="preserve jersey",
            model_id="test-model", status="COMPLETED", request_json={"promptHash": PROMPT_HASH},
        ))
        session.add(GenerationVariant(
            id=ids["variant"], parent_task_id=ids["parent"], variant_type=VariantKind.STABLE,
            prompt_text="slow movement", prompt_hash=PROMPT_HASH,
            ordered_storyboard_assets_hash=INPUT_HASH,
            generation_status=GenerationStatus.SUCCEEDED, download_status=DownloadStatus.READY,
            validation_status=ValidationStatus.PASSED,
            final_approval_status=QualityDecisionStatus.PENDING,
        ))
        await session.flush()
        session.add(ImageGenerationOutput(
            id=ids["image"], item_id=ids["item"], order_no=1,
            remote_url="https://example.invalid/image.png", object_key="outputs/image.png",
            sha256=OUTPUT_HASH, qualification_status=QualityDecisionStatus.PENDING,
        ))
        session.add(GenerationAttempt(
            id=ids["attempt"], variant_id=ids["variant"],
            status=AttemptStatus.SUCCEEDED, provider="kling", created_at=now,
        ))
        await session.flush()
        session.add(DownloadArtifact(
            id=ids["artifact"], attempt_id=ids["attempt"], status=DownloadStatus.READY,
            object_key="outputs/video.mp4", sha256=OUTPUT_HASH, revision=1,
        ))
        for name in ("director", "director2"):
            session.add(CreativeTask(
                id=ids[name], user_id=ids["owner"], product_id=ids["product"],
                status="STORYBOARD_REVIEW", snapshot_json={
                    "asset": {"sha256": INPUT_HASH}, "calls": 2, "cost_micros": 2,
                    "package": {"package_id": "package-frame", "revision": 1, "prompt": "frame"},
                    "candidates": [{
                        "candidate_id": "same-candidate", "shot_id": "FIRST_FRAME",
                        "sha256": OUTPUT_HASH, "object_key": "fake/frame",
                        "package_id": "package-frame", "synthetic": True, "qualified": False,
                    }],
                    "storyboard": {
                        "packages": {"SHOT_01": {
                            "package_id": "package-shot", "revision": 2, "prompt": "shot",
                        }},
                        "candidates": [{
                            "candidate_id": "candidate:SHOT_01", "shot_id": "SHOT_01",
                            "sha256": OUTPUT_HASH, "object_key": "fake/shot",
                            "package_id": "package-shot", "synthetic": True, "qualified": False,
                        }],
                    },
                },
            ))
        await session.commit()
    app = FastAPI()
    app.state.database = database
    app.state.settings = SimpleNamespace(
        ai_adapter_mode="openai", shared_authentication=False, app_env="test",
        dev_user_id=str(ids["owner"]), dev_admin_id=str(ids["admin"]),
    )
    # Exercise routing in isolation; the application router is deliberately untouched.
    app.include_router(router, prefix="/api/v1")
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
        headers={"X-User-Id": str(ids["owner"])},
    ) as client:
        yield SimpleNamespace(
            db=database, ids=ids, app=app, client=client,
            image=payload(subject_id=str(ids["image"])),
            video=payload("VIDEO_VARIANT", str(ids["variant"])),
            director=payload(
                "DIRECTOR_CANDIDATE", "candidate:SHOT_01", taskId=str(ids["director"]),
            ),
        )
    await database.dispose()


def query(body):
    return {key: body[key] for key in ("subjectType", "subjectId", "taskId") if key in body}


async def counts(env):
    async with env.db.session_factory() as session:
        return tuple([
            int(await session.scalar(select(func.count()).select_from(model)))
            for model in (AuditEvent, ApiIdempotencyRecord)
        ])


@pytest.mark.parametrize("subject_name", ["image", "video", "director"])
async def test_create_list_server_metadata_and_legacy_unchanged(review_env, subject_name):
    env = review_env
    body = getattr(env, subject_name)
    created = await env.client.post("/api/v1/human-reviews", json=body)
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["subject"]["outputHash"] == OUTPUT_HASH
    assert record["reviewerId"] == str(env.ids["owner"])
    assert record["reviewKey"] == body["reviewKey"]
    assert record["subject"]["synthetic"] is (subject_name == "director")
    assert record["subject"]["inputHash"] == INPUT_HASH
    if subject_name == "director":
        assert record["subject"]["packageId"] == "package-shot"
        assert record["subject"]["packageRevision"] == 2
    read = await env.client.get("/api/v1/human-reviews", params=query(body))
    assert read.status_code == 200, read.text
    assert read.json()["reviews"] == [record]
    assert read.json()["subject"] == record["subject"]
    async with env.db.session_factory() as session:
        audit = await session.get(AuditEvent, uuid.UUID(record["id"]))
        assert audit.action == human_reviews.ACTION
        assert audit.to_state == "PASS"
        assert len(audit.evidence_refs_json) == 1
        assert isinstance(audit.evidence_refs_json[0], str)
        evidence = audit.evidence_refs_json[0].removeprefix(human_reviews.PREFIX)
        assert canonical_json(json.loads(evidence)) == evidence
        assert len(audit.correlation_id) <= 80
        image = await session.get(ImageGenerationOutput, env.ids["image"])
        variant = await session.get(GenerationVariant, env.ids["variant"])
        director = await session.get(CreativeTask, env.ids["director"])
        assert image.qualification_status == QualityDecisionStatus.PENDING
        assert image.quality_gates_json == {}
        assert image.reviewed_at is None
        assert variant.final_approval_status == QualityDecisionStatus.PENDING
        assert variant.quality_gates_json == {}
        assert variant.final_approved_at is None
        assert director.snapshot_json["calls"] == 2
        assert director.snapshot_json["cost_micros"] == 2
        assert director.snapshot_json["storyboard"]["candidates"][0]["qualified"] is False
        for model in (ImageQuotaReservation, PointsReservation, PointsLedger, GenerationFeedback):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("role", ["other", "admin", "auditor"])
@pytest.mark.parametrize("subject_name", ["image", "video", "director"])
async def test_owner_only_even_for_privileged_roles(review_env, role, subject_name):
    env = review_env
    body = getattr(env, subject_name)
    headers = {"X-User-Id": str(env.ids[role])}
    for path in ("/api/v1/human-reviews", "/api/v1/human-reviews/export"):
        response = await env.client.get(path, headers=headers, params=query(body))
        assert response.status_code == 404, response.text
    response = await env.client.post("/api/v1/human-reviews", headers=headers, json=body)
    assert response.status_code == (403 if role == "auditor" else 404)
    assert await counts(env) == (0, 0)


async def test_auditor_owner_read_only(review_env):
    env = review_env
    created = await env.client.post("/api/v1/human-reviews", json=env.image)
    assert created.status_code == 201
    async with env.db.session_factory() as session:
        owner = await session.get(User, env.ids["owner"])
        owner.role = UserRole.AUDITOR
        await session.commit()
    for path in ("/api/v1/human-reviews", "/api/v1/human-reviews/export"):
        response = await env.client.get(path, params=query(env.image))
        assert response.status_code == 200, response.text
    denied = await env.client.post("/api/v1/human-reviews", json=env.image)
    assert denied.status_code == 403
    assert await counts(env) == (1, 1)


@pytest.mark.parametrize("mode", ["fake", "replay"])
async def test_runtime_fake_pass_never_upgrades_and_export_excludes(review_env, mode):
    env = review_env
    env.app.state.settings.ai_adapter_mode = mode
    created = await env.client.post("/api/v1/human-reviews", json=env.image)
    assert created.status_code == 201, created.text
    assert created.json()["subject"]["synthetic"] is True
    exported = await env.client.get("/api/v1/human-reviews/export", params=query(env.image))
    assert exported.status_code == 200, exported.text
    assert exported.json() == {
        "schemaVersion": "human-production-review-export.v1",
        "records": [], "excludedSyntheticCount": 1,
    }
    env.app.state.settings.ai_adapter_mode = "openai"
    exported = await env.client.get("/api/v1/human-reviews/export", params={
        **query(env.image), "includeSynthetic": "true",
    })
    assert exported.status_code == 200, exported.text
    assert exported.json()["records"] == [created.json()]
    assert exported.json()["excludedSyntheticCount"] == 0
    async with env.db.session_factory() as session:
        image = await session.get(ImageGenerationOutput, env.ids["image"])
        assert image.qualification_status == QualityDecisionStatus.PENDING


@pytest.mark.parametrize("subject_name", ["image", "video"])
async def test_persisted_fake_provenance_excluded_in_real_mode(review_env, subject_name):
    env = review_env
    async with env.db.session_factory() as session:
        if subject_name == "image":
            batch = await session.get(ImageGenerationBatch, env.ids["batch"])
            batch.request_json = {**batch.request_json, "synthetic": True}
        else:
            attempt = await session.get(GenerationAttempt, env.ids["attempt"])
            attempt.provider = "fake"
        await session.commit()
    body = getattr(env, subject_name)
    created = await env.client.post("/api/v1/human-reviews", json=body)
    assert created.status_code == 201, created.text
    assert created.json()["subject"]["synthetic"] is True
    exported = await env.client.get("/api/v1/human-reviews/export", params=query(body))
    assert exported.json()["excludedSyntheticCount"] == 1


async def test_replay_hash_change_and_conflict(review_env):
    env = review_env
    first = await env.client.post("/api/v1/human-reviews", json=env.image)
    assert first.status_code == 201, first.text
    async with env.db.session_factory() as session:
        image = await session.get(ImageGenerationOutput, env.ids["image"])
        image.sha256 = NEW_HASH
        image.object_key = None
        await session.commit()
    replay = await env.client.post("/api/v1/human-reviews", json=env.image)
    assert replay.status_code == 201, replay.text
    assert replay.json() == first.json()
    conflict = await env.client.post("/api/v1/human-reviews", json={
        **env.image, "expectedOutputHash": NEW_HASH,
    })
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert await counts(env) == (1, 1)


async def test_replay_rechecks_ownership(review_env):
    env = review_env
    first = await env.client.post("/api/v1/human-reviews", json=env.image)
    assert first.status_code == 201
    async with env.db.session_factory() as session:
        batch = await session.get(ImageGenerationBatch, env.ids["batch"])
        batch.user_id = env.ids["other"]
        await session.commit()
    replay = await env.client.post("/api/v1/human-reviews", json=env.image)
    assert replay.status_code == 404
    assert await counts(env) == (1, 1)


async def test_normalized_replay_and_append_only_training_history(review_env):
    env = review_env
    first_body = {
        **env.image, "verdict": "REWORK", "reasonCodes": ["GARMENT", "FACE", "FACE"],
        "note": "  fix logo  ",
    }
    first = await env.client.post("/api/v1/human-reviews", json=first_body)
    assert first.status_code == 201, first.text
    repeated = await env.client.post("/api/v1/human-reviews", json={
        **first_body, "reasonCodes": ["FACE", "GARMENT"], "note": "fix logo",
    })
    assert repeated.json() == first.json()
    second = await env.client.post("/api/v1/human-reviews", json={
        **env.image, "reviewKey": "review-2",
    })
    assert second.status_code == 201
    exported = await env.client.get("/api/v1/human-reviews/export", params=query(env.image))
    assert exported.status_code == 200, exported.text
    assert exported.json()["records"] == [first.json(), second.json()]
    assert await counts(env) == (2, 2)


async def test_concurrent_replay_creates_exactly_one_record(review_env):
    env = review_env
    responses = await asyncio.gather(*[
        env.client.post("/api/v1/human-reviews", json=env.image) for _ in range(4)
    ])
    assert [response.status_code for response in responses] == [201] * 4, [
        response.text for response in responses
    ]
    assert all(response.json() == responses[0].json() for response in responses)
    assert await counts(env) == (1, 1)


@pytest.mark.parametrize("failure_point", ["store", "commit"])
async def test_failure_before_commit_rolls_back_audit_and_claim(
    review_env, monkeypatch, failure_point,
):
    env = review_env

    async def broken(*args, **kwargs):
        raise RuntimeError("injected failure after audit flush")

    with monkeypatch.context() as patch:
        if failure_point == "store":
            patch.setattr(human_reviews, "store_idempotent_response", broken)
        else:
            patch.setattr(AsyncSession, "commit", broken)
        response = await env.client.post("/api/v1/human-reviews", json=env.image)
    assert response.status_code == 500
    assert await counts(env) == (0, 0)
    retried = await env.client.post("/api/v1/human-reviews", json=env.image)
    assert retried.status_code == 201, retried.text
    assert await counts(env) == (1, 1)


@pytest.mark.parametrize("subject_name", ["image", "video", "director"])
async def test_hash_mismatch_rolls_back_claim(review_env, subject_name):
    env = review_env
    body = getattr(env, subject_name)
    response = await env.client.post("/api/v1/human-reviews", json={
        **body, "expectedOutputHash": NEW_HASH,
    })
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "HUMAN_REVIEW_OUTPUT_HASH_MISMATCH"
    assert await counts(env) == (0, 0)


@pytest.mark.parametrize("missing", ["hash", "object", "ready", "deleted"])
async def test_unready_video_read_metadata_but_no_post(review_env, missing):
    env = review_env
    async with env.db.session_factory() as session:
        artifact = await session.get(DownloadArtifact, env.ids["artifact"])
        if missing == "hash":
            artifact.sha256 = None
        elif missing == "object":
            artifact.object_key = None
        elif missing == "ready":
            artifact.status = DownloadStatus.DOWNLOADING
        else:
            artifact.deleted_at = datetime.now(UTC)
        await session.commit()
    read = await env.client.get("/api/v1/human-reviews", params=query(env.video))
    assert read.status_code == 200, read.text
    response = await env.client.post("/api/v1/human-reviews", json=env.video)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "HUMAN_REVIEW_OUTPUT_NOT_READY"
    assert await counts(env) == (0, 0)


async def test_latest_ready_artifact_wins(review_env):
    env = review_env
    async with env.db.session_factory() as session:
        session.add(DownloadArtifact(
            attempt_id=env.ids["attempt"], status=DownloadStatus.READY, revision=2,
            object_key="outputs/video-v2.mp4", sha256=NEW_HASH,
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        ))
        session.add(DownloadArtifact(
            attempt_id=env.ids["attempt"], status=DownloadStatus.DOWNLOADING, revision=3,
            object_key="outputs/video-v3.mp4", sha256=INPUT_HASH,
        ))
        await session.commit()
    read = await env.client.get("/api/v1/human-reviews", params=query(env.video))
    assert read.status_code == 200, read.text
    assert read.json()["subject"]["outputHash"] == NEW_HASH
    created = await env.client.post("/api/v1/human-reviews", json={
        **env.video, "expectedOutputHash": NEW_HASH, "verdict": "FAIL", "reasonCodes": ["MOTION"],
    })
    assert created.status_code == 201, created.text


async def test_director_task_collision_isolated_and_shot_rework(review_env):
    env = review_env
    first = await env.client.post("/api/v1/human-reviews", json={
        **env.director, "verdict": "REWORK", "reasonCodes": ["SPACE"],
    })
    second = await env.client.post("/api/v1/human-reviews", json={
        **env.director, "taskId": str(env.ids["director2"]), "reviewKey": "review-2",
    })
    assert first.status_code == second.status_code == 201, (first.text, second.text)
    read = await env.client.get("/api/v1/human-reviews", params=query(env.director))
    assert read.json()["reviews"] == [first.json()]
    async with env.db.session_factory() as session:
        events = list(await session.scalars(select(AuditEvent)))
        assert len({event.entity_id for event in events}) == 2


@pytest.mark.parametrize("damage", [
    "prefix", "json", "version", "missing-version", "object", "verdict", "owner",
])
async def test_corrupt_or_unknown_envelope_is_controlled(review_env, damage):
    env = review_env
    created = await env.client.post("/api/v1/human-reviews", json=env.image)
    assert created.status_code == 201
    async with env.db.session_factory() as session:
        event = await session.get(AuditEvent, uuid.UUID(created.json()["id"]))
        data = json.loads(event.evidence_refs_json[0].removeprefix(human_reviews.PREFIX))
        if damage == "prefix":
            event.evidence_refs_json = ["object/path"]
        elif damage == "json":
            event.evidence_refs_json = [human_reviews.PREFIX + "{"]
        elif damage == "object":
            event.evidence_refs_json = [data]
        elif damage == "verdict":
            event.to_state = "FAIL"
        else:
            if damage == "version":
                data["schemaVersion"] = "human-production-review.v2"
            elif damage == "missing-version":
                data.pop("schemaVersion")
            else:
                data["ownerId"] = str(env.ids["other"])
            event.evidence_refs_json = [human_reviews.PREFIX + canonical_json(data)]
        await session.commit()
    for path in ("/api/v1/human-reviews", "/api/v1/human-reviews/export"):
        read = await env.client.get(path, params=query(env.image))
        assert read.status_code == 409, read.text
        assert read.json()["detail"]["code"] == "HUMAN_REVIEW_EVIDENCE_INVALID"


async def test_legacy_path_refs_ignored_and_task_filter_validated(review_env):
    env = review_env
    created = await env.client.post("/api/v1/human-reviews", json=env.image)
    assert created.status_code == 201
    async with env.db.session_factory() as session:
        event = await session.get(AuditEvent, uuid.UUID(created.json()["id"]))
        session.add(AuditEvent(
            actor_id=env.ids["owner"], action="IMAGE_QUALITY_DECISION",
            entity_type=event.entity_type, entity_id=event.entity_id,
            correlation_id="legacy", evidence_refs_json=["outputs/legacy.png"],
        ))
        await session.commit()
    read = await env.client.get("/api/v1/human-reviews", params=query(env.image))
    assert read.json()["reviews"] == [created.json()]
    wrong_task = await env.client.get("/api/v1/human-reviews", params={
        **query(env.image), "taskId": str(uuid.uuid4()),
    })
    assert wrong_task.status_code == 404


@pytest.mark.parametrize("missing", ["hash", "object"])
async def test_unready_image_never_creates_review(review_env, missing):
    env = review_env
    async with env.db.session_factory() as session:
        image = await session.get(ImageGenerationOutput, env.ids["image"])
        if missing == "hash":
            image.sha256 = None
        else:
            image.object_key = None
        await session.commit()
    response = await env.client.post("/api/v1/human-reviews", json=env.image)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "HUMAN_REVIEW_OUTPUT_NOT_READY"
    assert await counts(env) == (0, 0)


@pytest.mark.parametrize("damage", [
    None, "missing-task", "foreign-task", "foreign-package", "object",
])
async def test_director_batch_mapping_requires_true_task_provenance(review_env, damage):
    env = review_env
    async with env.db.session_factory() as session:
        task = await session.get(CreativeTask, env.ids["director"])
        snapshot = json.loads(json.dumps(task.snapshot_json))
        candidate = snapshot["storyboard"]["candidates"][0]
        candidate.update({
            "output_id": str(env.ids["image"]), "item_id": str(env.ids["item"]),
            "batch_id": str(env.ids["batch"]), "object_key": "outputs/image.png",
        })
        if damage == "object":
            candidate["object_key"] = "outputs/foreign.png"
        task.snapshot_json = snapshot
        provenance = {
            "creativeTaskId": str(task.id), "packageId": candidate["package_id"],
        }
        item = await session.get(ImageGenerationItem, env.ids["item"])
        item.request_json = provenance
        batch = await session.get(ImageGenerationBatch, env.ids["batch"])
        batch.request_json = dict(provenance)
        if damage == "missing-task":
            batch.request_json = {"packageId": candidate["package_id"]}
        elif damage == "foreign-task":
            batch.request_json = {**provenance, "creativeTaskId": str(env.ids["director2"])}
        elif damage == "foreign-package":
            batch.request_json = {**provenance, "packageId": "unrelated-package"}
        await session.commit()
    response = await env.client.post("/api/v1/human-reviews", json=env.director)
    if damage is None:
        assert response.status_code == 201, response.text
    else:
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "HUMAN_REVIEW_OUTPUT_BINDING_INVALID"
        assert await counts(env) == (0, 0)


async def test_missing_director_package_metadata_remains_null(review_env):
    env = review_env
    async with env.db.session_factory() as session:
        task = await session.get(CreativeTask, env.ids["director"])
        snapshot = json.loads(json.dumps(task.snapshot_json))
        snapshot["storyboard"]["packages"] = {}
        task.snapshot_json = snapshot
        await session.commit()
    response = await env.client.get("/api/v1/human-reviews", params=query(env.director))
    assert response.status_code == 200, response.text
    subject = response.json()["subject"]
    assert subject["packageId"] is None
    assert subject["packageRevision"] is None
    assert subject["promptHash"] is None
    assert subject["inputHash"] == INPUT_HASH
    created = await env.client.post("/api/v1/human-reviews", json=env.director)
    assert created.status_code == 201, created.text
    assert created.json()["subject"] == subject


@pytest.mark.parametrize("damage", ["missing-hash", "invalid-hash", "missing-object", "deleting"])
async def test_latest_usable_video_skips_unusable_ready_artifacts(review_env, damage):
    env = review_env
    async with env.db.session_factory() as session:
        session.add(DownloadArtifact(
            attempt_id=env.ids["attempt"], status=DownloadStatus.READY, revision=2,
            object_key=None if damage == "missing-object" else "outputs/new.mp4",
            sha256=(
                None if damage == "missing-hash"
                else "z" * 64 if damage == "invalid-hash" else NEW_HASH
            ),
            created_at=datetime.now(UTC) + timedelta(seconds=1),
            deletion_pending_at=datetime.now(UTC) if damage == "deleting" else None,
        ))
        await session.commit()
    read = await env.client.get("/api/v1/human-reviews", params=query(env.video))
    assert read.status_code == 200, read.text
    assert read.json()["subject"]["outputHash"] == OUTPUT_HASH
    response = await env.client.post("/api/v1/human-reviews", json=env.video)
    assert response.status_code == 201, response.text


async def test_actual_application_registration_session_auth_and_csrf(review_env, tmp_path):
    from libtv_agent.app import create_app
    from libtv_agent.config import Settings

    env = review_env
    settings = Settings(
        _env_file=None, app_env="test", database_url=str(env.db.engine.url),
        shared_authentication_enabled=True, session_secret="isolated-human-review-session-secret",
        object_store_mode="local", artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner", ai_adapter_mode="fake", libtv_adapter_mode="fake",
        paid_generation_enabled=False, kling_enabled=False, wavespeed_enabled=False,
        feedback_learning_enabled=False,
    )
    app = create_app(settings)
    # Real middleware/router/dependencies, with only a temporary DB and no startup workers.
    app.state.database = env.db
    session_token = "human-review-isolated-session-token"
    async with env.db.session_factory() as session:
        session.add(UserSession(
            user_id=env.ids["owner"],
            token_hash=hashlib.sha256(session_token.encode()).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ))
        await session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test",
    ) as client:
        forged = await client.get(
            "/api/v1/human-reviews", params=query(env.image),
            headers={"X-User-Id": str(env.ids["owner"])},
        )
        assert forged.status_code == 401, forged.text
        client.cookies.set(settings.session_cookie_name, session_token)
        for path in ("/api/v1/human-reviews", "/api/v1/human-reviews/export"):
            read = await client.get(path, params=query(env.image))
            assert read.status_code == 200, read.text
            assert read.headers["cache-control"] == "no-store"
        denied = await client.post("/api/v1/human-reviews", json=env.image)
        assert denied.status_code == 403
        assert denied.json()["detail"]["code"] == "CSRF_REJECTED"
        client.cookies.set(settings.csrf_cookie_name, "isolated-csrf")
        denied = await client.post(
            "/api/v1/human-reviews", json=env.image, headers={"X-CSRF-Token": "wrong"},
        )
        assert denied.status_code == 403
        assert await counts(env) == (0, 0)
        accepted = await client.post(
            "/api/v1/human-reviews", json=env.image,
            headers={"X-CSRF-Token": "isolated-csrf", "X-User-Id": str(env.ids["other"])},
        )
        assert accepted.status_code == 201, accepted.text
        assert accepted.json()["reviewerId"] == str(env.ids["owner"])
        assert accepted.json()["subject"]["synthetic"] is True
        assert accepted.headers["cache-control"] == "no-store"
        assert await counts(env) == (1, 1)
