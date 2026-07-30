import io
import uuid
from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import AttemptStatus, ParentTaskPhase
from libtv_agent.domain.models import Base, GenerationAttempt, GenerationCommand
from libtv_agent.services.material_validator import MaterialDescriptor, validate_materials
from libtv_agent.services.prompt_compiler import PromptCompileInput, compile_video_plan
from libtv_agent.templates.motion_actions import compatible_action_ids, list_motion_actions
from libtv_agent.templates.site_style_profiles import (
    SITE_STYLE_PROFILES,
    get_site_style_profile,
    list_site_style_profiles,
)
from libtv_agent.templates.video_templates import (
    VIDEO_TEMPLATES,
    get_video_template,
    list_video_templates,
)
from PIL import Image
from sqlalchemy import func, select


def png_bytes(color: str = "#217a58") -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (360, 640), color).save(stream, format="PNG")
    return stream.getvalue()


def material(index: int, *, sha256: str | None = None) -> MaterialDescriptor:
    return MaterialDescriptor(
        id=f"asset-{index}",
        order=index,
        original_name=f"storyboard-{index}.jpg",
        mime_type="image/jpeg",
        size_bytes=1024,
        sha256=sha256 or f"{index:064d}",
        width=1080,
        height=1920,
    )


@pytest.mark.parametrize("count", [1, 7])
def test_material_validator_accepts_supported_storyboard_counts(count: int) -> None:
    result = validate_materials(
        [material(index) for index in range(1, count + 1)],
        template=get_video_template("ootd_walk"),
        variant_count=1,
        action_intensity="standard",
        camera_tempo="standard",
        cut_mode="explicit_cuts",
    )

    assert result.valid
    assert result.vision_check_required is False


@pytest.mark.parametrize(
    ("materials", "code"),
    [
        ([], "STORYBOARD_COUNT_INVALID"),
        ([material(index) for index in range(1, 9)], "STORYBOARD_COUNT_INVALID"),
        ([material(1), replace(material(2), order=3)], "STORYBOARD_ORDER_INVALID"),
        ([replace(material(1), mime_type="application/octet-stream")], "IMAGE_MIME_UNSUPPORTED"),
        ([replace(material(1), size_bytes=0)], "IMAGE_EMPTY"),
        ([material(1, sha256="a" * 64), material(2, sha256="a" * 64)], "DUPLICATE_STORYBOARD"),
    ],
)
def test_material_validator_rejects_invalid_inputs(
    materials: list[MaterialDescriptor],
    code: str,
) -> None:
    result = validate_materials(
        materials,
        template=get_video_template("ootd_walk"),
        variant_count=1,
        action_intensity="standard",
        camera_tempo="standard",
        cut_mode="explicit_cuts",
    )

    assert not result.valid
    assert code in {issue.code for issue in result.errors}


def test_registered_templates_are_draft_until_production_prompts_are_supplied() -> None:
    templates = list_video_templates()

    assert {template.id for template in templates} == {
        "ootd_walk",
        "garment_detail",
        "mood_model",
    }
    assert {template.status for template in templates} == {"draft"}


def test_site_style_profiles_are_versioned_and_restricted_sources_are_explicit() -> None:
    profiles = list_site_style_profiles()

    assert {profile.id for profile in profiles} == {
        "geeksoutfit",
        "guidingcross",
        "nerdywave",
        "pagewings",
        "teachersgram",
        "goodnurselife",
        "classyoutlaw",
        "theretrotee",
    }
    assert {profile.status for profile in profiles} == {"draft"}
    assert get_site_style_profile("nerdywave").evidence_level == "restricted_site"


def test_motion_actions_are_filtered_by_video_type() -> None:
    profile = get_site_style_profile("geeksoutfit")

    detail_actions = compatible_action_ids("garment_detail", profile.preferred_actions)

    assert "controlled_walk" not in detail_actions
    assert "print_detail_pause" in detail_actions


def test_motion_action_library_has_structured_execution_and_risk_metadata() -> None:
    actions = list_motion_actions()

    assert len(actions) >= 38
    assert {action.category for action in actions} == {
        "outfit",
        "detail",
        "back",
        "interaction",
        "product",
    }
    assert all(action.purpose and action.compatible_templates for action in actions)
    assert any(action.requirements and action.risk_level == "conditional" for action in actions)
    assert {
        "graphic_glance_return",
        "collar_frame_release",
        "lapel_open_hold",
        "pocket_insert_release",
        "cuff_adjust_release",
        "layer_reveal_return",
        "garment_sway_settle",
        "diagonal_step_turn",
        "seated_weight_shift",
        "lean_release",
        "stand_from_seat_settle",
        "existing_prop_return",
    }.issubset({action.id for action in actions})


def test_prompt_compiler_rejects_draft_template_for_production() -> None:
    with pytest.raises(ValueError, match="not active"):
        compile_video_plan(
            PromptCompileInput(
                template=get_video_template("ootd_walk"),
                storyboard_count=1,
                action_intensity="standard",
                camera_tempo="standard",
                cut_mode="explicit_cuts",
                variant_index=1,
            )
        )


def test_prompt_compiler_is_deterministic_and_describes_change_not_image_facts() -> None:
    template = get_video_template("ootd_walk")
    compiled = compile_video_plan(
        PromptCompileInput(
            template=template,
            storyboard_count=3,
            action_intensity="standard",
            camera_tempo="slow",
            cut_mode="explicit_cuts",
            variant_index=2,
        ),
        allow_draft=True,
    )
    repeated = compile_video_plan(
        PromptCompileInput(
            template=template,
            storyboard_count=3,
            action_intensity="standard",
            camera_tempo="slow",
            cut_mode="explicit_cuts",
            variant_index=2,
        ),
        allow_draft=True,
    )

    assert compiled == repeated
    assert len(compiled.shot_instructions) == 3
    assert "动作" in compiled.master_prompt
    assert "镜头" in compiled.master_prompt
    assert "切镜" in compiled.master_prompt
    assert "保持人物身份一致" in compiled.master_prompt
    assert "发型" not in compiled.master_prompt
    assert "五官" not in compiled.master_prompt
    assert "背景里" not in compiled.master_prompt


def test_prompt_compiler_injects_site_style_without_rewriting_image_facts() -> None:
    profile = get_site_style_profile("classyoutlaw")
    compiled = compile_video_plan(
        PromptCompileInput(
            template=get_video_template("mood_model"),
            storyboard_count=2,
            action_intensity="standard",
            camera_tempo="standard",
            cut_mode="explicit_cuts",
            variant_index=1,
            site_profile=profile,
        ),
        allow_draft=True,
    )

    assert compiled.site_profile_id == "classyoutlaw"
    assert compiled.site_profile_version == profile.version
    assert "叛逆、超现实、强图形" in compiled.master_prompt
    assert "肩胯错位停格" in compiled.master_prompt
    assert "身体变形" in compiled.negative_prompt
    assert "发型" not in compiled.master_prompt


def test_variants_have_limited_differences_without_changing_invariants() -> None:
    template = get_video_template("garment_detail")
    variants = [
        compile_video_plan(
            PromptCompileInput(
                template=template,
                storyboard_count=2,
                action_intensity="standard",
                camera_tempo="standard",
                cut_mode="explicit_cuts",
                variant_index=index,
            ),
            allow_draft=True,
        )
        for index in range(1, 5)
    ]

    assert len({item.master_prompt for item in variants}) == 4
    assert len({item.invariants for item in variants}) == 1
    assert len({item.negative_prompt for item in variants}) == 1


@pytest.mark.asyncio
async def test_video_template_api_lists_drafts_without_exposing_a_paid_path() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/v1/video-templates",
                headers={"X-User-Id": settings.dev_user_id},
            )

    assert response.status_code == 200
    templates = response.json()
    assert [item["id"] for item in templates] == [
        "ootd_walk",
        "garment_detail",
        "mood_model",
    ]
    assert {item["status"] for item in templates} == {"draft"}
    assert all(item["defaultSettings"]["smartStoryboard"] is False for item in templates)


@pytest.mark.asyncio
async def test_site_style_profile_api_exposes_evidence_and_draft_status() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/v1/site-style-profiles",
                headers={"X-User-Id": settings.dev_user_id},
            )

    assert response.status_code == 200
    profiles = response.json()
    assert len(profiles) == 8
    assert {item["status"] for item in profiles} == {"draft"}
    assert profiles[0]["retrievedAt"] == "2026-07-30"
    assert profiles[0]["cameraLanguage"]
    assert profiles[0]["openingRule"]
    assert any(item["evidenceLevel"] == "restricted_site" for item in profiles)


@pytest.mark.asyncio
async def test_motion_action_api_exposes_prompt_and_compatibility_metadata() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/v1/motion-actions",
                headers={"X-User-Id": settings.dev_user_id},
            )

    assert response.status_code == 200
    actions = response.json()
    assert len(actions) >= 38
    assert {item["category"] for item in actions} == {
        "outfit",
        "detail",
        "back",
        "interaction",
        "product",
    }
    assert all(item["compatibleTemplates"] for item in actions)


@pytest.mark.asyncio
async def test_video_task_requires_explicit_paid_submission_consent(tmp_path) -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        object_store_mode="local",
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/video-tasks",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": "fixed-consent-required",
                },
                json={
                    "clientTaskId": "fixed-consent-required",
                    "title": "Fixed consent",
                    "storyboards": [
                        {
                            "uploadId": str(uuid.uuid4()),
                            "order": 1,
                            "required": True,
                        }
                    ],
                    "templateId": "ootd_walk",
                    "siteProfileId": "geeksoutfit",
                    "resultCount": 1,
                    "paidSubmissionConsent": False,
                },
            )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PAID_SUBMISSION_CONSENT_REQUIRED"


@pytest.mark.parametrize("result_count", [1, 4])
@pytest.mark.asyncio
async def test_fixed_video_task_compiles_indexed_kling_results_without_command_when_blocked(
    tmp_path,
    monkeypatch,
    result_count: int,
) -> None:
    monkeypatch.setitem(
        VIDEO_TEMPLATES,
        "ootd_walk",
        replace(VIDEO_TEMPLATES["ootd_walk"], status="active", version="1.0.0-test"),
    )
    monkeypatch.setitem(
        SITE_STYLE_PROFILES,
        "geeksoutfit",
        replace(SITE_STYLE_PROFILES["geeksoutfit"], status="active", version="1.0.0-test"),
    )
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        object_store_mode="local",
        artifact_root=tmp_path / f"artifacts-{result_count}",
        runner_root=tmp_path / f"runner-{result_count}",
        kling_cli_enabled=False,
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            uploaded = await client.post(
                "/api/v1/uploads",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": f"fixed-upload-{result_count}",
                },
                files={"file": ("shot.png", png_bytes(), "image/png")},
            )
            assert uploaded.status_code == 201, uploaded.text
            assert uploaded.json()["sizeBytes"] > 0
            response = await client.post(
                "/api/v1/video-tasks",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": f"fixed-create-{result_count}",
                },
                json={
                    "clientTaskId": f"fixed-{result_count}",
                    "title": f"Fixed {result_count}",
                    "storyboards": [
                        {"uploadId": uploaded.json()["id"], "order": 1, "required": True}
                    ],
                    "templateId": "ootd_walk",
                    "siteProfileId": "geeksoutfit",
                    "resultCount": result_count,
                    "actionIntensity": "standard",
                    "cameraTempo": "standard",
                    "cutMode": "explicit_cuts",
                    "paidSubmissionConsent": True,
                },
            )
            assert response.status_code == 201, response.text
            task = response.json()
            assert task["workflowKind"] == "FIXED_TEMPLATE"
            assert task["generationProvider"] == "kling"
            assert task["phase"] == "ACTION_REQUIRED"
            assert task["phaseReasonCode"] == "KLING_CAPABILITY_UNSUPPORTED"
            assert [variant["variantIndex"] for variant in task["variants"]] == list(
                range(1, result_count + 1)
            )
            assert {variant["kind"] for variant in task["variants"]} == {"STABLE"}
            assert len(task["compiledPlan"]["variants"]) == result_count
            assert task["materialValidation"]["valid"] is True
            assert task["paidSubmissionConsentAt"] is not None
        async with app.state.database.session_factory() as session:
            command_count = await session.scalar(
                select(func.count()).select_from(GenerationCommand)
            )
            assert command_count == 0


@pytest.mark.asyncio
async def test_fixed_video_task_queues_only_kling_commands_without_analysis(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setitem(
        VIDEO_TEMPLATES,
        "garment_detail",
        replace(VIDEO_TEMPLATES["garment_detail"], status="active", version="1.0.0-test"),
    )
    monkeypatch.setitem(
        SITE_STYLE_PROFILES,
        "teachersgram",
        replace(SITE_STYLE_PROFILES["teachersgram"], status="active", version="1.0.0-test"),
    )

    async def allow_kling(*args, **kwargs) -> None:
        del args, kwargs

    async def prepare_without_provider_call(session, adapter, object_store, task, settings):
        del adapter, object_store, settings
        attempts = []
        for variant in task.variants:
            attempt = GenerationAttempt(
                variant_id=variant.id,
                provider="kling_official_cli",
                provider_model="test-model",
                provider_status="queued",
                intent_hash=f"intent-{variant.variant_index}",
                status=AttemptStatus.PREPARED,
            )
            session.add(attempt)
            attempts.append(attempt)
        task.phase = ParentTaskPhase.QUEUED
        await session.flush()
        return attempts

    monkeypatch.setattr(
        "libtv_agent.services.fixed_video_tasks.ensure_provider_submission_allowed",
        allow_kling,
    )
    monkeypatch.setattr(
        "libtv_agent.services.fixed_video_tasks.prepare_kling_task",
        prepare_without_provider_call,
    )
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        object_store_mode="local",
        artifact_root=tmp_path / "artifacts-queued",
        runner_root=tmp_path / "runner-queued",
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            uploaded = await client.post(
                "/api/v1/uploads",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": "fixed-queued-upload",
                },
                files={"file": ("shot.png", png_bytes("#76444a"), "image/png")},
            )
            response = await client.post(
                "/api/v1/video-tasks",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": "fixed-queued-create",
                },
                json={
                    "clientTaskId": "fixed-queued",
                    "title": "Fixed queued",
                    "storyboards": [
                        {"uploadId": uploaded.json()["id"], "order": 1, "required": True}
                    ],
                    "templateId": "garment_detail",
                    "siteProfileId": "teachersgram",
                    "resultCount": 4,
                    "paidSubmissionConsent": True,
                },
            )
            assert response.status_code == 201, response.text
            task = response.json()
            assert task["phase"] == "QUEUED"
            assert task["analysisResult"] is None
            assert task["analysisRunId"] is None
            assert [variant["variantIndex"] for variant in task["variants"]] == [1, 2, 3, 4]
            assert {variant["provider"] for variant in task["variants"]} == {"kling_official_cli"}
        async with app.state.database.session_factory() as session:
            commands = list(await session.scalars(select(GenerationCommand)))
            assert len(commands) == 4
            assert {command.command_manifest_json["provider"] for command in commands} == {"kling"}
