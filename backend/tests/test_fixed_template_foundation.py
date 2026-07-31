import asyncio
import io
import uuid
from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import AttemptStatus, ParentTaskPhase
from libtv_agent.domain.models import (
    Asset,
    Base,
    GenerationAttempt,
    GenerationCommand,
    GenerationVariant,
    SubjectElementJob,
)
from libtv_agent.domain.schemas import VideoTaskCreate
from libtv_agent.services.fixed_video_tasks import (
    FixedVideoTaskValidationError,
    _validate_final_prompt_length,
)
from libtv_agent.services.material_validator import MaterialDescriptor, validate_materials
from libtv_agent.services.prompt_compiler import PromptCompileInput, compile_video_plan
from libtv_agent.templates.motion_actions import (
    ActionCapability,
    ActionContext,
    compatible_action_ids,
    list_motion_actions,
)
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


def test_video_task_subject_images_are_optional_ordered_and_exclusive_with_elements() -> None:
    common = {
        "clientTaskId": "subject-schema",
        "title": "Subject schema",
        "storyboards": [{"uploadId": str(uuid.uuid4()), "order": 1}],
        "templateId": "ootd_walk",
        "siteProfileId": "geeksoutfit",
        "paidSubmissionConsent": True,
    }

    without_subject = VideoTaskCreate.model_validate({**common, "subjectImages": []})
    assert without_subject.subject_images == []

    with_one_subject = VideoTaskCreate.model_validate(
        {
            **common,
            "subjectImages": [{"uploadId": str(uuid.uuid4()), "order": 1}],
        }
    )
    assert len(with_one_subject.subject_images) == 1
    with pytest.raises(ValueError, match="mutually exclusive"):
        VideoTaskCreate.model_validate(
            {
                **common,
                "subjectImages": [
                    {"uploadId": str(uuid.uuid4()), "order": 1},
                    {"uploadId": str(uuid.uuid4()), "order": 2},
                ],
                "elementIds": ["element-1"],
            }
        )
    with pytest.raises(ValueError, match="7-reference limit"):
        VideoTaskCreate.model_validate(
            {
                **common,
                "storyboards": [
                    {"uploadId": str(uuid.uuid4()), "order": order} for order in range(1, 5)
                ],
                "subjectImages": [
                    {"uploadId": str(uuid.uuid4()), "order": order} for order in range(1, 5)
                ],
            }
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


def test_registered_templates_are_active_after_prompt_contract_verification() -> None:
    templates = list_video_templates()

    assert {template.id for template in templates} == {
        "ootd_walk",
        "garment_detail",
        "mood_model",
    }
    assert {template.status for template in templates} == {"active"}
    assert {template.version for template in templates} == {"1.0.0"}


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
        "orionride",
        "ironpandafit",
        "tokyotiger",
        "boldoversize",
    }
    assert {profile.id for profile in profiles if profile.status == "active"} == {
        "geeksoutfit",
        "guidingcross",
        "teachersgram",
        "classyoutlaw",
        "theretrotee",
        "orionride",
        "ironpandafit",
        "tokyotiger",
        "boldoversize",
    }
    restricted = {profile.id for profile in profiles if profile.evidence_level == "restricted_site"}
    assert restricted == {"nerdywave", "pagewings", "goodnurselife"}
    assert all(
        profile.status == "draft"
        for profile in profiles
        if profile.evidence_level == "restricted_site"
    )


def test_motion_actions_are_filtered_by_video_type() -> None:
    profile = get_site_style_profile("geeksoutfit")

    detail_actions = compatible_action_ids(
        "garment_detail",
        profile.preferred_actions,
        context=ActionContext(confirmed=frozenset({ActionCapability.FRONT_PRINT_VISIBLE})),
    )

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
        "front_back_quarter_return",
        "hair_tuck_release",
        "seated_prop_sip_return",
    }.issubset({action.id for action in actions})


def test_prompt_compiler_rejects_draft_template_for_production() -> None:
    draft_template = replace(get_video_template("ootd_walk"), status="draft")
    with pytest.raises(ValueError, match="not active"):
        compile_video_plan(
            PromptCompileInput(
                template=draft_template,
                storyboard_count=1,
                result_count=1,
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
            result_count=4,
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
            result_count=4,
            action_intensity="standard",
            camera_tempo="slow",
            cut_mode="explicit_cuts",
            variant_index=2,
        ),
        allow_draft=True,
    )

    assert compiled == repeated
    assert len(compiled.shot_instructions) == 3
    assert all(shot.instruction in compiled.master_prompt for shot in compiled.shot_instructions)
    assert "时间轴：" in compiled.master_prompt
    assert "0-3.33秒（输入图1）" in compiled.master_prompt
    assert "3.33-6.67秒（输入图2）" in compiled.master_prompt
    assert "6.67-10秒（输入图3）" in compiled.master_prompt
    assert "动作" in compiled.master_prompt
    assert "镜头" in compiled.master_prompt
    assert "切镜" in compiled.master_prompt
    assert "保持人物身份、面部特征和体型一致" in compiled.master_prompt
    assert "服装款式、颜色、面料、版型、印花、Logo和文字内容不变" in compiled.master_prompt
    assert "布料真实的厚度、重量、体积、垂坠、褶皱、包裹关系与接触阴影" in compiled.master_prompt
    assert "避免服装出现贴图感、漂浮感和不自然反光" in compiled.master_prompt
    assert "场景、背景陈设和光线条件不变" in compiled.master_prompt
    assert "分镜结构、镜头对应关系及素材先后顺序" in compiled.master_prompt
    assert "皮肤保留真实纹理和自然细节" in compiled.master_prompt
    assert "避免过度磨皮、塑料感和蜡感" in compiled.master_prompt
    assert "真实日常UGC记录感" in compiled.master_prompt
    assert "不呈现精修商业广告感" in compiled.master_prompt
    assert "发型" not in compiled.master_prompt
    assert "五官" not in compiled.master_prompt
    assert "背景里" not in compiled.master_prompt


def test_prompt_compiler_injects_site_style_without_rewriting_image_facts() -> None:
    profile = get_site_style_profile("classyoutlaw")
    compiled = compile_video_plan(
        PromptCompileInput(
            template=get_video_template("mood_model"),
            storyboard_count=2,
            result_count=1,
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
    assert profile.expression_language.rstrip("。；") in compiled.master_prompt
    assert "肩胯错位停格" in compiled.master_prompt
    assert "身体变形" in compiled.negative_prompt
    assert "发型" not in compiled.master_prompt


def test_prompt_compiler_keeps_cut_mode_authoritative_and_ignores_legacy_tempo() -> None:
    common = {
        "template": get_video_template("ootd_walk"),
        "storyboard_count": 3,
        "result_count": 4,
        "action_intensity": "standard",
        "cut_mode": "explicit_cuts",
        "variant_index": 4,
        "site_profile": get_site_style_profile("ironpandafit"),
    }
    slow = compile_video_plan(PromptCompileInput(camera_tempo="slow", **common))
    fast = compile_video_plan(PromptCompileInput(camera_tempo="fast", **common))

    assert slow.master_prompt == fast.master_prompt
    assert "按照输入分镜顺序允许明确、干净的切镜" in slow.master_prompt
    assert "一次干净切镜" not in slow.master_prompt
    assert "节奏变化：" not in slow.master_prompt


def test_site_style_does_not_inject_unverified_shots_or_product_faces() -> None:
    compiled = compile_video_plan(
        PromptCompileInput(
            template=get_video_template("garment_detail"),
            storyboard_count=1,
            result_count=1,
            action_intensity="standard",
            camera_tempo="standard",
            cut_mode="explicit_cuts",
            variant_index=1,
            site_profile=get_site_style_profile("orionride"),
        )
    )

    assert "站点表达只作用于已有素材支持" in compiled.master_prompt
    assert "视频结构：" not in compiled.master_prompt
    assert "优先镜头：" not in compiled.master_prompt
    assert "商品呈现重点：" not in compiled.master_prompt
    assert "背面图形" not in compiled.master_prompt
    assert "背面中近景" not in compiled.master_prompt


def test_final_prompt_length_includes_reference_role_text() -> None:
    accepted = _validate_final_prompt_length("x" * 3072, code="TOO_LONG", message="too long")
    assert len(accepted) == 3072

    with pytest.raises(FixedVideoTaskValidationError) as exc_info:
        _validate_final_prompt_length("x" * 3073, code="TOO_LONG", message="too long")

    assert exc_info.value.code == "TOO_LONG"
    assert exc_info.value.details == {"finalLength": 3073, "limit": 3072}


def test_all_site_profiles_define_distinct_character_expression_language() -> None:
    profiles = list_site_style_profiles()
    expressions = {profile.expression_language for profile in profiles}

    assert len(expressions) == len(profiles)
    assert all(expression != "自然、克制并服务于商品展示" for expression in expressions)


def test_variants_have_limited_differences_without_changing_invariants() -> None:
    template = get_video_template("garment_detail")
    variants = [
        compile_video_plan(
            PromptCompileInput(
                template=template,
                storyboard_count=2,
                result_count=4,
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
    assert len({item.shot_instructions for item in variants}) == 1
    normalized_prompts = {
        item.master_prompt.replace(str(item.variant_seed["modifier"]), "<variant>")
        for item in variants
    }
    assert len(normalized_prompts) == 1
    for item in variants:
        modifier = str(item.variant_seed["modifier"])
        assert all(label in modifier for label in ("动作变化：", "神态变化：", "视频风格变化："))
        assert "节奏变化：" not in modifier
        assert "自行调整" not in modifier
        assert "轻微动作组合" not in modifier
        assert "有限运镜方式" not in modifier


def test_all_production_prompt_combinations_fit_kling_limit() -> None:
    active_profiles = [
        profile for profile in list_site_style_profiles() if profile.status == "active"
    ]

    for template in list_video_templates():
        for profile in active_profiles:
            for variant_index in range(1, 5):
                compiled = compile_video_plan(
                    PromptCompileInput(
                        template=template,
                        storyboard_count=template.max_images,
                        result_count=4,
                        action_intensity="standard",
                        camera_tempo="standard",
                        cut_mode="explicit_cuts",
                        variant_index=variant_index,
                        site_profile=profile,
                    )
                )
                assert len(compiled.master_prompt) <= 3072


def test_restricted_site_profile_cannot_enter_production() -> None:
    with pytest.raises(ValueError, match="not active"):
        compile_video_plan(
            PromptCompileInput(
                template=get_video_template("ootd_walk"),
                storyboard_count=1,
                result_count=1,
                action_intensity="standard",
                camera_tempo="standard",
                cut_mode="explicit_cuts",
                variant_index=1,
                site_profile=get_site_style_profile("nerdywave"),
            )
        )


@pytest.mark.asyncio
async def test_video_template_api_lists_verified_active_templates() -> None:
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
    assert {item["status"] for item in templates} == {"active"}
    assert all(item["defaultSettings"]["smartStoryboard"] is True for item in templates)


@pytest.mark.asyncio
async def test_site_style_profile_api_exposes_evidence_gated_status() -> None:
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
    assert len(profiles) == 12
    assert {item["id"] for item in profiles if item["status"] == "active"} == {
        "geeksoutfit",
        "guidingcross",
        "teachersgram",
        "classyoutlaw",
        "theretrotee",
        "orionride",
        "ironpandafit",
        "tokyotiger",
        "boldoversize",
    }
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
async def test_catalog_editor_preserves_action_safety_capabilities_and_versions_styles() -> None:
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
            headers = {"X-User-Id": settings.dev_admin_id}
            actions_response = await client.get("/api/v1/motion-actions", headers=headers)
            assert actions_response.status_code == 200
            action = next(
                item for item in actions_response.json() if item["id"] == "one_step_settle"
            )
            assert action.pop("requiredCapabilities") == ["forward_step_space"]
            action["label"] = f"{action['label']} edited"

            update_action_response = await client.put(
                "/api/v1/motion-actions/one_step_settle",
                headers=headers,
                json=action,
            )
            assert update_action_response.status_code == 200, update_action_response.text
            assert update_action_response.json()["requiredCapabilities"] == ["forward_step_space"]

            profiles_response = await client.get(
                "/api/v1/site-style-profiles",
                headers=headers,
            )
            assert profiles_response.status_code == 200
            profile = next(
                item for item in profiles_response.json() if item["id"] == "goodnurselife"
            )
            assert profile.pop("version") == "0.1.0-research"
            profile["researchNote"] = f"{profile['researchNote']} edited"

            update_profile_response = await client.put(
                "/api/v1/site-style-profiles/goodnurselife",
                headers=headers,
                json=profile,
            )
            assert update_profile_response.status_code == 200, update_profile_response.text
            assert update_profile_response.json()["version"] == "0.1.1"


@pytest.mark.asyncio
async def test_catalog_editor_rejects_invalid_references_and_requires_editor_role() -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )
    app = create_app(settings)
    action_payload = {
        "id": "catalog_test_action",
        "label": "Catalog test action",
        "category": "outfit",
        "instruction": "Start in a stable pose, shift once, then stop with the garment visible.",
        "purpose": "Keep the whole garment visible.",
        "compatibleTemplates": ["missing_template"],
        "requirements": [],
        "avoid": [],
        "riskLevel": "low",
    }
    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            forbidden_response = await client.post(
                "/api/v1/motion-actions",
                headers={"X-User-Id": settings.dev_user_id},
                json=action_payload,
            )
            assert forbidden_response.status_code == 403

            invalid_template_response = await client.post(
                "/api/v1/motion-actions",
                headers={"X-User-Id": settings.dev_admin_id},
                json=action_payload,
            )
            assert invalid_template_response.status_code == 422
            assert "missing_template" in invalid_template_response.text

            profiles_response = await client.get(
                "/api/v1/site-style-profiles",
                headers={"X-User-Id": settings.dev_admin_id},
            )
            profile = next(
                item for item in profiles_response.json() if item["id"] == "goodnurselife"
            )
            profile.pop("version")
            profile["preferredActions"] = ["missing_action"]
            invalid_action_response = await client.put(
                "/api/v1/site-style-profiles/goodnurselife",
                headers={"X-User-Id": settings.dev_admin_id},
                json=profile,
            )
            assert invalid_action_response.status_code == 422
            assert "missing_action" in invalid_action_response.text

            profile["preferredActions"] = []
            profile["retrievedAt"] = "2026-02-31"
            invalid_date_response = await client.put(
                "/api/v1/site-style-profiles/goodnurselife",
                headers={"X-User-Id": settings.dev_admin_id},
                json=profile,
            )
            assert invalid_date_response.status_code == 422


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
        kling_admin_config_file=tmp_path / f"kling-config-{result_count}.json",
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
            for compiled_variant in task["compiledPlan"]["variants"]:
                prompt = compiled_variant["master_prompt"]
                assert "所有未明确允许变化的输入事实保持不变" in prompt
                assert "当前结果相对输入只允许改变动作细节、神态和拍摄表达" in prompt
                assert "本次生成的" not in prompt
                assert "四个版本" not in prompt
            assert task["materialValidation"]["valid"] is True
            assert task["settings"]["smartStoryboard"] is True
            assert task["paidSubmissionConsentAt"] is not None
        async with app.state.database.session_factory() as session:
            command_count = await session.scalar(
                select(func.count()).select_from(GenerationCommand)
            )
            assert command_count == 0


@pytest.mark.asyncio
async def test_custom_video_task_uses_default_spec_and_skips_automatic_prompt_compilation(
    tmp_path,
) -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        object_store_mode="local",
        artifact_root=tmp_path / "artifacts-custom",
        runner_root=tmp_path / "runner-custom",
        kling_admin_config_file=tmp_path / "kling-custom.json",
        kling_cli_enabled=False,
        _env_file=None,
    )
    app = create_app(settings)
    user_prompt = "人物自然转身并停留，完整展示服装背面。"
    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            uploaded = await client.post(
                "/api/v1/uploads",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": "custom-direct-upload",
                },
                files={"file": ("shot.png", png_bytes(), "image/png")},
            )
            assert uploaded.status_code == 201, uploaded.text
            response = await client.post(
                "/api/v1/video-tasks",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": "custom-direct-create",
                },
                json={
                    "clientTaskId": "custom-direct",
                    "title": "Custom direct",
                    "storyboards": [
                        {"uploadId": uploaded.json()["id"], "order": 1, "required": True}
                    ],
                    "generationMode": "custom",
                    "customPrompt": user_prompt,
                    "resultCount": 2,
                    "paidSubmissionConsent": True,
                },
            )

    assert response.status_code == 201, response.text
    task = response.json()
    assert task["templateId"] == "ootd_walk"
    assert task["siteProfileId"] is None
    assert task["settings"]["generationMode"] == "custom"
    assert task["compiledPlan"]["compiler"] == "custom-direct-v1"
    assert task["compiledPlan"]["userPrompt"] == user_prompt
    assert len(task["variants"]) == 2
    assert {variant["promptText"] for variant in task["variants"]} == {
        f"{user_prompt} Reference roles: @image_1 are ordered storyboards and control "
        "scene, action, composition, and camera order."
    }
    assert all(
        variant["promptText"].startswith(user_prompt)
        and "站点风格" not in variant["promptText"]
        and "动作变化" not in variant["promptText"]
        for variant in task["variants"]
    )


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
                    "elementIds": ["element-model-1"],
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
            assert task["settings"]["elementIds"] == ["element-model-1"]
            assert [variant["variantIndex"] for variant in task["variants"]] == [1, 2, 3, 4]
            assert {variant["provider"] for variant in task["variants"]} == {"kling_official_cli"}
        async with app.state.database.session_factory() as session:
            commands = list(await session.scalars(select(GenerationCommand)))
            assert len(commands) == 4
            assert {command.command_manifest_json["provider"] for command in commands} == {"kling"}
            variants = list(await session.scalars(select(GenerationVariant)))
            element_id_sets = {
                tuple(variant.generation_config_json["elementIds"]) for variant in variants
            }
            assert element_id_sets == {("element-model-1",)}


@pytest.mark.asyncio
async def test_fixed_video_task_uses_subject_images_and_creates_reusable_element_in_background(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "libtv_agent.services.subject_elements.SUBJECT_ELEMENT_RETRY_BASE_SECONDS",
        0,
    )
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
                provider="kling_official_api",
                provider_model="kling-3.0-omni",
                provider_status="queued",
                intent_hash=f"subject-intent-{variant.variant_index}",
                status=AttemptStatus.PREPARED,
            )
            session.add(attempt)
            attempts.append(attempt)
        task.phase = ParentTaskPhase.QUEUED
        await session.flush()
        return attempts

    class SubjectElementAdapter:
        def __init__(self) -> None:
            self.created = []
            self.calls = 0

        def get_provider_name(self) -> str:
            return "kling_official_api"

        async def create_element(self, request):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary element provider failure")
            self.created.append(request)
            return {
                "data": {
                    "id": "automatic-subject-1",
                    "name": request.element_name,
                    "description": request.element_description,
                    "status": "submitted",
                }
            }

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
        artifact_root=tmp_path / "artifacts-subject",
        runner_root=tmp_path / "runner-subject",
        _env_file=None,
    )
    app = create_app(settings)
    adapter = SubjectElementAdapter()
    async with app.router.lifespan_context(app):
        app.state.kling_adapter = adapter
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            uploads = []
            for key, filename, color in (
                ("subject-storyboard", "storyboard.png", "#76444a"),
                ("subject-front", "linen-shirt-front.png", "#335577"),
            ):
                response = await client.post(
                    "/api/v1/uploads",
                    headers={
                        "X-User-Id": settings.dev_user_id,
                        "Idempotency-Key": key,
                    },
                    files={"file": (filename, png_bytes(color), "image/png")},
                )
                assert response.status_code == 201, response.text
                uploads.append(response.json()["id"])

            response = await client.post(
                "/api/v1/video-tasks",
                headers={
                    "X-User-Id": settings.dev_user_id,
                    "Idempotency-Key": "fixed-subject-create",
                },
                json={
                    "clientTaskId": "fixed-subject",
                    "title": "Fixed subject",
                    "storyboards": [{"uploadId": uploads[0], "order": 1, "required": True}],
                    "subjectImages": [
                        {"uploadId": uploads[1], "order": 1},
                    ],
                    "templateId": "garment_detail",
                    "siteProfileId": "teachersgram",
                    "resultCount": 1,
                    "paidSubmissionConsent": True,
                },
            )
            assert response.status_code == 201, response.text
            task_id = uuid.UUID(response.json()["id"])
            await asyncio.gather(*tuple(app.state.subject_element_jobs))

        async with app.state.database.session_factory() as session:
            assets = list(
                await session.scalars(
                    select(Asset).where(Asset.parent_task_id == task_id).order_by(Asset.order_no)
                )
            )
            variants = list(
                await session.scalars(
                    select(GenerationVariant).where(GenerationVariant.parent_task_id == task_id)
                )
            )
            subject_job = await session.scalar(
                select(SubjectElementJob).where(SubjectElementJob.parent_task_id == task_id)
            )

    assert [(asset.role, asset.source_type, asset.order_no) for asset in assets] == [
        ("STORYBOARD", "STORYBOARD", 1),
        ("PRODUCT", "SUBJECT_REFERENCE", 101),
    ]
    assert all(asset.used_for_generation for asset in assets)
    assert all(not asset.used_for_analysis for asset in assets)
    assert "@image_1" in variants[0].prompt_text
    assert "@image_2 is the subject frontal reference" in variants[0].prompt_text
    assert len(adapter.created) == 1
    assert adapter.calls == 2
    assert adapter.created[0].element_name.startswith("linen-shirt-")
    assert len(adapter.created[0].refer_images) == 1
    assert adapter.created[0].refer_images[0] == adapter.created[0].frontal_image
    assert adapter.created[0].external_task_id == f"fixed-video-subject-{task_id.hex}"
    assert subject_job is not None
    assert subject_job.status == "SUBMITTED"
    assert subject_job.attempt_count == 2
    assert subject_job.provider_task_id == "automatic-subject-1"
    assert subject_job.last_error_code is None


@pytest.mark.asyncio
async def test_video_task_rejects_storyboard_and_element_references_over_omni_limit(
    tmp_path,
) -> None:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        object_store_mode="local",
        artifact_root=tmp_path / "artifacts-element-limit",
        runner_root=tmp_path / "runner-element-limit",
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
                    "Idempotency-Key": "fixed-element-limit",
                },
                json={
                    "clientTaskId": "fixed-element-limit",
                    "title": "Fixed element limit",
                    "storyboards": [
                        {
                            "uploadId": str(uuid.uuid4()),
                            "order": index,
                            "required": True,
                        }
                        for index in range(1, 5)
                    ],
                    "elementIds": [
                        "element-1",
                        "element-2",
                        "element-3",
                        "element-4",
                    ],
                    "templateId": "ootd_walk",
                    "siteProfileId": "geeksoutfit",
                    "resultCount": 1,
                    "paidSubmissionConsent": True,
                },
            )

    assert response.status_code == 422
    assert "7-reference limit" in response.text
