import asyncio
import uuid
from types import SimpleNamespace

import pytest
from libtv_agent.domain.enums import AIUsageReservationStatus
from libtv_agent.domain.models import (
    AIUsageReservation,
    FeedbackLearningJob,
    User,
    UserVideoLearningProfile,
)
from libtv_agent.services import feedback_learning as learning
from libtv_agent.services.ai_usage import read_ai_quota
from sqlalchemy import delete, func, select
from test_ai_pricing import _priced_settings
from test_ai_usage import _database


async def _app(tmp_path, monkeypatch, **settings_options):
    user_id = uuid.uuid4()
    engine, factory = await _database(tmp_path / "feedback.db", user_ids=[user_id])
    scope = "fixed:ootd_walk:geeksoutfit"
    async with factory() as session:
        session.add_all([
            UserVideoLearningProfile(
                user_id=user_id, scope_key=scope, template_id="ootd_walk",
                site_profile_id="geeksoutfit", deterministic_guidance="Preserve product facts",
            ),
            FeedbackLearningJob(user_id=user_id, scope_key=scope),
        ])
        await session.commit()

    async def history(*_args, **_kwargs):
        return []

    monkeypatch.setattr(learning, "_scope_feedback", history)
    settings = _priced_settings(
        openai_model="small", openai_api_key="synthetic-unused-key", **settings_options,
    )
    app = SimpleNamespace(state=SimpleNamespace(
        settings=settings, database=SimpleNamespace(session_factory=factory),
    ))
    return app, engine, factory, user_id, scope


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["quota", "price"])
async def test_feedback_budget_denial_never_calls_provider(tmp_path, monkeypatch, reason):
    options = {"ai_risk_daily_user_limit": 1} if reason == "quota" else {}
    app, engine, factory, user_id, scope = await _app(tmp_path, monkeypatch, **options)
    if reason == "price":
        app.state.settings.ai_price_catalog_json = '{"version":"empty","prices":[]}'
    calls = 0

    async def provider(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("denied feedback request reached provider")

    monkeypatch.setattr(learning, "synthesize_feedback_preferences", provider)
    await learning._run_feedback_learning_job(app, user_id, scope)
    async with factory() as session:
        job = await session.scalar(select(FeedbackLearningJob))
        profile = await session.scalar(select(UserVideoLearningProfile))
        assert job.status == "BLOCKED"
        assert profile.deterministic_guidance == "Preserve product facts"
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 0
    assert calls == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_feedback_reserves_before_call_settles_and_never_resubmits(tmp_path, monkeypatch):
    app, engine, factory, user_id, scope = await _app(tmp_path, monkeypatch)
    calls = 0

    async def provider(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        async with factory() as session:
            row = await session.scalar(select(AIUsageReservation))
            assert row.status == AIUsageReservationStatus.RESERVED
        result = learning.FeedbackPreferenceSynthesis(
            summary="Natural motion", prompt_guidance="Keep the product visible",
        )
        result._actual_input_tokens = 100
        result._actual_output_tokens = 50
        result._provider_response_id = "synthetic-feedback-response"
        return result

    monkeypatch.setattr(learning, "synthesize_feedback_preferences", provider)
    await learning._run_feedback_learning_job(app, user_id, scope)
    async with factory() as session:
        row = await session.scalar(select(AIUsageReservation))
        job = await session.scalar(select(FeedbackLearningJob))
        assert row.status == AIUsageReservationStatus.SETTLED
        assert row.actual_cost_microusd == 300
        assert job.status == "SUCCEEDED"
        quota = await read_ai_quota(session, app.state.settings, user_id=user_id)
        assert quota["reserved"] == "0.000"
        assert quota["settled"] == "0.001"
        # Simulate recovery after a job marker was lost, with the paid ledger retained.
        job.status = "RUNNING"
        await session.commit()
    await learning._run_feedback_learning_job(app, user_id, scope)
    assert calls == 1
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 1
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("not_submitted", [False, True])
async def test_feedback_unknown_is_retained_without_automatic_retry(
    tmp_path, monkeypatch, not_submitted,
):
    app, engine, factory, user_id, scope = await _app(tmp_path, monkeypatch)
    calls = 0

    async def provider(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if not_submitted:
            raise learning.FeedbackLearningNotSubmittedError("local credential preflight failed")
        raise TimeoutError("provider acceptance unknown")

    monkeypatch.setattr(learning, "synthesize_feedback_preferences", provider)
    await learning._run_feedback_learning_job(app, user_id, scope)
    await learning._run_feedback_learning_job(app, user_id, scope)
    async with factory() as session:
        row = await session.scalar(select(AIUsageReservation))
        quota = await read_ai_quota(session, app.state.settings, user_id=user_id)
        assert row.status == (
            AIUsageReservationStatus.RELEASED if not_submitted else AIUsageReservationStatus.UNKNOWN
        )
        assert quota["reserved"] == "0.000"
        assert (quota["unknown"] == "0.000") is not_submitted
        assert quota["settled"] == "0.000"
    assert calls == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_feedback_success_without_usage_keeps_unknown_budget(tmp_path, monkeypatch):
    app, engine, factory, user_id, scope = await _app(tmp_path, monkeypatch)

    async def provider(*_args, **_kwargs):
        return learning.FeedbackPreferenceSynthesis(summary="Natural", prompt_guidance="Visible")

    monkeypatch.setattr(learning, "synthesize_feedback_preferences", provider)
    await learning._run_feedback_learning_job(app, user_id, scope)
    async with factory() as session:
        row = await session.scalar(select(AIUsageReservation))
        assert row.status == AIUsageReservationStatus.UNKNOWN
        assert (await session.scalar(select(FeedbackLearningJob))).status == "SUCCEEDED"
    await engine.dispose()


@pytest.mark.asyncio
async def test_feedback_disabled_account_never_reserves_or_calls(tmp_path, monkeypatch):
    app, engine, factory, user_id, scope = await _app(tmp_path, monkeypatch)
    async with factory() as session:
        user = await session.get(User, user_id)
        user.video_learning_enabled = False
        await session.commit()

    async def provider(*_args, **_kwargs):
        raise AssertionError("disabled learning reached provider")

    monkeypatch.setattr(learning, "synthesize_feedback_preferences", provider)
    await learning._run_feedback_learning_job(app, user_id, scope)
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_feedback_workers_dispatch_once(tmp_path, monkeypatch):
    app, engine, factory, user_id, scope = await _app(tmp_path, monkeypatch)
    calls = 0

    async def provider(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return learning.FeedbackPreferenceSynthesis(summary="Natural", prompt_guidance="Visible")

    monkeypatch.setattr(learning, "synthesize_feedback_preferences", provider)
    await asyncio.gather(
        learning._run_feedback_learning_job(app, user_id, scope),
        learning._run_feedback_learning_job(app, user_id, scope),
    )
    assert calls == 1
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_old_feedback_result_does_not_write_rebuilt_profile(tmp_path, monkeypatch):
    app, engine, factory, user_id, scope = await _app(tmp_path, monkeypatch)

    async def provider(*_args, **_kwargs):
        async with factory() as session:
            await session.execute(delete(FeedbackLearningJob))
            await session.execute(delete(UserVideoLearningProfile))
            session.add_all([
                FeedbackLearningJob(user_id=user_id, scope_key=scope),
                UserVideoLearningProfile(
                    user_id=user_id, scope_key=scope, template_id="ootd_walk",
                    site_profile_id="geeksoutfit", summary="New profile",
                ),
            ])
            await session.commit()
        result = learning.FeedbackPreferenceSynthesis(
            summary="Obsolete result", prompt_guidance="Obsolete instructions",
        )
        result._actual_input_tokens, result._actual_output_tokens = 100, 50
        return result

    monkeypatch.setattr(learning, "synthesize_feedback_preferences", provider)
    await learning._run_feedback_learning_job(app, user_id, scope)
    async with factory() as session:
        profile = await session.scalar(select(UserVideoLearningProfile))
        assert profile.summary == "New profile"
        assert profile.llm_prompt_guidance == ""
        assert (await session.scalar(select(FeedbackLearningJob))).status == "PENDING"
        assert (await session.scalar(select(AIUsageReservation))).status == (
            AIUsageReservationStatus.SETTLED
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_old_feedback_timeout_cannot_overwrite_new_pending_version(tmp_path, monkeypatch):
    app, engine, factory, user_id, scope = await _app(tmp_path, monkeypatch)

    async def provider(*_args, **_kwargs):
        async with factory() as session:
            profile = await session.scalar(select(UserVideoLearningProfile))
            profile.version = 2
            job = await session.scalar(select(FeedbackLearningJob))
            job.profile_version, job.status = 2, "PENDING"
            await session.commit()
        raise TimeoutError("old request timed out")

    monkeypatch.setattr(learning, "synthesize_feedback_preferences", provider)
    await learning._run_feedback_learning_job(app, user_id, scope)
    async with factory() as session:
        job = await session.scalar(select(FeedbackLearningJob))
        assert job.profile_version == 2
        assert job.status == "PENDING"
        assert (await session.scalar(select(AIUsageReservation))).status == (
            AIUsageReservationStatus.UNKNOWN
        )
    await engine.dispose()
