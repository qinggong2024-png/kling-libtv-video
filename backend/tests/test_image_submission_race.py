import asyncio

from httpx import ASGITransport, AsyncClient
from libtv_agent.api import image_generations as routes
from libtv_agent.domain.models import ImageGenerationItem
from sqlalchemy import select
from test_image_quota_concurrency import post, world  # noqa: F401,E402


async def test_stale_replay_does_not_overwrite_success(world, monkeypatch):  # noqa: F811
    app, factory, provider, users = world
    provider_entered = asyncio.Event()
    release_provider = asyncio.Event()
    replay_loaded = asyncio.Event()
    release_replay = asyncio.Event()
    submit = provider.submit_prediction
    service = routes.submit_batch

    async def held_provider(*args):
        provider_entered.set()
        await release_provider.wait()
        return await submit(*args)

    async def held_replay(session, *, batch, **kwargs):
        if batch.items[0].status == "SUBMITTING":
            replay_loaded.set()
            await release_replay.wait()
        return await service(session, batch=batch, **kwargs)

    provider.submit_prediction = held_provider
    monkeypatch.setattr(routes, "submit_batch", held_replay)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(post(client, users[0], "same"))
        replay = None
        try:
            await asyncio.wait_for(provider_entered.wait(), 5)
            replay = asyncio.create_task(post(client, users[0], "same"))
            await asyncio.wait_for(replay_loaded.wait(), 5)
            release_provider.set()
            assert (await first).status_code == 201
            release_replay.set()
            assert (await replay).status_code == 201
        finally:
            release_provider.set()
            release_replay.set()
            await asyncio.gather(
                *[task for task in (first, replay) if task], return_exceptions=True
            )
    async with factory() as session:
        item = await session.scalar(select(ImageGenerationItem))
        assert item.status == "CREATED", (item.status, item.provider_task_id)
    assert len(provider.submissions) == 1
