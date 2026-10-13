from __future__ import annotations

import asyncio
import io
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.creative.workflow import PIPELINE, REALITY, Authorization, Command, digest
from libtv_agent.domain.models import (
    Base,
    CreativePromptRegistry,
    CreativeRecord,
    CreativeTask,
    ImageGenerationBatch,
)
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
async def workflow(tmp_path: Path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'workflow.db').as_posix()}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    settings = Settings(
        app_env="test", database_url=url, object_store_mode="local",
        artifact_root=tmp_path / "artifacts", runner_root=tmp_path / "runner",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, app, settings


class Flow:
    def __init__(self, client, app, settings):
        self.client, self.app, self.settings = client, app, settings
        self.headers = {"X-User-Id": settings.dev_user_id}
        self.result = None

    async def create(self, client_key=None):
        product = await self.client.post(
            "/api/v1/products", headers=self.headers,
            json={"internalSkuId": str(uuid.uuid4())},
        )
        assert product.status_code == 201, product.text
        self.product_id = product.json()["id"]
        data = io.BytesIO()
        Image.new("RGB", (64, 96), "red").save(data, "PNG")
        response = await self.client.post(
            "/api/v1/creative-workflow/tasks", headers=self.headers,
            data={"product_id": self.product_id, **(
                {"client_key": client_key} if client_key else {}
            )},
            files={"front": ("front.png", data.getvalue(), "image/png")},
        )
        assert response.status_code == 201, response.text
        self.task_id = response.json()["id"]
        self.version = 0
        return response

    async def command(self, action, expected_status=200, **kwargs):
        response = await self.client.post(
            f"/api/v1/creative-workflow/tasks/{self.task_id}/commands",
            headers=self.headers,
            json={
                "command_key": str(uuid.uuid4()), "expected_version": self.version,
                "action": action, **kwargs,
            },
        )
        assert response.status_code == expected_status, response.text
        if response.status_code == 200:
            self.result = response.json()
            self.version = self.result["state_version"]
        return response

    async def plan(self):
        await self.create()
        await self.command("analyze")
        await self.command("select_direction", direction_id="A")
        self.package = self.result["snapshot"]["package"]

    async def authorize(self, **kwargs):
        if "parent_authorization_id" not in kwargs and self.result:
            prior = self.result["snapshot"].get("authorization")
            if prior:
                kwargs["parent_authorization_id"] = prior["authorization_id"]
        auth = {
            "authorization_id": str(uuid.uuid4()), "package_id": self.package["package_id"],
            "locks_hash": self.package["locks_hash"],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "max_calls": 6, "max_cost_micros": 6,
            **kwargs,
        }
        return await self.command("authorize", authorization=auth)

    async def generate(self, **kwargs):
        response = await self.command("generate", package_id=self.package["package_id"], **kwargs)
        self.package = self.result["snapshot"]["package"]
        return response


@pytest.mark.asyncio
async def test_front_only_closed_loop_and_append_only_evidence(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    assert flow.result["snapshot"]["trace"] == list(PIPELINE[:5])
    analysis = flow.result["snapshot"]["director_analysis"]
    assert analysis["schema_version"] == "director-analysis.v1"
    assert [stage["order"] for stage in analysis["stages"]] == list(range(1, 9))
    assert analysis["trace"] == [
        "PRODUCT_BRAND_AUDIENCE_DNA",
        "SCENE_REALITY_SPATIAL",
        "STORYBOARD_SHOT_MIX_PRECHECK",
        "KEY_VISUAL_SELECTOR",
        "IMAGE_PROMPT_MOTION_READY",
        "MODEL_AWARE_VIDEO_STRATEGY",
        "EMOTION_VIDEO_PROMPT",
        "VIDEO_QA_ONE_FIX",
    ]
    assert analysis["video_strategy"]["strategy"] == "strategy_unresolved"
    assert analysis["stages"][0]["status"] == "COMPLETE"
    assert flow.result["snapshot"]["director_analysis_hash"] == digest(analysis)
    assert [value["dimension"] for value in flow.package["reality"]] == list(REALITY)
    assert flow.package["reality"][-1]["decision"] == "none"
    await flow.authorize()
    await flow.generate()
    snapshot = flow.result["snapshot"]
    assert snapshot["trace"] == list(PIPELINE)
    assert snapshot["cost_micros"] == 2
    output = snapshot["candidates"][0]
    assert output["synthetic"]
    assert output["media_evidence"] == "CANONICAL_COPY_PLACEHOLDER_NOT_GENERATED"
    await flow.command("select", candidate_id=output["candidate_id"], expected_status=409)
    await flow.command("review", candidate_id=output["candidate_id"], decision="QUALIFIED")
    await flow.command("select", candidate_id=output["candidate_id"])
    selection = flow.result["snapshot"]["selection"]
    for key in ("shot_id", "package_id", "batch_id", "item_id", "output_id"):
        assert selection[key] == output[key]
    async with flow.app.state.database.session_factory() as session:
        rows = list(await session.scalars(select(CreativeRecord).where(
            CreativeRecord.task_id == uuid.UUID(flow.task_id),
        )))
    assert {row.kind for row in rows} >= {
        "asset_link", "plan", "package", "authorization", "attempt", "iteration",
        "review", "selection",
        "director_analysis",
    }
    analysis_records = sorted(
        (row for row in rows if row.kind == "director_analysis"),
        key=lambda row: row.record_key,
    )
    assert [row.record_key for row in analysis_records] == ["1", "2"]
    assert analysis_records[0].payload_json["selected_direction"] is None
    assert analysis_records[1].payload_json == analysis
    critic = next(row for row in rows if row.kind == "review"
                  and row.payload_json["reviewer_kind"] == "FAKE_CRITIC")
    assert critic.payload_json["decision"] == "UNVERIFIED"
    assert set(critic.payload_json["axes"].values()) == {"unverified"}


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["select_direction", "authorize", "generate", "revise"])
@pytest.mark.parametrize("corruption", [
    "missing", "reordered", "edited_evidence", "foreign_source", "stale_facts",
    "changed_direction", "different_selection",
])
async def test_analysis_contract_gate_blocks_corruption_without_side_effects(
    workflow, action, corruption,
):
    flow = Flow(*workflow)
    if action == "select_direction":
        await flow.create()
        await flow.command("analyze")
    else:
        await flow.plan()
        await flow.authorize(loop_enabled=True)
        if action == "revise":
            await flow.generate()

    async with flow.app.state.database.session_factory() as session:
        task = await session.get(CreativeTask, uuid.UUID(flow.task_id))
        snapshot = deepcopy(task.snapshot_json)
        analysis = snapshot["director_analysis"]
        if corruption == "missing":
            del snapshot["director_analysis"]
        elif corruption == "reordered":
            analysis["stages"].reverse()
        elif corruption == "edited_evidence":
            analysis["stages"][0]["evidence"] = ["fabricated result"]
        elif corruption == "foreign_source":
            analysis["source_hash"] = "f" * 64
            snapshot["director_analysis_hash"] = digest(analysis)
        elif corruption == "stale_facts":
            analysis["facts_revision"] += 1
            snapshot["director_analysis_hash"] = digest(analysis)
        elif corruption == "changed_direction":
            snapshot["plan"]["directions"][0]["scene"] = "different scene"
        else:
            analysis["selected_direction"] = "B"
            analysis["planning_status"] = "READY_FOR_PACKAGE"
            snapshot["director_analysis_hash"] = digest(analysis)
        task.snapshot_json = snapshot
        await session.commit()
        prior_records = list(await session.scalars(select(CreativeRecord).where(
            CreativeRecord.task_id == task.id,
        )))

    kwargs = {}
    if action == "select_direction":
        kwargs["direction_id"] = "A"
    elif action == "authorize":
        kwargs["authorization"] = {
            "authorization_id": str(uuid.uuid4()),
            "package_id": flow.package["package_id"],
            "locks_hash": flow.package["locks_hash"],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "max_calls": 2, "max_cost_micros": 2,
        }
    elif action == "revise":
        kwargs.update(
            package_id=flow.package["package_id"],
            candidate_id=flow.result["snapshot"]["candidates"][0]["candidate_id"],
            changed_modules=["Reality"], fix="change light", failure_region="shirt",
        )
    else:
        kwargs["package_id"] = flow.package["package_id"]
    response = await flow.command(action, expected_status=409, **kwargs)
    expected = (
        "DIRECTOR_ANALYSIS_REQUIRED"
        if corruption == "missing"
        else "DIRECTOR_ANALYSIS_INVALID"
    )
    assert response.json()["detail"]["code"] == expected
    async with flow.app.state.database.session_factory() as session:
        task = await session.get(CreativeTask, uuid.UUID(flow.task_id))
        assert task.state_version == flow.version
        assert task.snapshot_json == snapshot
        records = list(await session.scalars(select(CreativeRecord).where(
            CreativeRecord.task_id == task.id,
        )))
        assert len(records) == len(prior_records)


@pytest.mark.asyncio
async def test_owner_isolation_and_production_endpoint_disabled(workflow):
    flow = Flow(*workflow)
    await flow.create()
    path = f"/api/v1/creative-workflow/tasks/{flow.task_id}"
    response = await flow.client.get(path, headers={"X-User-Id": flow.settings.dev_admin_id})
    assert response.status_code == 404
    response = await flow.client.post(
        path + "/commands", headers={"X-User-Id": flow.settings.dev_admin_id},
        json={"action": "analyze", "expected_version": 0, "command_key": "intruder"},
    )
    assert response.status_code == 404
    flow.settings.app_env = "development"
    response = await flow.client.get(path, headers=flow.headers)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "OFFLINE_WORKFLOW_DISABLED"
    flow.settings.app_env = "test"
    flow.settings.paid_generation_enabled = True
    response = await flow.client.get(path, headers=flow.headers)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PAID_MODE_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_idempotent_replay_conflict_and_stale_version(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    await flow.authorize()
    response = await flow.generate(command_key="same-key")
    original = response.json()
    repeated = await flow.command(
        "generate", command_key="same-key", expected_version=flow.version - 1,
        package_id=flow.package["package_id"],
    )
    assert repeated.json() == original
    conflict = await flow.command(
        "generate", command_key="same-key", package_id="other", expected_status=409,
    )
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
    stale = await flow.command("stop", expected_version=0, expected_status=409)
    assert stale.json()["detail"]["code"] == "STALE_VERSION"


@pytest.mark.asyncio
async def test_cas_competing_commands_one_wins(workflow):
    flow = Flow(*workflow)
    await flow.create()
    path = f"/api/v1/creative-workflow/tasks/{flow.task_id}/commands"
    results = await asyncio.gather(*[
        flow.client.post(path, headers=flow.headers, json={
            "action": "analyze", "expected_version": 0, "command_key": f"worker-{i}",
        }) for i in range(2)
    ])
    assert sorted(response.status_code for response in results) == [200, 409]
    read = await flow.client.get(path.removesuffix("/commands"), headers=flow.headers)
    assert read.json()["state_version"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["UNKNOWN", "WRITE_UNCERTAIN"])
async def test_uncertain_holds_cost_and_only_reconciliation_restores(workflow, outcome):
    flow = Flow(*workflow)
    await flow.plan()
    await flow.authorize()
    await flow.generate(fake_outcome=outcome)
    assert flow.result["status"] == "ACTION_REQUIRED"
    assert flow.result["snapshot"]["cost_micros"] == 2
    for action in ("generate", "revise", "authorize"):
        response = await flow.command(action, expected_status=409)
        assert response.json()["detail"]["code"] == "EXECUTION_UNKNOWN"
    await flow.command("reconcile", expected_status=409)
    await flow.command("reconcile", reconcile_not_submitted=True)
    assert flow.result["snapshot"]["cost_micros"] == 0
    assert flow.result["snapshot"]["calls"] == 2
    await flow.generate()
    assert len(flow.result["snapshot"]["candidates"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cap,code", [(1, "CALL_LIMIT"), (6, "BUDGET_EXHAUSTED")])
async def test_atomic_budget_rejection_does_not_consume_or_mutate(workflow, cap, code):
    flow = Flow(*workflow)
    await flow.plan()
    await flow.authorize(max_calls=cap, max_cost_micros=1)
    response = await flow.command(
        "generate", package_id=flow.package["package_id"], expected_status=409,
    )
    assert response.json()["detail"]["code"] == code
    read = await flow.client.get(
        f"/api/v1/creative-workflow/tasks/{flow.task_id}", headers=flow.headers,
    )
    assert read.json()["snapshot"]["calls"] == 0
    assert read.json()["state_version"] == flow.version


@pytest.mark.asyncio
async def test_loop_default_off_and_authorized_new_package(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    await flow.authorize()
    await flow.generate()
    parent = flow.result["snapshot"]["candidates"][-1]["candidate_id"]
    response = await flow.command(
        "revise", candidate_id=parent, package_id=flow.package["package_id"],
        changed_modules=["Reality"], fix="change light angle", failure_region="shirt",
        expected_status=409,
    )
    assert response.json()["detail"]["code"] == "LOOP_NOT_AUTHORIZED"
    await flow.authorize(loop_enabled=True, max_revisions=1)
    old_package = flow.package.copy()
    await flow.command(
        "revise", candidate_id=parent, package_id=old_package["package_id"],
        changed_modules=["Reality"], fix="change light angle", failure_region="shirt",
    )
    new = flow.result["snapshot"]["package"]
    assert new["parent_package_id"] == old_package["package_id"]
    assert new["locks_hash"] == old_package["locks_hash"]
    assert len(flow.result["snapshot"]["candidates"]) == 2
    child = flow.result["snapshot"]["candidates"][-1]
    assert child["revision_index"] == 1
    assert child["parent_candidate_id"] == parent
    await flow.command(
        "revise", candidate_id=child["candidate_id"], package_id=new["package_id"],
        changed_modules=["Reality"], fix="change focus", failure_region="shirt",
        expected_status=409,
    )


@pytest.mark.asyncio
async def test_no_progress_stop_and_expiration(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    await flow.authorize(loop_enabled=True, max_revisions=2)
    await flow.generate()
    first = flow.result["snapshot"]["candidates"][-1]
    await flow.command(
        "revise", candidate_id=first["candidate_id"], package_id=flow.package["package_id"],
        changed_modules=["Reality"], fix="same fix", failure_region="shirt",
    )
    second = flow.result["snapshot"]["candidates"][-1]
    response = await flow.command(
        "revise", candidate_id=second["candidate_id"],
        package_id=flow.result["snapshot"]["package"]["package_id"],
        changed_modules=["Reality"], fix="same fix", failure_region="shirt",
        expected_status=409,
    )
    assert response.json()["detail"]["code"] == "NO_PROGRESS"
    await flow.command("stop")
    response = await flow.command("generate", expected_status=409)
    assert response.json()["detail"]["code"] == "USER_STOPPED"


@pytest.mark.asyncio
async def test_expired_and_mismatched_authorization(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    for values in [
        {"expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
        {"package_id": "old"}, {"locks_hash": "wrong"}, {"shot_ids": []},
    ]:
        auth = {
            "authorization_id": str(uuid.uuid4()), "package_id": flow.package["package_id"],
            "locks_hash": flow.package["locks_hash"], "max_calls": 2, "max_cost_micros": 2,
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(), **values,
        }
        await flow.command("authorize", authorization=auth, expected_status=409)


@pytest.mark.asyncio
async def test_asset_hash_and_revocation(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    key = flow.result["snapshot"]["asset"]["object_key"]
    path = await flow.app.state.object_store.localize(key, Path("unused"))
    original = path.read_bytes()
    path.write_bytes(b"changed")
    response = await flow.command("authorize", expected_status=409)
    assert response.json()["detail"]["code"] == "ASSET_HASH_MISMATCH"
    path.write_bytes(original)
    await flow.authorize()
    await flow.command(
        "revoke_asset", reason="source withdrawn", impact_scope="all-new-execution",
    )
    assert flow.result["status"] == "BLOCKED"
    await flow.command("generate", expected_status=409)


@pytest.mark.asyncio
async def test_ai_cannot_qualify_and_review_retraction_clears_selection(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    await flow.authorize()
    await flow.generate()
    output = flow.result["snapshot"]["candidates"][-1]
    await flow.command(
        "review", candidate_id=output["candidate_id"], decision="QUALIFIED",
        reviewer_kind="FAKE_CRITIC", expected_status=422,
    )
    await flow.command("review", candidate_id=output["candidate_id"], decision="QUALIFIED")
    await flow.command("select", candidate_id=output["candidate_id"])
    await flow.command(
        "review", candidate_id=output["candidate_id"], decision="REJECTED",
        reason="garment details are not readable",
    )
    assert "selection" not in flow.result["snapshot"]
    assert flow.result["snapshot"]["latest_review"]["decision"] == "REJECTED"
    assert flow.result["snapshot"]["latest_review"]["reason"] == (
        "garment details are not readable"
    )


@pytest.mark.asyncio
async def test_rejected_review_requires_reason_and_persists_append_only_history(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    await flow.authorize()
    await flow.generate()
    output = flow.result["snapshot"]["candidates"][-1]

    missing = await flow.command(
        "review", candidate_id=output["candidate_id"], decision="REJECTED",
        expected_status=422,
    )
    assert "REJECTED requires a review reason" in str(missing.json())

    too_long = await flow.command(
        "review", candidate_id=output["candidate_id"], decision="REJECTED",
        reason="x" * 501, expected_status=422,
    )
    assert "string_too_long" in str(too_long.json())

    await flow.command(
        "review", candidate_id=output["candidate_id"], decision="REJECTED",
        reason="  print is not readable  ",
    )
    rejected = flow.result["snapshot"]["latest_review"]
    assert rejected["reason"] == "print is not readable"

    await flow.command(
        "review", candidate_id=output["candidate_id"], decision="QUALIFIED",
    )
    assert flow.result["snapshot"]["latest_review"]["decision"] == "QUALIFIED"
    assert flow.result["snapshot"]["latest_review"]["reason"] is None

    async with flow.app.state.database.session_factory() as session:
        rows = list(await session.scalars(select(CreativeRecord).where(
            CreativeRecord.task_id == uuid.UUID(flow.task_id),
            CreativeRecord.kind == "review",
        )))
    human_reviews = [
        row.payload_json for row in rows if row.payload_json["reviewer_kind"] == "HUMAN"
    ]
    assert {review["decision"] for review in human_reviews} == {"REJECTED", "QUALIFIED"}
    rejected_record = next(review for review in human_reviews if review["decision"] == "REJECTED")
    assert rejected_record["reason"] == "print is not readable"


def test_contract_forbids_unbounded_loop_unknown_modules_and_naive_expiry():
    with pytest.raises(ValidationError):
        Command(
            command_key="key", expected_version=0, action="revise", changed_modules=["Product"],
        )
    auth = {
        "authorization_id": "auth", "package_id": "p", "locks_hash": "h",
        "expires_at": datetime.now(UTC), "max_calls": 2, "max_cost_micros": 2,
    }
    with pytest.raises(ValidationError):
        Authorization(**{**auth, "max_revisions": 3})
    with pytest.raises(ValidationError):
        Authorization(**{**auth, "expires_at": datetime.now()})


@pytest.mark.asyncio
async def test_new_app_recovers_persistent_commands_and_selection(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    await flow.authorize()
    generated = await flow.generate(command_key="recover")
    body = {
        "action": "generate", "command_key": "recover",
        "expected_version": flow.version - 1, "package_id": flow.package["package_id"],
    }
    restarted = create_app(flow.settings)
    async with restarted.router.lifespan_context(restarted):
        async with AsyncClient(
            transport=ASGITransport(app=restarted), base_url="http://test",
        ) as client:
            response = await client.post(
                f"/api/v1/creative-workflow/tasks/{flow.task_id}/commands",
                headers=flow.headers, json=body,
            )
            assert response.status_code == 200, response.text
            assert response.json() == generated.json()


@pytest.mark.asyncio
async def test_wrong_candidate_wrong_package_and_revision_preserves_old_package(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    await flow.authorize(loop_enabled=True)
    await flow.generate()
    output = flow.result["snapshot"]["candidates"][-1]
    await flow.command("review", candidate_id="foreign-output", decision="QUALIFIED",
                       expected_status=409)
    await flow.command("revise", candidate_id=output["candidate_id"], package_id="other",
                       expected_status=409)
    original = flow.package.copy()
    await flow.command(
        "revise", candidate_id=output["candidate_id"], package_id=original["package_id"],
        changed_modules=["Scene"], fix="change distance", failure_region="shirt",
        expected_status=409,
    )
    await flow.command(
        "revise", candidate_id=output["candidate_id"], package_id=original["package_id"],
        changed_modules=["Reality"], fix="change light", failure_region="shirt",
    )
    async with flow.app.state.database.session_factory() as session:
        rows = list(await session.scalars(select(CreativeRecord).where(
            CreativeRecord.task_id == uuid.UUID(flow.task_id), CreativeRecord.kind == "package",
        )))
    assert len(rows) == 2
    stored = next(row for row in rows if row.record_key == original["package_id"])
    assert stored.payload_json == original
    await flow.command("review", candidate_id=output["candidate_id"], decision="QUALIFIED")
    response = await flow.command("select", candidate_id=output["candidate_id"],
                                  expected_status=409)
    assert response.json()["detail"]["code"] == "STALE_CANDIDATE_PACKAGE"


@pytest.mark.asyncio
async def test_unknown_then_revoke_then_reconcile_stays_blocked(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    await flow.authorize()
    await flow.generate(fake_outcome="UNKNOWN")
    await flow.command(
        "revoke_asset", reason="license withdrawn", impact_scope="all-new-execution",
    )
    assert flow.result["status"] == "BLOCKED"
    await flow.command("reconcile", reconcile_not_submitted=True)
    assert flow.result["status"] == "BLOCKED"
    assert flow.result["snapshot"]["asset"]["revoked"] is True
    with pytest.raises(AssertionError):
        await flow.generate()


@pytest.mark.asyncio
async def test_task_creation_idempotency_is_owner_scoped_and_fingerprint_bound(workflow):
    flow = Flow(*workflow)
    first = await flow.create(client_key="create-once")
    data = io.BytesIO()
    Image.new("RGB", (64, 96), "red").save(data, "PNG")
    repeated = await flow.client.post(
        "/api/v1/creative-workflow/tasks",
        headers=flow.headers,
        data={"product_id": flow.product_id, "client_key": "create-once"},
        files={"front": ("front.png", data.getvalue(), "image/png")},
    )
    assert repeated.status_code == 201
    assert repeated.json() == first.json()
    data2 = io.BytesIO()
    Image.new("RGB", (64, 96), "blue").save(data2, "PNG")
    conflict = await flow.client.post(
        "/api/v1/creative-workflow/tasks",
        headers=flow.headers,
        data={"product_id": flow.product_id, "client_key": "create-once"},
        files={"front": ("front.png", data2.getvalue(), "image/png")},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "TASK_IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_prompt_registry_and_fake_batch_mapping_are_persistent(workflow):
    flow = Flow(*workflow)
    await flow.plan()
    await flow.authorize()
    await flow.generate()
    snapshot = flow.result["snapshot"]
    async with flow.app.state.database.session_factory() as session:
        registry = list(await session.scalars(select(CreativePromptRegistry)))
        batches = list(await session.scalars(select(ImageGenerationBatch)))
    assert registry and registry[0].payload_json["activation_status"] == "ACTIVE"
    assert batches and batches[0].items[0].outputs[0].sha256 == snapshot["asset"]["sha256"]
    assert batches[0].items[0].request_json["shotId"] == "FIRST_FRAME"


@pytest.mark.asyncio
async def test_product_fact_change_invalidates_unexecuted_task(workflow):
    flow = Flow(*workflow)
    await flow.create()
    newer = await flow.client.post(
        f"/api/v1/products/{flow.product_id}/versions",
        headers=flow.headers,
        json={
            "sourceType": "USER_UPLOAD",
            "sourceAssetReferences": ["creative-offline/replacement"],
            "truthFields": {"color": "blue"},
        },
    )
    assert newer.status_code == 201, newer.text
    await flow.command("analyze", expected_status=409)
    assert flow.result is None
