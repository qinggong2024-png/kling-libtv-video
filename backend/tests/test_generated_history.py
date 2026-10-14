from datetime import UTC, datetime, timedelta
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.domain.models import ImageGenerationBatch
from test_image_generation_batches import _app
from test_creative_workflow import Flow, workflow  # noqa: F401


@pytest.mark.asyncio
async def test_image_history_paginates_without_provider_calls(tmp_path):
    app, settings = await _app(tmp_path)
    async with app.router.lifespan_context(app):
        owner = uuid.UUID(settings.dev_user_id)
        async with app.state.database.session_factory() as session:
            for index in range(105):
                session.add(ImageGenerationBatch(
                    user_id=owner, client_batch_id=f'client-{index}',
                    idempotency_key=f'key-{index}', request_hash='a' * 64,
                    name=f'history-{index}', provider='nanobanana', status='COMPLETED',
                    expected_generation_count=1, paid_submission_consent_at=datetime.now(UTC),
                    request_json={}, created_at=datetime.now(UTC) - timedelta(days=index),
                ))
            await session.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            headers = {'X-User-Id': str(owner)}
            first = await client.get('/api/v1/image-generation-batches', headers=headers)
            assert first.status_code == 200, first.text
            assert len(first.json()) == 100
            cursor = first.json()[-1]['nextCursor']
            second = await client.get(f'/api/v1/image-generation-batches?cursor={cursor}', headers=headers)
            assert second.status_code == 200, second.text
            assert len(second.json()) == 5
            assert 'nextCursor' not in second.json()[-1]
            assert not {item['id'] for item in first.json()} & {item['id'] for item in second.json()}
            assert not app.state.wavespeed_adapter.submissions
            invalid = await client.get(f'/api/v1/image-generation-batches?cursor={uuid.uuid4()}', headers=headers)
            assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_director_history_includes_tasks_without_client_key(workflow):
    flow = Flow(*workflow)
    await flow.create()
    response = await flow.client.get('/api/v1/creative-workflow/tasks', headers=flow.headers)
    assert response.status_code == 200, response.text
    assert flow.task_id in {item['id'] for item in response.json()}
    assert response.json()[0]['mode'] == 'OFFLINE_FAKE_ONLY'
    invalid = await flow.client.get(f'/api/v1/creative-workflow/tasks?cursor={uuid.uuid4()}', headers=flow.headers)
    assert invalid.status_code == 422
