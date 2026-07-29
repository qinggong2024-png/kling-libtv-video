import asyncio
import io
import uuid
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.adapters.openai_analysis import AnalysisTimeoutError, fake_analysis
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import (
    CommandStatus,
    ConsistencyLevel,
    DownloadStatus,
    FeedbackValue,
    GenerationStatus,
    ParentTaskPhase,
)
from libtv_agent.domain.models import (
    AuditEvent,
    Base,
    DownloadArtifact,
    GenerationCommand,
    GenerationFeedback,
    GenerationVariant,
    ParentTask,
    PointsLedger,
    User,
    VisualFactCache,
)
from libtv_agent.runner.supervisor import (
    ProcessIdentity,
    RunnerSupervisor,
    classify_recovery,
    process_identity_matches,
)
from libtv_agent.services.confirmation import auto_confirm_pass_tasks
from libtv_agent.services.runtime_control import get_runtime_config, update_runtime_config
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

USER_ID = "00000000-0000-0000-0000-000000000001"
OTHER_USER_ID = "00000000-0000-0000-0000-000000000002"
ADMIN_ID = "00000000-0000-0000-0000-000000000099"


def png_bytes(color: str) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (360, 640), color).save(stream, format="PNG")
    return stream.getvalue()


@asynccontextmanager
async def running_app(
    tmp_path: Path,
    scenario: str = "success",
    *,
    libtv_mode: str = "fake",
    ai_mode: str = "fake",
):
    await asyncio.to_thread(tmp_path.mkdir, parents=True, exist_ok=True)
    database_path = (tmp_path / f"{scenario}.db").as_posix()
    database_url = f"sqlite+aiosqlite:///{database_path}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with engine.begin() as connection:
        await connection.execute(
            User.__table__.insert().values(
                id=uuid.UUID(OTHER_USER_ID),
                username="other-user",
                password_hash="offline-disabled",
                role="USER",
                is_active=True,
            )
        )
    await engine.dispose()
    settings = Settings(
        app_env="test",
        database_url=database_url,
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        fake_libtv_scenario=scenario,
        libtv_adapter_mode=libtv_mode,
        ai_adapter_mode=ai_mode,
        object_store_mode="local",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, app


def user_headers(key: str | None = None, user_id: str = USER_ID) -> dict[str, str]:
    headers = {"X-User-Id": user_id}
    if key:
        headers["Idempotency-Key"] = key
    return headers


async def wait_for_task_phase(
    client: AsyncClient,
    task_id: str,
    *phases: str,
    timeout_seconds: float = 5,
) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        current = await client.get(f"/api/v1/tasks/{task_id}", headers=user_headers())
        assert current.status_code == 200, current.text
        task = current.json()
        if task["phase"] in phases:
            return task
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(f"task {task_id} remained in {task['phase']}")
        await asyncio.sleep(0.01)


async def create_analyzed_task(
    client: AsyncClient,
    colors: list[str] | None = None,
    client_task_id: str = "client-1",
    analysis_model: str = "gpt-5.6-terra",
    user_requirement: str = "突出服装细节",
    variants: list[str] | None = None,
) -> dict:
    uploads = []
    for index, color in enumerate(colors or ["#217a58", "#d6a32d"], start=1):
        response = await client.post(
            "/api/v1/uploads",
            headers=user_headers(f"upload-{client_task_id}-{index}"),
            files={"file": (f"shot-{index}.png", png_bytes(color), "image/png")},
        )
        assert response.status_code == 201, response.text
        uploads.append(response.json())
    response = await client.post(
        "/api/v1/tasks",
        headers=user_headers(f"create-{client_task_id}"),
        json={
            "clientTaskId": client_task_id,
            "title": f"Task {client_task_id}",
            "storyboards": [
                {"uploadId": upload["id"], "order": index, "required": True}
                for index, upload in enumerate(uploads, start=1)
            ],
            "userRequirement": user_requirement,
            "analysisModel": analysis_model,
            "generationProvider": "libtv",
            "sourceUploadDurationSeconds": 1.25,
            "variants": variants or ["STABLE", "DYNAMIC"],
        },
    )
    assert response.status_code == 201, response.text
    task = response.json()
    response = await client.post(
        f"/api/v1/tasks/{task['id']}/analyze",
        headers=user_headers(f"analyze-{client_task_id}"),
        json={"expectedStateVersion": task["stateVersion"]},
    )
    assert response.status_code == 202, response.text
    return await wait_for_task_phase(client, task["id"], "AWAITING_CONFIRMATION")


async def create_draft_task(
    client: AsyncClient,
    client_task_id: str,
) -> dict:
    upload = await client.post(
        "/api/v1/uploads",
        headers=user_headers(f"upload-{client_task_id}"),
        files={"file": ("shot.png", png_bytes("#217a58"), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    response = await client.post(
        "/api/v1/tasks",
        headers=user_headers(f"create-{client_task_id}"),
        json={
            "clientTaskId": client_task_id,
            "title": f"Task {client_task_id}",
            "storyboards": [{"uploadId": upload.json()["id"], "order": 1, "required": True}],
            "userRequirement": "突出服装细节",
            "analysisModel": "gpt-5.6-terra",
            "generationProvider": "libtv",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_generation_feedback_persists_and_guides_matching_future_prompts(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path) as (client, app):
        first = await create_analyzed_task(
            client,
            colors=["#217a58"],
            client_task_id="feedback-source",
        )
        stable = next(item for item in first["variants"] if item["kind"] == "STABLE")
        async with app.state.database.session_factory() as session:
            task_model = await session.get(ParentTask, uuid.UUID(first["id"]))
            variant_model = await session.get(GenerationVariant, uuid.UUID(stable["id"]))
            assert task_model is not None
            assert variant_model is not None
            task_model.phase = ParentTaskPhase.DELIVERABLE
            variant_model.generation_status = GenerationStatus.SUCCEEDED
            await session.commit()

        response = await client.put(
            f"/api/v1/tasks/{first['id']}/variants/{stable['id']}/feedback",
            headers=user_headers(),
            json={
                "feedback": "LIKE",
                "reasons": ["GARMENT_ACCURATE", "NATURAL_MOTION"],
                "comment": "  转身自然，服装还原准确  ",
            },
        )
        assert response.status_code == 200, response.text
        liked = next(item for item in response.json()["variants"] if item["id"] == stable["id"])
        assert liked["feedback"] == "LIKE"
        assert liked["feedbackReasons"] == ["GARMENT_ACCURATE", "NATURAL_MOTION"]
        assert liked["feedbackComment"] == "转身自然，服装还原准确"

        forbidden = await client.put(
            f"/api/v1/tasks/{first['id']}/variants/{stable['id']}/feedback",
            headers=user_headers(user_id=OTHER_USER_ID),
            json={"feedback": "DISLIKE"},
        )
        assert forbidden.status_code == 404

        second = await create_analyzed_task(
            client,
            colors=["#217a58"],
            client_task_id="feedback-target",
        )
        next_stable = next(item for item in second["variants"] if item["kind"] == "STABLE")
        next_dynamic = next(item for item in second["variants"] if item["kind"] == "DYNAMIC")
        assert "同类场景反馈优化" in next_stable["promptText"]
        assert "赞 1，踩 0" in next_stable["promptText"]
        assert "保持服装颜色、版型、印花与文字的准确还原" in next_stable["promptText"]
        assert "同类场景反馈优化" not in next_dynamic["promptText"]

        switched = await client.put(
            f"/api/v1/tasks/{first['id']}/variants/{stable['id']}/feedback",
            headers=user_headers(),
            json={"feedback": "DISLIKE"},
        )
        assert switched.status_code == 200
        switched_variant = next(
            item for item in switched.json()["variants"] if item["id"] == stable["id"]
        )
        assert switched_variant["feedback"] == "DISLIKE"
        assert switched_variant["feedbackReasons"] == []
        assert switched_variant["feedbackComment"] is None
        async with app.state.database.session_factory() as session:
            feedback_rows = list(await session.scalars(select(GenerationFeedback)))
            assert len(feedback_rows) == 1
            assert feedback_rows[0].value == FeedbackValue.DISLIKE

        cleared = await client.put(
            f"/api/v1/tasks/{first['id']}/variants/{stable['id']}/feedback",
            headers=user_headers(),
            json={"feedback": None},
        )
        assert cleared.status_code == 200
        cleared_variant = next(
            item for item in cleared.json()["variants"] if item["id"] == stable["id"]
        )
        assert cleared_variant["feedback"] is None

        invalid = await client.put(
            f"/api/v1/tasks/{first['id']}/variants/{stable['id']}/feedback",
            headers=user_headers(),
            json={"feedback": "LIKE", "reasons": ["CAMERA_TOO_FAST"]},
        )
        assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_generation_feedback_rejects_unfinished_variant(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, _app):
        task = await create_analyzed_task(client, client_task_id="feedback-not-ready")
        variant = task["variants"][0]
        response = await client.put(
            f"/api/v1/tasks/{task['id']}/variants/{variant['id']}/feedback",
            headers=user_headers(),
            json={"feedback": "LIKE"},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "FEEDBACK_NOT_READY"


@pytest.mark.asyncio
async def test_visual_fact_cache_reuses_content_and_remaps_asset_ids(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, app):
        first = await create_analyzed_task(client, client_task_id="cache-first")
        second = await create_analyzed_task(client, client_task_id="cache-second")

        first_ids = {asset["id"] for asset in first["assets"] if asset["role"] != "PRODUCT"}
        second_ids = {asset["id"] for asset in second["assets"] if asset["role"] != "PRODUCT"}
        analyzed_ids = {fact["assetId"] for fact in second["analysisResult"]["storyboardFacts"]}
        assert first_ids.isdisjoint(second_ids)
        assert analyzed_ids == second_ids

        async with app.state.database.session_factory() as session:
            cache_rows = list(await session.scalars(select(VisualFactCache)))
        assert len(cache_rows) == 1
        assert {fact["assetId"] for fact in cache_rows[0].facts_json["storyboardFacts"]} == {
            "STORYBOARD_1",
            "STORYBOARD_2",
        }

        await create_analyzed_task(
            client,
            client_task_id="cache-different-requirement",
            user_requirement="重点展示背面印花",
        )
        async with app.state.database.session_factory() as session:
            assert (
                int(await session.scalar(select(func.count()).select_from(VisualFactCache)) or 0)
                == 2
            )


@pytest.mark.asyncio
async def test_task_list_cursor_paginates_without_overlap(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, _):
        for index in range(3):
            await create_draft_task(client, f"cursor-{index}")

        first_page = await client.get(
            "/api/v1/tasks",
            params={"limit": 2},
            headers=user_headers(),
        )
        assert first_page.status_code == 200, first_page.text
        assert len(first_page.json()) == 2
        cursor = first_page.headers.get("x-next-cursor")
        assert cursor

        second_page = await client.get(
            "/api/v1/tasks",
            params={"limit": 2, "cursor": cursor},
            headers=user_headers(),
        )
        assert second_page.status_code == 200, second_page.text
        assert len(second_page.json()) == 1
        assert {task["id"] for task in first_page.json()}.isdisjoint(
            {task["id"] for task in second_page.json()}
        )


@pytest.mark.asyncio
async def test_analysis_provider_failure_is_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise ConnectionError("upstream reset")

    monkeypatch.setattr("libtv_agent.adapters.openai_analysis.OpenAIAnalysisAdapter.analyze", fail)
    async with running_app(tmp_path, ai_mode="openai") as (client, _):
        task = await create_draft_task(client, "analysis-provider-failure")
        response = await client.post(
            f"/api/v1/tasks/{task['id']}/analyze",
            headers=user_headers("analysis-provider-failure-analyze"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert response.status_code == 202
        current = await wait_for_task_phase(client, task["id"], "ACTION_REQUIRED")
        assert current["phaseReasonCode"] == "ANALYSIS_PROVIDER_FAILED"
        assert current["actionCapabilities"]["canRetryAnalysis"] is True


@pytest.mark.asyncio
async def test_analysis_falls_back_to_sol_when_terra_result_fails_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested_models: list[str] = []

    async def analyze(adapter: object, _prompt: str, images: list[object]) -> object:
        model = str(adapter.settings.openai_model)  # type: ignore[attr-defined]
        requested_models.append(model)
        asset_ids = [str(image.asset_id) for image in images]
        result = fake_analysis(asset_ids)
        if model == "gpt-5.6-terra":
            result.dynamic_plan = result.stable_plan.model_copy(deep=True)
        return result

    monkeypatch.setattr(
        "libtv_agent.adapters.openai_analysis.OpenAIAnalysisAdapter.analyze", analyze
    )
    async with running_app(tmp_path, ai_mode="openai") as (client, app):
        task = await create_analyzed_task(client, client_task_id="analysis-fallback")

        assert task["phase"] == "AWAITING_CONFIRMATION"
        assert requested_models == ["gpt-5.6-terra", "gpt-5.6-sol"]
        async with app.state.database.session_factory() as session:
            fallback_events = list(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.action == "OPENAI_ANALYSIS_FALLBACK_STARTED"
                    )
                )
            )
        assert len(fallback_events) == 1
        assert "primaryModel:gpt-5.6-terra" in fallback_events[0].evidence_refs_json
        assert "fallbackModel:gpt-5.6-sol" in fallback_events[0].evidence_refs_json


@pytest.mark.asyncio
async def test_analysis_timeout_is_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested_models: list[str] = []

    async def timeout(*args: object, **kwargs: object) -> object:
        adapter = args[0]
        requested_models.append(str(adapter.settings.openai_model))  # type: ignore[attr-defined]
        del kwargs
        raise AnalysisTimeoutError("OpenAI image analysis exceeded 1 seconds")

    monkeypatch.setattr(
        "libtv_agent.adapters.openai_analysis.OpenAIAnalysisAdapter.analyze", timeout
    )
    async with running_app(tmp_path, ai_mode="openai") as (client, _):
        task = await create_draft_task(client, "analysis-timeout")
        response = await client.post(
            f"/api/v1/tasks/{task['id']}/analyze",
            headers=user_headers("analysis-timeout-analyze"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert response.status_code == 202
        current = await wait_for_task_phase(client, task["id"], "ACTION_REQUIRED")
        assert current["phaseReasonCode"] == "ANALYSIS_TIMEOUT"
        assert current["actionCapabilities"]["canRetryAnalysis"] is True
        assert requested_models == ["gpt-5.6-terra"]

        async def succeed(_adapter: object, _prompt: str, images: list[object]) -> object:
            asset_ids = [str(image.asset_id) for image in images]
            return fake_analysis(asset_ids)

        monkeypatch.setattr(
            "libtv_agent.adapters.openai_analysis.OpenAIAnalysisAdapter.analyze", succeed
        )
        retried = await client.post(
            f"/api/v1/tasks/{task['id']}/analyze",
            headers=user_headers("analysis-timeout-retry"),
            json={"expectedStateVersion": current["stateVersion"]},
        )
        assert retried.status_code == 202, retried.text
        recovered = await wait_for_task_phase(client, task["id"], "AWAITING_CONFIRMATION")
        assert recovered["phaseReasonCode"] is None
        assert recovered["actionCapabilities"]["canRetryAnalysis"] is False


@pytest.mark.asyncio
async def test_task_snapshots_user_selected_model_and_generation_provider(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, app):
        task = await create_analyzed_task(
            client,
            client_task_id="preference-snapshot",
            analysis_model="custom-analysis-model-v2",
        )
        assert task["analysisModel"] == "custom-analysis-model-v2"
        assert task["generationProvider"] == "libtv"
        async with app.state.database.session_factory() as session:
            stored = await session.get(ParentTask, uuid.UUID(task["id"]))
            assert stored is not None
            assert all(
                variant.generation_config_json["analysisModel"] == "custom-analysis-model-v2"
                and variant.generation_config_json["generationProvider"] == "libtv"
                for variant in stored.variants
            )


@pytest.mark.asyncio
async def test_prompts_can_be_edited_and_revised_before_confirmation(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, app):
        task = await create_analyzed_task(client, client_task_id="prompt-revision")
        edited = await client.patch(
            f"/api/v1/tasks/{task['id']}/prompts",
            headers=user_headers(),
            json={
                "expectedStateVersion": task["stateVersion"],
                "stablePrompt": "稳定方案：保持正面服装细节。",
                "dynamicPrompt": "动态方案：增加行进镜头。",
            },
        )
        assert edited.status_code == 200, edited.text
        edited_task = edited.json()
        assert edited_task["stateVersion"] == task["stateVersion"] + 1
        assert [variant["promptText"] for variant in edited_task["variants"]] == [
            "动态方案：增加行进镜头。",
            "稳定方案：保持正面服装细节。",
        ]
        assert all(variant["promptHash"] for variant in edited_task["variants"])

        advised = await client.post(
            f"/api/v1/tasks/{task['id']}/prompt-assistant",
            headers=user_headers(),
            json={
                "expectedStateVersion": edited_task["stateVersion"],
                "action": "ADVISE",
                "instruction": "减少转身，增加服装正面特写",
                "stablePrompt": "稳定方案：保持正面服装细节。",
                "dynamicPrompt": "动态方案：增加行进镜头。",
            },
        )
        assert advised.status_code == 200, advised.text
        assert advised.json()["task"]["stateVersion"] == edited_task["stateVersion"]
        assert "减少转身" in advised.json()["advice"]

        regenerated = await client.post(
            f"/api/v1/tasks/{task['id']}/prompt-assistant",
            headers=user_headers(),
            json={
                "expectedStateVersion": edited_task["stateVersion"],
                "action": "REGENERATE",
                "instruction": "减少转身，增加服装正面特写",
                "stablePrompt": "稳定方案：保持正面服装细节。",
                "dynamicPrompt": "动态方案：增加行进镜头。",
            },
        )
        assert regenerated.status_code == 200, regenerated.text
        revised_task = regenerated.json()["task"]
        assert revised_task["stateVersion"] == edited_task["stateVersion"] + 1
        assert all(
            "创意补充：减少转身，增加服装正面特写" in variant["promptText"]
            for variant in revised_task["variants"]
        )
        revised_prompts = {
            variant["kind"]: variant["promptText"] for variant in revised_task["variants"]
        }
        targeted = await client.post(
            f"/api/v1/tasks/{task['id']}/prompt-assistant",
            headers=user_headers(),
            json={
                "expectedStateVersion": revised_task["stateVersion"],
                "action": "REGENERATE",
                "instruction": "镜头更加平稳",
                "stablePrompt": revised_prompts["STABLE"],
                "dynamicPrompt": revised_prompts["DYNAMIC"],
                "targetVariant": "STABLE",
            },
        )
        assert targeted.status_code == 200, targeted.text
        targeted_prompts = {
            variant["kind"]: variant["promptText"]
            for variant in targeted.json()["task"]["variants"]
        }
        assert "创意补充：镜头更加平稳" in targeted_prompts["STABLE"]
        assert targeted_prompts["DYNAMIC"] == revised_prompts["DYNAMIC"]
        async with app.state.database.session_factory() as session:
            actions = list(
                await session.scalars(
                    select(AuditEvent.action).where(AuditEvent.entity_id == task["id"])
                )
            )
        assert "EDIT_TASK_PROMPTS" in actions
        assert "REGENERATE_TASK_PROMPTS" in actions


@pytest.mark.asyncio
async def test_auto_confirmation_only_advances_pass_tasks(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, app):
        preference = await client.get(
            "/api/v1/auth/preferences/prompt-confirmation", headers=user_headers()
        )
        assert preference.status_code == 200
        assert preference.json() == {"automatic": False}
        preference = await client.patch(
            "/api/v1/auth/preferences/prompt-confirmation",
            headers=user_headers(),
            json={"automatic": True},
        )
        assert preference.status_code == 200
        assert preference.json() == {"automatic": True}
        passed = await create_analyzed_task(client, client_task_id="auto-pass")
        warning = await create_analyzed_task(client, client_task_id="auto-warning")
        review = await create_analyzed_task(client, client_task_id="auto-review")
        async with app.state.database.session_factory() as session:
            warning_task = await session.get(ParentTask, uuid.UUID(warning["id"]))
            review_task = await session.get(ParentTask, uuid.UUID(review["id"]))
            assert warning_task is not None and review_task is not None
            warning_task.consistency_level = ConsistencyLevel.WARNING
            review_task.consistency_level = ConsistencyLevel.QUALITY_REVIEW
            await session.commit()

            assert (
                await auto_confirm_pass_tasks(
                    session,
                    app.state.libtv_adapter,
                    app.state.object_store,
                    app.state.settings,
                    limit=3,
                )
                == 0
            )
            runtime = await get_runtime_config(session, app.state.settings)
            assert runtime is not None
            config = deepcopy(runtime.config_json)
            config["globalPaused"] = False
            config["paidSubmissionsPaused"] = False
            config["promptConfirmationRequired"] = True
            updated = await update_runtime_config(
                session,
                app.state.settings,
                config=config,
                actor_id=None,
                reason="enable submissions for user preference test",
                expected_version=runtime.version,
            )
            await session.commit()
            assert updated.config_json["promptConfirmationRequired"] is True
            assert (
                await auto_confirm_pass_tasks(
                    session,
                    app.state.libtv_adapter,
                    app.state.object_store,
                    app.state.settings,
                    limit=3,
                )
                == 1
            )

            pass_task = await session.get(ParentTask, uuid.UUID(passed["id"]))
            await session.refresh(warning_task)
            await session.refresh(review_task)
            assert (
                pass_task is not None and pass_task.phase != ParentTaskPhase.AWAITING_CONFIRMATION
            )
            assert warning_task.phase == ParentTaskPhase.AWAITING_CONFIRMATION
            assert review_task.phase == ParentTaskPhase.AWAITING_CONFIRMATION
            auto_events = list(
                await session.scalars(
                    select(AuditEvent).where(AuditEvent.action == "AUTO_CONFIRM_TASK")
                )
            )
            assert len(auto_events) == 1
            assert auto_events[0].entity_id == passed["id"]


@pytest.mark.asyncio
async def test_complete_fake_flow_is_deliverable_and_idempotent(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, app):
        task = await create_analyzed_task(client)
        assert task["phase"] == "AWAITING_CONFIRMATION"
        assert task["consistencyLevel"] == "PASS"
        assert all(variant["promptHash"] for variant in task["variants"])
        analyzing_timings = {stage["key"]: stage for stage in task["timing"]["stages"]}
        assert analyzing_timings["SOURCE_UPLOAD"]["durationSeconds"] == 1.2
        assert analyzing_timings["ANALYSIS"]["status"] == "COMPLETED"
        assert analyzing_timings["ANALYSIS"]["attemptCount"] == 1
        assert analyzing_timings["CONFIRMATION"]["status"] == "ACTIVE"
        response = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("confirm-1"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert response.status_code == 200, response.text
        completed = response.json()
        assert completed["phase"] == "DELIVERABLE"
        assert {variant["kind"] for variant in completed["variants"]} == {
            "STABLE",
            "DYNAMIC",
        }
        assert all(variant["downloadStatus"] == "READY" for variant in completed["variants"])
        completed_timings = {stage["key"]: stage for stage in completed["timing"]["stages"]}
        assert completed_timings["MATERIALIZATION"]["status"] == "COMPLETED"
        assert completed_timings["GENERATION"]["status"] == "COMPLETED"
        assert completed_timings["DOWNLOAD"]["status"] == "COMPLETED"
        artifact_id = completed["variants"][0]["downloadArtifactId"]
        download = await client.get(f"/api/v1/downloads/{artifact_id}", headers=user_headers())
        assert download.status_code == 200
        assert download.content[4:8] == b"ftyp"

        replayed = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("confirm-1"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert replayed.status_code == 200
        async with app.state.database.session_factory() as session:
            command_count = await session.scalar(
                select(func.count()).select_from(GenerationCommand)
            )
            terminal_count = await session.scalar(
                select(func.count())
                .select_from(GenerationCommand)
                .where(GenerationCommand.status == CommandStatus.TERMINAL)
            )
        assert (command_count, terminal_count) == (2, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["STABLE", "DYNAMIC"])
async def test_single_output_flow_only_generates_the_requested_variant(
    tmp_path: Path,
    variant: str,
) -> None:
    async with running_app(tmp_path / variant.lower()) as (client, app):
        task = await create_analyzed_task(
            client,
            client_task_id=f"single-{variant.lower()}",
            variants=[variant],
        )
        assert [item["kind"] for item in task["variants"]] == [variant]

        response = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers(f"confirm-single-{variant.lower()}"),
            json={"expectedStateVersion": task["stateVersion"]},
        )

        assert response.status_code == 200, response.text
        completed = response.json()
        assert completed["phase"] == "DELIVERABLE"
        assert [item["kind"] for item in completed["variants"]] == [variant]
        assert completed["variants"][0]["downloadStatus"] == "READY"
        async with app.state.database.session_factory() as session:
            command_count = await session.scalar(
                select(func.count()).select_from(GenerationCommand)
            )
        assert command_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["STABLE", "DYNAMIC"])
async def test_confirmation_can_narrow_a_dual_output_task_to_one_variant(
    tmp_path: Path,
    variant: str,
) -> None:
    async with running_app(tmp_path / variant[0].lower()) as (client, app):
        task = await create_analyzed_task(
            client,
            client_task_id=f"confirm-{variant.lower()}",
        )
        assert {item["kind"] for item in task["variants"]} == {"STABLE", "DYNAMIC"}

        response = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers(f"confirm-narrow-{variant.lower()}"),
            json={
                "expectedStateVersion": task["stateVersion"],
                "variants": [variant],
            },
        )

        assert response.status_code == 200, response.text
        completed = response.json()
        assert [item["kind"] for item in completed["variants"]] == [variant]
        async with app.state.database.session_factory() as session:
            command_count = await session.scalar(
                select(func.count()).select_from(GenerationCommand)
            )
        assert command_count == 1


@pytest.mark.asyncio
async def test_completed_task_reuse_clones_assets_and_only_selected_prompts(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path) as (client, _app):
        source = await create_analyzed_task(
            client,
            client_task_id="reuse-source",
        )
        completed_response = await client.post(
            f"/api/v1/tasks/{source['id']}/confirm",
            headers=user_headers("reuse-source-confirm"),
            json={"expectedStateVersion": source["stateVersion"]},
        )
        assert completed_response.status_code == 200, completed_response.text
        completed = completed_response.json()
        source_dynamic = next(item for item in completed["variants"] if item["kind"] == "DYNAMIC")

        payload = {
            "clientTaskId": "reuse-dynamic-only",
            "title": "Reused dynamic task",
            "expectedSourceStateVersion": completed["stateVersion"],
            "variants": ["DYNAMIC"],
        }
        reused_response = await client.post(
            f"/api/v1/tasks/{completed['id']}/reuse",
            headers=user_headers("reuse-dynamic"),
            json=payload,
        )

        assert reused_response.status_code == 201, reused_response.text
        reused = reused_response.json()
        assert reused["phase"] == "AWAITING_CONFIRMATION"
        assert [item["kind"] for item in reused["variants"]] == ["DYNAMIC"]
        assert reused["variants"][0]["promptText"] == source_dynamic["promptText"]
        assert [item["sha256"] for item in reused["assets"]] == [
            item["sha256"] for item in completed["assets"]
        ]
        assert {item["id"] for item in reused["assets"]}.isdisjoint(
            {item["id"] for item in completed["assets"]}
        )

        replayed = await client.post(
            f"/api/v1/tasks/{completed['id']}/reuse",
            headers=user_headers("reuse-dynamic"),
            json=payload,
        )
        assert replayed.status_code == 201
        assert replayed.json()["id"] == reused["id"]

        confirmed_response = await client.post(
            f"/api/v1/tasks/{reused['id']}/confirm",
            headers=user_headers("reuse-dynamic-confirm"),
            json={"expectedStateVersion": reused["stateVersion"]},
        )
        assert confirmed_response.status_code == 200, confirmed_response.text
        confirmed = confirmed_response.json()
        assert confirmed["phase"] == "DELIVERABLE"
        assert [item["kind"] for item in confirmed["variants"]] == ["DYNAMIC"]


@pytest.mark.asyncio
async def test_product_reference_is_analyzed_but_not_uploaded_to_libtv(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, app):
        uploads = []
        for index, (name, color) in enumerate(
            (("storyboard.png", "#217a58"), ("product.png", "#d6a32d")), start=1
        ):
            response = await client.post(
                "/api/v1/uploads",
                headers=user_headers(f"split-upload-{index}"),
                files={"file": (name, png_bytes(color), "image/png")},
            )
            assert response.status_code == 201, response.text
            uploads.append(response.json())
        response = await client.post(
            "/api/v1/tasks",
            headers=user_headers("split-create"),
            json={
                "clientTaskId": "split-inputs",
                "title": "Split inputs",
                "storyboards": [{"uploadId": uploads[0]["id"], "order": 1}],
                "productImages": [{"uploadId": uploads[1]["id"], "order": 1}],
            },
        )
        assert response.status_code == 201, response.text
        draft = response.json()
        assert [(asset["role"], asset["usedForGeneration"]) for asset in draft["assets"]] == [
            ("STORYBOARD", True),
            ("PRODUCT", False),
        ]
        analyzed = await client.post(
            f"/api/v1/tasks/{draft['id']}/analyze",
            headers=user_headers("split-analyze"),
            json={"expectedStateVersion": draft["stateVersion"]},
        )
        assert analyzed.status_code == 202, analyzed.text
        task = await wait_for_task_phase(client, draft["id"], "AWAITING_CONFIRMATION")
        confirmed = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("split-confirm"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert app.state.libtv_adapter.upload_count == 1


@pytest.mark.asyncio
async def test_cross_user_isolation_and_duplicate_submit_protection(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, app):
        task = await create_analyzed_task(client)
        hidden = await client.get(
            f"/api/v1/tasks/{task['id']}", headers=user_headers(user_id=OTHER_USER_ID)
        )
        assert hidden.status_code == 404
        created = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("confirm-original"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert created.status_code == 200
        duplicate = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("confirm-new-key"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert duplicate.status_code == 409
        async with app.state.database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(GenerationCommand)) == 2


@pytest.mark.asyncio
async def test_unknown_is_reconciled_read_only_without_resubmit(tmp_path: Path) -> None:
    async with running_app(tmp_path, "exit_after_task") as (client, app):
        task = await create_analyzed_task(client)
        response = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("confirm-unknown"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["phase"] == "ACTION_REQUIRED"
        unknown = await client.get(
            "/api/v1/admin/reconciliations", headers=user_headers(user_id=ADMIN_ID)
        )
        assert unknown.status_code == 200
        assert len(unknown.json()) == 1
        reconciled_attempts = 0
        while unknown.json():
            item = unknown.json()[0]
            reconciled = await client.post(
                f"/api/v1/admin/reconciliations/{item['attemptId']}/classify",
                headers=user_headers(f"reconcile-{item['attemptId']}", user_id=ADMIN_ID),
                json={"action": "RECONCILE"},
            )
            assert reconciled.status_code == 200, reconciled.text
            assert reconciled.json()["status"] == "SUCCEEDED"
            reconciled_attempts += 1
            unknown = await client.get(
                "/api/v1/admin/reconciliations", headers=user_headers(user_id=ADMIN_ID)
            )
        assert reconciled_attempts == 2
        final = await client.get(f"/api/v1/tasks/{task['id']}", headers=user_headers())
        assert final.json()["phase"] == "DELIVERABLE"
        async with app.state.database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(GenerationCommand)) == 2


@pytest.mark.asyncio
async def test_partial_success_and_materialization_fault(tmp_path: Path) -> None:
    async with running_app(tmp_path / "partial", "dynamic_terminal_failure") as (client, _):
        task = await create_analyzed_task(client)
        response = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("confirm-partial"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert response.status_code == 200
        assert response.json()["phase"] == "PARTIALLY_DELIVERABLE"
        assert [variant["generationStatus"] for variant in response.json()["variants"]].count(
            "SUCCEEDED"
        ) == 1
        partial_timings = {stage["key"]: stage for stage in response.json()["timing"]["stages"]}
        assert partial_timings["DOWNLOAD"]["status"] == "COMPLETED"

    async with running_app(tmp_path / "materialize", "upload_fail_1") as (client, _):
        task = await create_analyzed_task(client, colors=["#113355"])
        response = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("confirm-materialize-fail"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert response.status_code == 409
        current = await client.get(f"/api/v1/tasks/{task['id']}", headers=user_headers())
        assert current.json()["phase"] == "ACTION_REQUIRED"


def test_runner_recovery_contract_covers_restart_pid_and_disk_cases() -> None:
    identity = ProcessIdentity("host", 10, "now", "nonce", "exe", "command")
    assert process_identity_matches(identity, identity)
    assert (
        classify_recovery(
            launch_started=True,
            command_host_alive=True,
            identity_matches=True,
            terminal_result_valid=False,
            host_restarted=False,
        )
        == "RUNNING"
    )
    assert (
        classify_recovery(
            launch_started=True,
            command_host_alive=True,
            identity_matches=False,
            terminal_result_valid=False,
            host_restarted=False,
        )
        == "MANUAL_REVIEW"
    )
    assert (
        classify_recovery(
            launch_started=True,
            command_host_alive=False,
            identity_matches=False,
            terminal_result_valid=False,
            host_restarted=True,
        )
        == "RECOVERY_AUDIT"
    )
    assert (
        classify_recovery(
            launch_started=True,
            command_host_alive=False,
            identity_matches=False,
            terminal_result_valid=False,
            host_restarted=False,
            log_writable=False,
        )
        == "UNKNOWN"
    )


@pytest.mark.asyncio
async def test_batch_confirmation_and_remote_restore_do_not_recharge(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, app):
        first = await create_analyzed_task(client, ["#334455"], "batch-1")
        second = await create_analyzed_task(client, ["#885522"], "batch-2")
        payload = {
            "tasks": [
                {
                    "taskId": task["id"],
                    "expectedStateVersion": task["stateVersion"],
                }
                for task in (first, second)
            ]
        }
        preflight = await client.post(
            "/api/v1/confirmations/preflight", headers=user_headers(), json=payload
        )
        assert preflight.json()["estimatedPoints"] == 480
        executed = await client.post(
            "/api/v1/confirmations/execute", headers=user_headers("batch-execute"), json=payload
        )
        assert executed.status_code == 200, executed.text
        batch = executed.json()
        assert batch["succeededCount"] == 2
        assert batch["failedCount"] == 0
        confirmed_tasks = [result["task"] for result in batch["results"]]
        assert [task["phase"] for task in confirmed_tasks] == [
            "DELIVERABLE",
            "DELIVERABLE",
        ]

        stable = next(
            variant for variant in confirmed_tasks[0]["variants"] if variant["kind"] == "STABLE"
        )
        async with app.state.database.session_factory() as session:
            stable_variant = await session.get(GenerationVariant, uuid.UUID(stable["id"]))
            assert stable_variant
            stable_variant.download_status = DownloadStatus.DOWNLOADING
            await session.commit()
        duplicate_restore = await client.post(
            f"/api/v1/tasks/{first['id']}/restore-remote-output",
            headers=user_headers("restore-while-downloading"),
            json={"variant": "STABLE"},
        )
        assert duplicate_restore.status_code == 409
        assert duplicate_restore.json()["detail"]["code"] == "DOWNLOAD_ALREADY_IN_PROGRESS"

        async with app.state.database.session_factory() as session:
            resumed = await RunnerSupervisor(
                app.state.libtv_adapter,
                app.state.object_store,
                app.state.settings,
            ).resume_incomplete_downloads(session)
            stable_variant = await session.get(GenerationVariant, uuid.UUID(stable["id"]))
            assert resumed == 1
            assert stable_variant and stable_variant.download_status == DownloadStatus.READY

        artifact_id = uuid.UUID(stable["downloadArtifactId"])
        async with app.state.database.session_factory() as session:
            stable_variant = await session.get(GenerationVariant, uuid.UUID(stable["id"]))
            assert stable_variant
            stable_variant.download_status = DownloadStatus.READY
            artifact = await session.get(DownloadArtifact, artifact_id)
            assert artifact and artifact.object_key
            await app.state.object_store.delete(artifact.object_key)
            artifact.object_key = None
            ledger_before = await session.scalar(select(func.count()).select_from(PointsLedger))
            await session.commit()
        restored = await client.post(
            f"/api/v1/tasks/{first['id']}/restore-remote-output",
            headers=user_headers("restore-stable"),
            json={"variant": "STABLE"},
        )
        assert restored.status_code == 200, restored.text
        refreshed = await client.get(f"/api/v1/tasks/{first['id']}", headers=user_headers())
        assert refreshed.json()["phase"] == "DELIVERABLE"
        async with app.state.database.session_factory() as session:
            ledger_after = await session.scalar(select(func.count()).select_from(PointsLedger))
            artifact_count = await session.scalar(
                select(func.count()).select_from(DownloadArtifact)
            )
        assert ledger_after == ledger_before
        assert artifact_count == 5


@pytest.mark.asyncio
async def test_batch_confirmation_reports_each_result_and_replays_it(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, _):
        first = await create_analyzed_task(client, ["#334455"], "batch-partial-1")
        second = await create_analyzed_task(client, ["#885522"], "batch-partial-2")
        payload = {
            "tasks": [
                {"taskId": first["id"], "expectedStateVersion": first["stateVersion"]},
                {
                    "taskId": second["id"],
                    "expectedStateVersion": second["stateVersion"] + 1,
                },
            ]
        }
        headers = user_headers("batch-partial-results")

        executed = await client.post("/api/v1/confirmations/execute", headers=headers, json=payload)
        replayed = await client.post("/api/v1/confirmations/execute", headers=headers, json=payload)

        assert executed.status_code == 200, executed.text
        assert replayed.json() == executed.json()
        assert executed.json()["succeededCount"] == 1
        assert executed.json()["failedCount"] == 1
        assert [result["status"] for result in executed.json()["results"]] == [
            "SUCCEEDED",
            "FAILED",
        ]
        assert executed.json()["results"][1]["errorCode"] == "VERSION_CONFLICT"
        unchanged = await client.get(f"/api/v1/tasks/{second['id']}", headers=user_headers())
        assert unchanged.json()["phase"] == "AWAITING_CONFIRMATION"


@pytest.mark.asyncio
async def test_new_supervisor_resumes_ready_commands_after_api_restart(
    tmp_path: Path,
) -> None:
    database_url = ""
    task_id = ""
    async with running_app(tmp_path) as (client, app):
        app.state.settings.auto_run_fake_commands = False
        task = await create_analyzed_task(client, ["#1e6d8f"], "restart")
        response = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("confirm-restart"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["phase"] == "QUEUED"
        database_url = app.state.settings.database_url
        task_id = task["id"]

    settings = Settings(
        app_env="test",
        database_url=database_url,
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner-restarted",
        object_store_mode="local",
        _env_file=None,
    )
    restarted = create_app(settings)
    async with restarted.router.lifespan_context(restarted):
        async with restarted.state.database.session_factory() as session:
            processed = await RunnerSupervisor(
                restarted.state.libtv_adapter,
                restarted.state.object_store,
                settings,
                owner="restarted-runner",
            ).run_ready(session)
        assert processed == 2
        async with AsyncClient(
            transport=ASGITransport(app=restarted), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/tasks/{task_id}", headers=user_headers())
            assert response.json()["phase"] == "DELIVERABLE"


@pytest.mark.asyncio
async def test_concurrent_confirmation_has_one_cas_winner(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, app):
        app.state.settings.auto_run_fake_commands = False
        task = await create_analyzed_task(client, ["#406080"], "concurrent-confirm")
        payload = {"expectedStateVersion": task["stateVersion"]}
        first, second = await asyncio.gather(
            client.post(
                f"/api/v1/tasks/{task['id']}/confirm",
                headers=user_headers("concurrent-confirm-a"),
                json=payload,
            ),
            client.post(
                f"/api/v1/tasks/{task['id']}/confirm",
                headers=user_headers("concurrent-confirm-b"),
                json=payload,
            ),
        )
        assert sorted([first.status_code, second.status_code]) == [200, 409]
        loser = first if first.status_code == 409 else second
        assert loser.json()["detail"]["code"] == "VERSION_CONFLICT"
        async with app.state.database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(GenerationCommand)) == 2


@pytest.mark.asyncio
async def test_concurrent_same_idempotency_key_replays_one_create(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (client, _):
        uploaded = await client.post(
            "/api/v1/uploads",
            headers=user_headers("idempotency-upload"),
            files={"file": ("shot.png", png_bytes("#6a3252"), "image/png")},
        )
        payload = {
            "clientTaskId": "idempotency-concurrent",
            "title": "Concurrent idempotency",
            "storyboards": [{"uploadId": uploaded.json()["id"], "order": 1, "required": True}],
            "userRequirement": "",
        }
        first, second = await asyncio.gather(
            client.post(
                "/api/v1/tasks",
                headers=user_headers("same-create-key"),
                json=payload,
            ),
            client.post(
                "/api/v1/tasks",
                headers=user_headers("same-create-key"),
                json=payload,
            ),
        )
        assert first.status_code == second.status_code == 201
        assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_materialization_retry_resumes_same_saga(tmp_path: Path) -> None:
    async with running_app(tmp_path, "upload_fail_1") as (client, app):
        task = await create_analyzed_task(client, ["#315f41"], "materialization-retry")
        failed = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("materialization-retry-confirm"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert failed.status_code == 409
        app.state.libtv_adapter.scenario = "success"
        recovered = await client.post(
            f"/api/v1/admin/tasks/{task['id']}/retry-materialization",
            headers=user_headers("retry-materialization", user_id=ADMIN_ID),
        )
        assert recovered.status_code == 200, recovered.text
        current = await client.get(f"/api/v1/tasks/{task['id']}", headers=user_headers())
        assert current.json()["phase"] == "DELIVERABLE"
        assert app.state.libtv_adapter.upload_count == 2


@pytest.mark.asyncio
async def test_download_interruption_retries_without_new_generation(tmp_path: Path) -> None:
    async with running_app(tmp_path, "download_interrupt_once") as (client, app):
        task = await create_analyzed_task(client, ["#795632"], "download-retry")
        response = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("download-retry-confirm"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["phase"] == "DELIVERABLE"
        assert app.state.libtv_adapter.run_count == 2
        assert app.state.libtv_adapter.download_count == 3


@pytest.mark.asyncio
async def test_complete_synthetic_replay_flow_is_deliverable(tmp_path: Path) -> None:
    async with running_app(tmp_path, libtv_mode="replay", ai_mode="replay") as (client, _):
        task = await create_analyzed_task(client, ["#356c52"], "synthetic-replay")
        assert task["phase"] == "AWAITING_CONFIRMATION"
        assert task["analysisResult"]["modelVersion"] == "synthetic-replay-2.1"
        assert task["analysisResult"]["stablePlan"]["shots"][0]["action"] == "做小幅自然动作"
        response = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("synthetic-replay-confirm"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["phase"] == "DELIVERABLE"
        assert all(variant["downloadStatus"] == "READY" for variant in response.json()["variants"])


@pytest.mark.asyncio
async def test_prepare_only_materializes_two_variants_and_stops_before_paid_boundary(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path) as (client, app):
        task = await create_analyzed_task(client, client_task_id="prepare-only")
        app.state.settings.libtv_adapter_mode = "real"
        app.state.settings.libtv_execution_mode = "prepare-only"

        response = await client.post(
            f"/api/v1/tasks/{task['id']}/confirm",
            headers=user_headers("prepare-only-confirm"),
            json={"expectedStateVersion": task["stateVersion"]},
        )

        assert response.status_code == 200, response.text
        prepared = response.json()
        if prepared["phase"] == "PREPARING":
            prepared = await wait_for_task_phase(client, task["id"], "WAITING_FOR_SEAL")
        assert prepared["phase"] == "WAITING_FOR_SEAL"
        assert prepared["phaseReasonCode"] == "PREPARE_ONLY_COMPLETE"
        assert app.state.libtv_adapter.run_count == 0
        preview = await client.get(
            f"/api/v1/tasks/{task['id']}/generation-preview", headers=user_headers()
        )
        assert preview.status_code == 200, preview.text
        commands = preview.json()["commands"]
        assert len(commands) == 2
        assert all(command["argv"][-1] == "--run" for command in commands)
        assert all(command["estimatedGenerationCount"] == 1 for command in commands)
        assert all(command["authorized"] is False for command in commands)
        assert all(command["parameterSummary"]["smartStoryboard"] is True for command in commands)
        assert await asyncio.to_thread(Path(preview.json()["previewFile"]).is_file)
        async with app.state.database.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(GenerationCommand)) == 0


@pytest.mark.asyncio
async def test_real_confirmation_returns_while_materialization_continues_in_background(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path) as (client, app):
        task = await create_analyzed_task(client, client_task_id="background-confirm")
        app.state.settings.libtv_adapter_mode = "real"
        app.state.settings.libtv_execution_mode = "prepare-only"
        materialization_started = asyncio.Event()
        release_materialization = asyncio.Event()
        original_create_group = app.state.libtv_adapter.create_group

        async def delayed_create_group(*, project_uuid: str, name: str):
            materialization_started.set()
            await release_materialization.wait()
            return await original_create_group(project_uuid=project_uuid, name=name)

        app.state.libtv_adapter.create_group = delayed_create_group
        response = await asyncio.wait_for(
            client.post(
                f"/api/v1/tasks/{task['id']}/confirm",
                headers=user_headers("background-confirm-submit"),
                json={"expectedStateVersion": task["stateVersion"]},
            ),
            timeout=1,
        )

        assert response.status_code == 200, response.text
        assert response.json()["phase"] == "PREPARING"
        await asyncio.wait_for(materialization_started.wait(), timeout=1)
        release_materialization.set()
        prepared = await wait_for_task_phase(client, task["id"], "WAITING_FOR_SEAL")
        assert prepared["phaseReasonCode"] == "PREPARE_ONLY_COMPLETE"
