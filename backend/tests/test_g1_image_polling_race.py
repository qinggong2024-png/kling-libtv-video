from httpx import ASGITransport, AsyncClient
from libtv_agent.domain.models import (
    ImageGenerationBatch,
    ImageGenerationItem,
    ImageGenerationOutput,
)
from libtv_agent.services.image_generations import refresh_batch
from sqlalchemy import func, select, update
from test_image_quota_concurrency import post, world  # noqa: F401


async def test_stale_image_poll_preserves_independent_completion(world):  # noqa: F811
    app, factory, provider, users = world
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await post(client, users[0], "image-poll-race")
        assert response.status_code == 201

    async def query(task_id):
        async with factory() as other:
            await other.execute(
                update(ImageGenerationItem).values(
                    status="COMPLETED", raw_response_json={"newer": True}
                )
            )
            await other.execute(update(ImageGenerationBatch).values(status="COMPLETED"))
            await other.commit()
        return {"data": {"id": task_id, "status": "processing"}}

    provider.get_prediction = query
    async with factory() as stale:
        batch = await stale.scalar(select(ImageGenerationBatch))
        await refresh_batch(stale, app=app, batch=batch)
    async with factory() as verify:
        item = await verify.scalar(select(ImageGenerationItem))
        batch = await verify.scalar(select(ImageGenerationBatch))
        assert item.status == "COMPLETED"
        assert item.raw_response_json == {"newer": True}
        assert batch.status == "COMPLETED"
    assert len(provider.submissions) == 1


async def test_two_preloaded_sessions_materialize_once(world, monkeypatch):  # noqa: F811
    app, factory, provider, users = world
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await post(client, users[0], "image-double-poll")).status_code == 201
    downloads = []

    async def query(task_id):
        return {
            "data": {
                "id": task_id,
                "status": "completed",
                "outputs": ["https://synthetic.example.test/output.png"],
            }
        }

    async def materialize(app, output):
        downloads.append(output.id)
        output.object_key = "synthetic/completed.png"

    provider.get_prediction = query
    monkeypatch.setattr("libtv_agent.services.image_generations._materialize_output", materialize)
    async with factory() as first, factory() as second:
        batch1 = await first.scalar(select(ImageGenerationBatch))
        batch2 = await second.scalar(select(ImageGenerationBatch))
        await refresh_batch(first, app=app, batch=batch1)
        await refresh_batch(second, app=app, batch=batch2)
        assert batch2.status == "COMPLETED"
    async with factory() as verify:
        assert await verify.scalar(select(func.count()).select_from(ImageGenerationOutput)) == 1
    assert len(downloads) == 1
    assert len(provider.submissions) == 1
