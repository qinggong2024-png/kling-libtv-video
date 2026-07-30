import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from libtv_agent.adapters.openai_analysis import AnalysisResult, fake_analysis
from libtv_agent.domain.contracts import (
    canonical_json,
    compatible_schema,
    delivery_filename,
    generation_intent_hash,
    map_error_code,
    sha256_json,
)
from libtv_agent.domain.enums import VariantKind
from libtv_agent.domain.schemas import ActionCapabilities, PointsQuotaRead, TaskCreate, TaskRead
from libtv_agent.services.prompts import (
    calculate_timeline,
    compress_prompt,
    count_ab_differences,
    normalize_analysis_motion,
    normalize_motion_language,
    render_prompt,
    select_mode_type,
    select_prompt_max_chars,
    validate_ab_action_difference,
    validate_required_coverage,
)


def test_canonical_json_and_hash_are_order_independent() -> None:
    left = {"b": 2, "a": {"z": 1, "x": "中"}}
    right = {"a": {"x": "中", "z": 1}, "b": 2}
    assert canonical_json(left) == canonical_json(right)
    assert sha256_json(left) == sha256_json(right)


def test_generation_intent_requires_frozen_identity_fields() -> None:
    with pytest.raises(ValueError, match="missing fields"):
        generation_intent_hash({"userId": "u"})


@pytest.mark.parametrize(
    "variants",
    [["STABLE"], ["DYNAMIC"], ["STABLE", "DYNAMIC"]],
)
def test_task_create_accepts_one_or_two_requested_outputs(variants: list[str]) -> None:
    payload = TaskCreate.model_validate(
        {
            "clientTaskId": "client-1",
            "title": "服装广告",
            "storyboards": [
                {
                    "uploadId": "00000000-0000-0000-0000-000000000010",
                    "order": 1,
                }
            ],
            "variants": variants,
        }
    )

    assert [variant.value for variant in payload.variants] == variants


@pytest.mark.parametrize(
    "variants",
    [[], ["STABLE", "STABLE"], ["DYNAMIC", "STABLE"]],
)
def test_task_create_rejects_missing_duplicate_or_reversed_outputs(
    variants: list[str],
) -> None:
    with pytest.raises(ValueError):
        TaskCreate.model_validate(
            {
                "clientTaskId": "client-1",
                "title": "服装广告",
                "storyboards": [
                    {
                        "uploadId": "00000000-0000-0000-0000-000000000010",
                        "order": 1,
                    }
                ],
                "variants": variants,
            }
        )


def test_task_read_serializes_sqlite_naive_timestamps_as_utc() -> None:
    task = TaskRead(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        client_task_id="client-timezone",
        title="时区测试",
        asset_count=1,
        user_requirement="",
        analysis_model="gpt-5.6-sol",
        generation_provider="libtv",
        phase="ACTION_REQUIRED",
        phase_reason_code="PROVIDER_FAILED",
        consistency_level=None,
        analysis_result=None,
        analysis_run_id=None,
        analysis_stage=None,
        analysis_started_at=None,
        analysis_heartbeat_at=None,
        canvas_project_uuid=None,
        state_version=2,
        assets=[],
        variants=[],
        points_quota=PointsQuotaRead(),
        action_capabilities=ActionCapabilities(
            can_edit=False,
            can_confirm=False,
            can_cancel=False,
            can_retry_analysis=False,
            can_regenerate=True,
            can_download=False,
        ),
        created_at=datetime(2026, 7, 28, 6, 0),
        updated_at=datetime(2026, 7, 28, 6, 5, tzinfo=UTC),
    )

    payload = json.loads(task.model_dump_json())
    assert payload["createdAt"] == "2026-07-28T06:00:00Z"
    assert payload["updatedAt"] == "2026-07-28T06:05:00Z"


def test_timeline_covers_exact_duration_and_required_assets() -> None:
    shots = [
        {"referenceAssetIds": ["A1"], "durationWeight": 2},
        {"referenceAssetIds": ["A2"], "durationWeight": 3},
    ]
    timeline = calculate_timeline(shots)
    validate_required_coverage(timeline, ["A1", "A2"])
    assert [(shot.start, shot.end) for shot in timeline] == [(0.0, 4.0), (4.0, 10.0)]
    with pytest.raises(ValueError, match="A3"):
        validate_required_coverage(timeline, ["A1", "A2", "A3"])


def test_stable_and_dynamic_plans_differ_and_prompts_are_bounded() -> None:
    analysis = fake_analysis(["A1", "A2", "A3", "A4"])
    stable = calculate_timeline(analysis.stable_plan.model_dump(by_alias=True)["shots"])
    dynamic = calculate_timeline(analysis.dynamic_plan.model_dump(by_alias=True)["shots"])
    assert count_ab_differences(stable, dynamic) >= 2
    prompt = render_prompt(VariantKind.DYNAMIC, dynamic, ["IMG-1", "IMG-2"], "突出袖口")
    assert '{{Node "IMG-1"}}' in prompt
    assert "按上传顺序理解参考图" in prompt
    assert "真实 iPhone 后置摄像头" in prompt
    assert "进入状态" in prompt
    assert "退出状态" in prompt
    assert "0.0-" not in prompt
    assert " 秒）" not in prompt
    assert len(compress_prompt(prompt * 10, 300)) <= 300


def test_prompt_uses_relative_duration_guidance_without_exact_time_slices() -> None:
    timeline = calculate_timeline(
        [
            {
                "referenceAssetIds": ["A1"],
                "durationWeight": 3,
                "entryState": "站立持书",
                "action": "自然下蹲取书",
                "exitState": "下蹲并稳定持书",
            },
            {
                "referenceAssetIds": ["A2"],
                "durationWeight": 1,
                "entryState": "承接下蹲持书姿势",
                "action": "抬眼看向镜头",
                "exitState": "保持下蹲并看向镜头",
            },
        ]
    )

    prompt = render_prompt(VariantKind.STABLE, timeline, ["IMG-1", "IMG-2"], "")

    assert "充分展开" in prompt
    assert "短暂承接" in prompt
    assert "进入状态站立持书；动作自然下蹲取书；退出状态下蹲并稳定持书" in prompt
    assert re.search(r"\d+\.\d+-\d+\.\d+\s*秒", prompt) is None


def test_kling_prompt_uses_compact_soft_limit() -> None:
    assert select_prompt_max_chars("kling", 2000) == 1600
    assert select_prompt_max_chars("kling", 1200) == 1200
    assert select_prompt_max_chars("libtv", 2000) == 2000
    with pytest.raises(ValueError, match="positive"):
        select_prompt_max_chars("kling", 0)


def test_dynamic_requires_a_different_person_action() -> None:
    same_action = [
        {
            "referenceAssetIds": ["A1"],
            "durationWeight": 1,
            "action": "自然转动肩部",
            "camera": "保持固定",
        }
    ]
    stable = calculate_timeline(same_action)
    dynamic = calculate_timeline(
        [{**same_action[0], "camera": "平稳横移", "shotFunction": "不同镜头功能"}]
    )

    with pytest.raises(ValueError, match="different person actions"):
        validate_ab_action_difference(stable, dynamic)

    qualifier_only_dynamic = calculate_timeline([{**same_action[0], "action": "明显自然转动肩部"}])
    with pytest.raises(ValueError, match="different person actions"):
        validate_ab_action_difference(stable, qualifier_only_dynamic)


def test_rapid_motion_language_is_normalized_before_rendering() -> None:
    payload = {
        "stablePlan": {
            "shots": [
                {
                    "entryState": "快速进入站姿",
                    "action": "快速向前走一步",
                    "exitState": "突然停在镜头前",
                    "camera": "快速跟拍并突然变焦",
                    "shotFunction": "迅速建立产品",
                }
            ]
        },
        "dynamicPlan": {
            "shots": [
                {
                    "action": "Take a quick forward step and rapidly turn",
                    "camera": "Fast tracking with a speed ramp and whip pan",
                    "shotFunction": "Rapid product reveal",
                }
            ]
        },
    }

    normalized = normalize_analysis_motion(payload)
    text = json.dumps(normalized, ensure_ascii=False).casefold()
    for forbidden in (
        "快速",
        "迅速",
        "突然",
        "quick",
        "rapid",
        "fast tracking",
        "speed ramp",
        "whip pan",
    ):
        assert forbidden not in text
    assert normalize_motion_language("快速移动") == "自然移动"


def test_prompt_adapts_short_sleeve_mirror_scene_per_storyboard() -> None:
    timeline = calculate_timeline(
        [
            {
                "referenceAssetIds": ["A1"],
                "durationWeight": 1,
                "action": "在镜中缓慢侧移一步",
                "camera": "保持手机构图稳定",
                "productDisplay": "胸前印花",
                "shotFunction": "短袖动作展示",
            }
        ]
    )

    prompt = render_prompt(
        VariantKind.DYNAMIC,
        timeline,
        ["IMG-1"],
        "",
        2000,
        garment_category="短袖圆领T恤",
        storyboard_facts=[
            {
                "assetId": "A1",
                "scene": "卧室内对镜拍摄",
                "framing": "全身",
                "pose": "站立并手持手机",
                "actionCandidates": ["镜内侧移"],
                "interactionObjects": ["手机"],
            }
        ],
    )

    assert "短袖可使用自然重心切换" in prompt
    assert "保持在镜面范围内" in prompt
    assert "不使用第三人称跟拍" in prompt
    assert "动态版与稳定版保持接近的自然速度" in prompt


def test_prompt_restricts_dress_motion_and_expands_open_jersey_space() -> None:
    timeline = calculate_timeline(
        [
            {
                "referenceAssetIds": ["A1"],
                "durationWeight": 1,
                "action": "自然改变站姿",
                "camera": "平稳切换景别",
            }
        ]
    )
    dress_prompt = render_prompt(
        VariantKind.DYNAMIC,
        timeline,
        ["IMG-1"],
        "",
        2000,
        garment_category="连衣裙",
        storyboard_facts=[{"assetId": "A1", "scene": "室内房间", "pose": "站立"}],
    )
    jersey_prompt = render_prompt(
        VariantKind.DYNAMIC,
        timeline,
        ["IMG-1"],
        "",
        2000,
        garment_category="足球球衣",
        storyboard_facts=[{"assetId": "A1", "scene": "室外空旷球场", "pose": "站立"}],
    )

    assert "不得旋转甩裙" in dress_prompt
    assert "最多缓慢移动半步" in dress_prompt
    assert "不得连续走动" in dress_prompt
    assert "印花、文字和缝线视为锁定在布料表面的固定纹理" in dress_prompt
    assert "不得爬行、漂移、闪烁、抖动或局部伸缩" in dress_prompt
    assert "裙装保持原地或最多缓慢移动半步" in dress_prompt
    assert "球衣可使用比裙装更清晰的站姿切换" in jersey_prompt
    assert "室外或空旷场景允许更大的自然移动范围" in jersey_prompt


def test_bounded_prompt_preserves_every_shot_and_final_motion_guardrail() -> None:
    timeline = calculate_timeline(
        [
            {
                "referenceAssetIds": [f"A{index}"],
                "durationWeight": 1,
                "action": "在参考场景允许范围内完成一段自然且清楚的人物姿态变化" * 3,
                "camera": "使用平稳匀速的中景构图并保持商品区域清晰" * 3,
                "productDisplay": "服装正面版型、印花、文字和可见面料结构" * 3,
                "shotFunction": "建立不同的人物动作和商品展示层次" * 3,
            }
            for index in range(1, 5)
        ]
    )

    prompt = render_prompt(
        VariantKind.DYNAMIC,
        timeline,
        [f"IMG-{index}" for index in range(1, 5)],
        "",
        1600,
        garment_category="短袖T恤",
        storyboard_facts=[
            {"assetId": f"A{index}", "scene": "室外空旷场景", "pose": "站立"}
            for index in range(1, 5)
        ],
    )

    assert len(prompt) <= 1600
    for index in range(1, 5):
        assert f"第 {index} 段" in prompt
    assert "硬约束：开启智能分镜" in prompt
    assert "全片人物与镜头保持自然匀速" in prompt


def test_mode_type_and_schema_compatibility() -> None:
    schema = {
        "maxMediaCount": 7,
        "modeTypes": ["singleImage2video", "mixed2video"],
        "fields": {"duration": {"enum": [10], "originalField": "duration"}},
    }
    assert select_mode_type(1, schema) == "singleImage2video"
    assert select_mode_type(7, schema) == "mixed2video"
    with pytest.raises(ValueError, match="incompatible"):
        select_mode_type(8, schema)
    assert compatible_schema(
        schema,
        {**schema, "fields": {**schema["fields"], "newField": {}}},
        {"media": ["A1"], "params": {"duration": 10}},
    )
    assert not compatible_schema(
        schema,
        {**schema, "maxMediaCount": 0},
        {"media": ["A1"], "params": {"duration": 10}},
    )


def test_filename_and_error_mapping_contract() -> None:
    assert delivery_filename("2026-07-27", "user123456", "task123456", "STABLE", 2) == (
        "2026-07-27_user1234_task1234_stable_v2.mp4"
    )
    assert map_error_code("generation", submitted=True) == "GENERATION_UNKNOWN"
    assert map_error_code("download") == "DOWNLOAD_RETRYABLE"


def test_committed_ai_json_schema_matches_offline_model() -> None:
    contract = json.loads(
        (Path(__file__).parents[1] / "contracts" / "ai-analysis.schema.json").read_text(
            encoding="utf-8"
        )
    )
    payload = fake_analysis(["A1", "A2"]).model_dump(mode="json", by_alias=True)
    assert contract["properties"]["schemaVersion"]["const"] == payload["schemaVersion"]
    assert AnalysisResult.model_validate(payload).model_version == "fake-2.2"
