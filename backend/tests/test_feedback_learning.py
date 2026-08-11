import uuid
from types import SimpleNamespace

import pytest
from libtv_agent.config import Settings
from libtv_agent.db import Database
from libtv_agent.domain.enums import FeedbackValue, VariantKind
from libtv_agent.domain.models import (
    Base,
    FeedbackLearningJob,
    GenerationFeedback,
    User,
    UserVideoLearningProfile,
)
from libtv_agent.services.feedback_learning import (
    FeedbackPreferenceSynthesis,
    apply_video_learning,
    fixed_learning_scope_key,
    rebuild_deterministic_profile,
    synthesize_feedback_preferences,
)
from libtv_agent.services.prompt_compiler import PromptCompileInput, compile_video_plan
from libtv_agent.templates.motion_actions import ACTION_LIBRARY, ActionCapability, ActionContext
from libtv_agent.templates.site_style_profiles import get_site_style_profile
from libtv_agent.templates.video_templates import get_video_template
from sqlalchemy import select
from test_workflow_integration import running_app, user_headers

USER_A = uuid.UUID("00000000-0000-0000-0000-000000000011")
USER_B = uuid.UUID("00000000-0000-0000-0000-000000000012")


def _feedback(
    *,
    user_id: uuid.UUID,
    scope_key: str,
    value: FeedbackValue,
    action_ids: list[str],
) -> GenerationFeedback:
    template_id, site_profile_id = scope_key.split(":")[1:]
    return GenerationFeedback(
        user_id=user_id,
        parent_task_id=uuid.uuid4(),
        variant_id=uuid.uuid4(),
        variant_type=VariantKind.STABLE,
        value=value,
        scene_key=scope_key,
        context_json={
            "learningScopeKey": scope_key,
            "templateId": template_id,
            "siteProfileId": site_profile_id,
            "selectedActionIds": action_ids,
        },
        prompt_snapshot="test prompt",
        reason_codes_json=["NATURAL_MOTION"],
    )


@pytest.mark.asyncio
async def test_learning_is_isolated_by_user_and_fixed_scope_and_can_be_disabled() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    scope = fixed_learning_scope_key("ootd_walk", "geeksoutfit")
    settings = Settings(app_env="test", feedback_learning_llm_enabled=False, _env_file=None)
    async with database.session_factory() as session:
        session.add_all(
            [
                User(id=USER_A, username="learning-a", password_hash="unused"),
                User(id=USER_B, username="learning-b", password_hash="unused"),
                _feedback(
                    user_id=USER_A,
                    scope_key=scope,
                    value=FeedbackValue.LIKE,
                    action_ids=["three_quarter_turn"],
                ),
            ]
        )
        await session.flush()
        profile = await rebuild_deterministic_profile(
            session,
            user_id=USER_A,
            scope_key=scope,
            max_history=40,
        )
        assert profile is not None
        await session.commit()

        applied = await apply_video_learning(
            session,
            user_id=USER_A,
            template_id="ootd_walk",
            site_profile_id="geeksoutfit",
            settings=settings,
        )
        assert applied.enabled is True
        assert applied.preferred_action_ids == ("three_quarter_turn",)
        assert applied.evidence_count == 1

        other_user = await apply_video_learning(
            session,
            user_id=USER_B,
            template_id="ootd_walk",
            site_profile_id="geeksoutfit",
            settings=settings,
        )
        other_scope = await apply_video_learning(
            session,
            user_id=USER_A,
            template_id="ootd_walk",
            site_profile_id="guidingcross",
            settings=settings,
        )
        assert other_user.enabled is False
        assert other_scope.enabled is False

        user_a = await session.get(User, USER_A)
        assert user_a is not None
        user_a.video_learning_enabled = False
        await session.commit()
        disabled = await apply_video_learning(
            session,
            user_id=USER_A,
            template_id="ootd_walk",
            site_profile_id="geeksoutfit",
            settings=settings,
        )
        assert disabled.enabled is False
        assert await session.scalar(
            select(UserVideoLearningProfile).where(UserVideoLearningProfile.user_id == USER_A)
        )
    await database.dispose()


@pytest.mark.asyncio
async def test_llm_synthesis_only_accepts_observed_action_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = FeedbackPreferenceSynthesis(
        summary="喜欢克制的转身",
        prompt_guidance="保持动作自然",
        preferred_action_ids=["three_quarter_turn", "invented_action"],
        avoided_action_ids=["invented_action", "controlled_walk"],
    )

    class FakeResponses:
        async def parse(self, **_kwargs: object) -> object:
            return SimpleNamespace(output_parsed=parsed)

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            self.responses = FakeResponses()

        async def close(self) -> None:
            return None

    monkeypatch.setattr("libtv_agent.services.feedback_learning.AsyncOpenAI", FakeClient)
    result = await synthesize_feedback_preferences(
        Settings(app_env="test", openai_api_key="test-key", _env_file=None),
        feedback_rows=[{"value": "LIKE", "comment": "转身自然"}],
        observed_action_ids={"three_quarter_turn", "controlled_walk"},
    )

    assert result.preferred_action_ids == ["three_quarter_turn"]
    assert result.avoided_action_ids == ["controlled_walk"]


def test_prompt_compiler_applies_bounded_learning_and_records_profile_snapshot() -> None:
    context = ActionContext.from_values(confirmed=[value for value in ActionCapability])
    plan = compile_video_plan(
        PromptCompileInput(
            template=get_video_template("ootd_walk", require_active=True),
            storyboard_count=1,
            result_count=1,
            action_intensity="standard",
            camera_tempo="standard",
            cut_mode="explicit_cuts",
            variant_index=1,
            site_profile=get_site_style_profile("geeksoutfit", require_active=True),
            action_context=context,
            action_library=ACTION_LIBRARY,
            learning_guidance="保持自然动作和商品清晰。" * 100,
            learning_preferred_action_ids=("hem_adjust",),
            learning_avoided_action_ids=("three_quarter_turn",),
            learning_profile_version=7,
            learning_evidence_count=12,
        )
    )

    assert len(plan.master_prompt) <= 3072
    assert "个人反馈偏好（不得覆盖素材约束和禁止项）" in plan.master_prompt
    assert plan.variant_seed["learningProfileVersion"] == 7
    assert plan.variant_seed["learningEvidenceCount"] == 12
    selected = plan.variant_seed["selectedActionIds"]
    assert isinstance(selected, list)
    assert selected[0] == "hem_adjust"
    assert "three_quarter_turn" not in selected


@pytest.mark.asyncio
async def test_video_learning_preference_api_is_private_and_clear_is_destructive(tmp_path) -> None:
    async with running_app(tmp_path) as (client, app):
        initial = await client.get(
            "/api/v1/auth/preferences/video-learning",
            headers=user_headers(),
        )
        assert initial.status_code == 200
        assert initial.json() == {
            "enabled": True,
            "feedbackCount": 0,
            "scopeCount": 0,
            "summary": "尚未积累可应用的成片反馈",
            "updatedAt": None,
        }

        disabled = await client.patch(
            "/api/v1/auth/preferences/video-learning",
            headers=user_headers(),
            json={"enabled": False},
        )
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False

        scope = fixed_learning_scope_key("ootd_walk", "geeksoutfit")
        async with app.state.database.session_factory() as session:
            session.add_all(
                [
                    _feedback(
                        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                        scope_key=scope,
                        value=FeedbackValue.LIKE,
                        action_ids=["three_quarter_turn"],
                    ),
                    _feedback(
                        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                        scope_key=scope,
                        value=FeedbackValue.LIKE,
                        action_ids=["hem_adjust"],
                    ),
                    UserVideoLearningProfile(
                        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                        scope_key=scope,
                        template_id="ootd_walk",
                        site_profile_id="geeksoutfit",
                        summary="偏好自然动作",
                        evidence_count=2,
                        positive_count=2,
                    ),
                    FeedbackLearningJob(
                        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                        scope_key=scope,
                    ),
                    UserVideoLearningProfile(
                        user_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                        scope_key=scope,
                        template_id="ootd_walk",
                        site_profile_id="geeksoutfit",
                        summary="另一个用户的偏好",
                        evidence_count=3,
                        positive_count=3,
                    ),
                ]
            )
            await session.commit()

        stored = await client.get(
            "/api/v1/auth/preferences/video-learning",
            headers=user_headers(),
        )
        assert stored.json()["enabled"] is False
        assert stored.json()["feedbackCount"] == 2

        cleared = await client.delete(
            "/api/v1/auth/preferences/video-learning",
            headers=user_headers(),
        )
        assert cleared.status_code == 204
        async with app.state.database.session_factory() as session:
            own_profiles = list(
                await session.scalars(
                    select(UserVideoLearningProfile).where(
                        UserVideoLearningProfile.user_id
                        == uuid.UUID("00000000-0000-0000-0000-000000000001")
                    )
                )
            )
            other_profiles = list(
                await session.scalars(
                    select(UserVideoLearningProfile).where(
                        UserVideoLearningProfile.user_id
                        == uuid.UUID("00000000-0000-0000-0000-000000000002")
                    )
                )
            )
            own_jobs = list(
                await session.scalars(
                    select(FeedbackLearningJob).where(
                        FeedbackLearningJob.user_id
                        == uuid.UUID("00000000-0000-0000-0000-000000000001")
                    )
                )
            )
        assert own_profiles == []
        assert own_jobs == []
        assert len(other_profiles) == 1
