import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.adapters.wavespeed import WaveSpeedError
from libtv_agent.api.image_generations import _public_error
from libtv_agent.domain.models import ImageGenerationItem
from sqlalchemy import select
from test_image_quota_concurrency import post, world  # noqa: F401


@pytest.mark.parametrize("code", ["WAVESPEED_REQUEST_FAILED", "token=private-code"])
def test_public_error_never_exposes_provider_text_or_arbitrary_details(code):
    result = _public_error(
        {
            "code": code,
            "message": "token=private-key https://cdn.test/a?sig=private-signature",
            "retryable": False,
            "details": {
                "submitted": True,
                "prompt": "private-prompt",
                "reference": "data:image/png;base64,private-image",
            },
        }
    )
    assert "private" not in json.dumps(result)
    assert result["retryable"] is False
    assert result["details"] == {"submitted": True}
    assert result["code"] == (code if code.startswith("WAVESPEED") else "IMAGE_GENERATION_FAILED")


def test_no_error_stays_absent():
    assert _public_error(None) is None


async def test_persisted_provider_error_is_private_on_create_replay_and_read(world):  # noqa: F811
    app, factory, provider, users = world
    app.state.image_generation_refresh_lock = asyncio.Lock()
    calls = 0

    async def reject(*args):
        nonlocal calls
        calls += 1
        raise WaveSpeedError(
            "WAVESPEED_REQUEST_FAILED",
            "token=private-key https://cdn.test/output?sig=private-signature",
            submitted=True,
            uncertain=True,
            details={
                "prompt": "private-prompt",
                "reference": "data:image/png;base64,private-image",
            },
        )

    provider.submit_prediction = reject
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await post(client, users[0], "privacy-key")
        assert created.status_code == 201, created.text
        replay = await post(client, users[0], "privacy-key")
        fetched = await client.get(
            f"/api/v1/image-generation-batches/{created.json()['id']}",
            headers={"X-User-Id": str(users[0])},
        )
        for response in (created, replay, fetched):
            assert response.status_code in {200, 201}
            assert "private-" not in response.text
            assert response.json()["status"] == "write_uncertain"
            assert response.json()["items"][0]["error"]["details"] == {"submitted": True}
    assert calls == 1
    async with factory() as session:
        item = await session.scalar(select(ImageGenerationItem))
        assert item.error_json["details"]["prompt"] == "private-prompt"
