import asyncio
import json
import uuid

import pytest
from libtv_agent.adapters.openai_analysis import OpenAIAnalysisAdapter, fake_analysis
from libtv_agent.domain.enums import AIUsageReservationStatus
from libtv_agent.domain.models import AIUsageReservation
from libtv_agent.services import analysis
from libtv_agent.services.analysis_lifecycle import StaleAnalysisRunError
from sqlalchemy import select
from test_workflow_integration import (
    create_draft_task,
    running_app,
    user_headers,
    wait_for_task_phase,
)


@pytest.mark.asyncio
async def test_combined_primary_and_fallback_cap_rejects_before_provider(tmp_path, monkeypatch):
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("over-budget request must not dispatch")

    monkeypatch.setattr(OpenAIAnalysisAdapter, "analyze", forbidden)
    async with running_app(tmp_path, ai_mode="openai") as (client, app):
        task = await create_draft_task(client, "combined-cap")
        catalog = json.loads(app.state.settings.ai_price_catalog_json)
        for price in catalog["prices"]:
            price["rate_microusd"] = 0 if price["unit"] == "input_token" else (
                750 if price["model"] == "gpt-5.6-luna" else 500
            )
        app.state.settings.ai_price_catalog_json = json.dumps(catalog)
        response = await client.post(
            f"/api/v1/tasks/{task['id']}/analyze", headers=user_headers("combined-cap"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert response.status_code == 422, response.text
        assert "including fallback" in response.text
        assert not calls
        async with app.state.database.session_factory() as session:
            assert (await session.scalars(select(AIUsageReservation))).all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("needs_fallback", [False, True])
async def test_both_reserved_before_primary_and_unused_fallback_released(
    tmp_path, monkeypatch, needs_fallback,
):
    calls = []

    async def synthetic(adapter, prompt, images):
        async with app.state.database.session_factory() as session:
            rows = list(await session.scalars(select(AIUsageReservation)))
        assert len(rows) == 2
        fallback = next(row for row in rows if row.operation_type == "AI_ANALYSIS_FALLBACK")
        assert fallback.status == AIUsageReservationStatus.RESERVED
        calls.append(adapter.settings.openai_model)
        result = fake_analysis([str(image.asset_id) for image in images])
        adapter.actual_input_tokens = 100
        adapter.actual_output_tokens = 100
        if needs_fallback and len(calls) == 1:
            result.dynamic_plan = result.stable_plan.model_copy(deep=True)
        return result

    monkeypatch.setattr(OpenAIAnalysisAdapter, "analyze", synthetic)
    async with running_app(tmp_path, ai_mode="openai") as (client, app):
        task = await create_draft_task(client, "pre-reserve-fallback")
        response = await client.post(
            f"/api/v1/tasks/{task['id']}/analyze", headers=user_headers("pre-reserve-fallback"),
            json={"expectedStateVersion": task["stateVersion"]},
        )
        assert response.status_code == 202, response.text
        await wait_for_task_phase(client, task["id"], "AWAITING_CONFIRMATION")
        await asyncio.gather(*list(app.state.analysis_jobs))
        async with app.state.database.session_factory() as session:
            rows = list(await session.scalars(select(AIUsageReservation)))
        fallback = next(row for row in rows if row.operation_type == "AI_ANALYSIS_FALLBACK")
        assert fallback.status == (
            AIUsageReservationStatus.SETTLED if needs_fallback
            else AIUsageReservationStatus.RELEASED
        )
        assert len(calls) == (2 if needs_fallback else 1)

        # A recovered worker cannot dispatch a terminal or already claimed reservation.
        async with app.state.database.session_factory() as session:
            with pytest.raises(StaleAnalysisRunError, match="already dispatched"):
                await analysis._run_openai_analysis_request(
                    session, None, app.state.settings, uuid.uuid4(),
                    fallback.model, "low", 6000, "", [], [], fallback.id,
                )
        assert len(calls) == (2 if needs_fallback else 1)
