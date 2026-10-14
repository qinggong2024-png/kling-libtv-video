import uuid
from pathlib import Path

import pytest
from libtv_agent.adapters.openai_analysis import AnalysisTimeoutError, OpenAIAnalysisAdapter
from libtv_agent.api import tasks as tasks_api
from libtv_agent.domain.enums import AIUsageReservationStatus, ParentTaskPhase
from libtv_agent.domain.models import AIUsageReservation
from libtv_agent.services.prompt_revision import PromptRevisionTimeoutError
from sqlalchemy import select
from test_workflow_integration import (
    create_analyzed_task,
    create_draft_task,
    running_app,
    user_headers,
    wait_for_task_phase,
)


async def _reservations(app, user_id: str) -> list[AIUsageReservation]:
    async with app.state.database.session_factory() as session:
        return list(
            await session.scalars(
                select(AIUsageReservation).where(
                    AIUsageReservation.user_id == uuid.UUID(user_id)
                )
            )
        )


@pytest.mark.asyncio
async def test_analysis_quota_rejection_does_not_start_provider(tmp_path: Path) -> None:
    async with running_app(tmp_path, scenario="analysis-quota") as (client, app):
        task = await create_draft_task(client, "analysis-quota")
        app.state.settings.ai_risk_daily_user_limit = 1
        called = False

        async def forbidden(*args: object, **kwargs: object) -> object:
            nonlocal called
            called = True
            raise AssertionError("analysis provider must not run when the quota is full")

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(OpenAIAnalysisAdapter, "analyze", forbidden)
        try:
            response = await client.post(
                f"/api/v1/tasks/{task['id']}/analyze",
                headers=user_headers("analysis-quota-key"),
                json={"expectedStateVersion": task["stateVersion"]},
            )
        finally:
            monkeypatch.undo()
        assert response.status_code == 429, response.text
        assert called is False
        assert await _reservations(app, task["userId"]) == []


@pytest.mark.asyncio
async def test_analysis_idempotency_and_offline_settlement_are_single_shot(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path, scenario="analysis-replay") as (client, app):
        task = await create_draft_task(client, "analysis-replay")
        headers = user_headers("analysis-replay-key")
        first = await client.post(
            f"/api/v1/tasks/{task['id']}/analyze",
            headers=headers,
            json={"expectedStateVersion": task["stateVersion"]},
        )
        second = await client.post(
            f"/api/v1/tasks/{task['id']}/analyze",
            headers=headers,
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert first.status_code == 202, first.text
        assert second.status_code == 202, second.text
        await wait_for_task_phase(client, task["id"], "AWAITING_CONFIRMATION")
        rows = await _reservations(app, task["userId"])
        assert len(rows) == 1
        assert rows[0].operation_type == "AI_ANALYSIS"
        assert rows[0].status == AIUsageReservationStatus.SETTLED
        assert rows[0].actual_cost_status == "OFFLINE"


@pytest.mark.asyncio
async def test_analysis_timeout_keeps_unknown_risk_units(tmp_path: Path) -> None:
    async with running_app(tmp_path, scenario="analysis-unknown") as (client, app):
        task = await create_draft_task(client, "analysis-unknown")
        app.state.settings.ai_adapter_mode = "openai"
        app.state.settings.openai_api_key = "test-only-key"

        async def timeout(*args: object, **kwargs: object) -> object:
            raise AnalysisTimeoutError("test timeout")

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(OpenAIAnalysisAdapter, "analyze", timeout)
        try:
            response = await client.post(
                f"/api/v1/tasks/{task['id']}/analyze",
                headers=user_headers("analysis-unknown-key"),
                json={"expectedStateVersion": task["stateVersion"]},
            )
            assert response.status_code == 202, response.text
            current = await wait_for_task_phase(client, task["id"], "ACTION_REQUIRED")
        finally:
            monkeypatch.undo()
        assert current["phase"] == ParentTaskPhase.ACTION_REQUIRED.value
        rows = await _reservations(app, task["userId"])
        assert len(rows) == 1
        assert rows[0].status == AIUsageReservationStatus.UNKNOWN
        assert rows[0].actual_cost_status == "UNKNOWN_COST"


@pytest.mark.asyncio
async def test_prompt_assistant_quota_rejection_does_not_call_provider(tmp_path: Path) -> None:
    async with running_app(tmp_path, scenario="prompt-quota") as (client, app):
        task = await create_analyzed_task(client, client_task_id="prompt-quota")
        app.state.settings.ai_risk_daily_user_limit = 1
        called = False

        async def forbidden(*args: object, **kwargs: object) -> object:
            nonlocal called
            called = True
            raise AssertionError("prompt provider must not run when the quota is full")

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(tasks_api, "run_prompt_assistant", forbidden)
        try:
            response = await client.post(
                f"/api/v1/tasks/{task['id']}/prompt-assistant",
                headers=user_headers("prompt-quota-key"),
                json={
                    "expectedStateVersion": task["stateVersion"],
                    "action": "ADVISE",
                    "instruction": "保持服装细节",
                    "stablePrompt": task["variants"][0]["promptText"],
                    "dynamicPrompt": task["variants"][1]["promptText"],
                },
            )
        finally:
            monkeypatch.undo()
        assert response.status_code == 429, response.text
        assert called is False
        assert not any(
            row.operation_type == "AI_PROMPT_ADVISE"
            for row in await _reservations(app, task["userId"])
        )


@pytest.mark.asyncio
async def test_prompt_assistant_idempotency_and_offline_settlement(tmp_path: Path) -> None:
    async with running_app(tmp_path, scenario="prompt-replay") as (client, app):
        task = await create_analyzed_task(client, client_task_id="prompt-replay")
        payload = {
            "expectedStateVersion": task["stateVersion"],
            "action": "ADVISE",
            "instruction": "保持服装细节",
            "stablePrompt": task["variants"][0]["promptText"],
            "dynamicPrompt": task["variants"][1]["promptText"],
        }
        headers = user_headers("prompt-replay-key")
        first = await client.post(
            f"/api/v1/tasks/{task['id']}/prompt-assistant",
            headers=headers,
            json=payload,
        )
        second = await client.post(
            f"/api/v1/tasks/{task['id']}/prompt-assistant",
            headers=headers,
            json=payload,
        )
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        rows = [
            row
            for row in await _reservations(app, task["userId"])
            if row.operation_type == "AI_PROMPT_ADVISE"
        ]
        assert len(rows) == 1
        assert rows[0].status == AIUsageReservationStatus.SETTLED
        assert rows[0].actual_cost_status == "OFFLINE"


@pytest.mark.asyncio
async def test_prompt_assistant_timeout_is_unknown_and_same_key_cannot_retry(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path, scenario="prompt-unknown") as (client, app):
        task = await create_analyzed_task(client, client_task_id="prompt-unknown")
        app.state.settings.ai_adapter_mode = "openai"
        app.state.settings.openai_api_key = "test-only-key"
        payload = {
            "expectedStateVersion": task["stateVersion"],
            "action": "REGENERATE",
            "instruction": "保持服装细节",
            "stablePrompt": task["variants"][0]["promptText"],
            "dynamicPrompt": task["variants"][1]["promptText"],
        }

        async def timeout(*args: object, **kwargs: object) -> object:
            raise PromptRevisionTimeoutError("test timeout")

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(tasks_api, "run_prompt_assistant", timeout)
        try:
            response = await client.post(
                f"/api/v1/tasks/{task['id']}/prompt-assistant",
                headers=user_headers("prompt-unknown-key"),
                json=payload,
            )
            replay = await client.post(
                f"/api/v1/tasks/{task['id']}/prompt-assistant",
                headers=user_headers("prompt-unknown-key"),
                json=payload,
            )
        finally:
            monkeypatch.undo()
        assert response.status_code == 504, response.text
        assert replay.status_code == 409, replay.text
        rows = [
            row
            for row in await _reservations(app, task["userId"])
            if row.operation_type == "AI_PROMPT_REGENERATE"
        ]
        assert len(rows) == 1
        assert rows[0].status == AIUsageReservationStatus.UNKNOWN
        assert rows[0].actual_cost_status == "UNKNOWN_COST"
