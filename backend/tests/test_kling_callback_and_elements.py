from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.adapters.video_provider import ProviderOutput, ProviderTaskResult
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import AttemptStatus, ConsistencyLevel, VariantKind
from libtv_agent.domain.models import (
    Base,
    GenerationAttempt,
    GenerationVariant,
    ParentTask,
    User,
)
from libtv_agent.services.kling_callbacks import (
    KlingCallbackError,
    KlingCallbackObservation,
    process_kling_callback,
)
from libtv_agent.services.tasks import _build_task_read
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class FakeKlingAdapter:
    def __init__(self, result: ProviderTaskResult) -> None:
        self.result = result
        self.query_count = 0
        self.elements: dict[str, dict[str, Any]] = {}

    async def query(self, provider_task_id: str) -> ProviderTaskResult:
        assert provider_task_id == "remote-task-1"
        self.query_count += 1
        return self.result

    async def create_element(self, payload: Any) -> dict[str, Any]:
        element = {
            "id": "element-1",
            "status": "ready",
            "name": payload.element_name,
            "description": payload.element_description,
            "imageUrls": [
                payload.frontal_image,
                *payload.refer_images,
            ],
        }
        self.elements["element-1"] = element
        return {"data": element}

    async def query_element(
        self,
        *,
        task_id: str | None = None,
        external_task_id: str | None = None,
    ) -> dict[str, Any]:
        assert external_task_id is None
        return {"data": self.elements[str(task_id)]}

    async def list_elements(
        self,
        *,
        page_num: int,
        page_size: int,
        official: bool,
    ) -> dict[str, Any]:
        assert page_num == 1
        assert page_size == 30
        assert official is False
        return {
            "data": {
                "elements": list(self.elements.values()),
                "total": len(self.elements),
            }
        }

    async def delete_element(self, element_id: str) -> None:
        self.elements.pop(element_id)


def _verified_result(status: str = "succeeded") -> ProviderTaskResult:
    outputs = (
        (ProviderOutput(url="https://cdn.example.test/result.mp4", content_type="video"),)
        if status == "succeeded"
        else ()
    )
    return ProviderTaskResult(
        status=status,
        raw_status=status,
        outputs=outputs,
        raw_response={
            "id": "remote-task-1",
            "status": status,
            "outputs": [{"type": "video", "url": "https://cdn.example.test/result.mp4"}]
            if outputs
            else [],
        },
        credits_consumed=12,
    )


async def _database(tmp_path: Path) -> tuple[Any, async_sessionmaker[Any]]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'kling-callback.db').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _attempt_graph() -> tuple[ParentTask, GenerationVariant, GenerationAttempt]:
    task = ParentTask(
        id=uuid.uuid4(),
        user_id=USER_ID,
        client_task_id="callback-task",
        title="Callback task",
        asset_count=1,
        consistency_level=ConsistencyLevel.PASS,
    )
    variant = GenerationVariant(
        id=uuid.uuid4(),
        parent_task=task,
        variant_type=VariantKind.DYNAMIC,
        prompt_text="prompt",
        generation_config_json={"generationProvider": "kling"},
    )
    attempt = GenerationAttempt(
        id=uuid.uuid4(),
        variant=variant,
        status=AttemptStatus.RUNNING,
        provider="kling_official_api",
        task_id="remote-task-1",
        submitted_at=datetime.now(UTC),
    )
    return task, variant, attempt


@pytest.mark.asyncio
async def test_verified_callback_is_idempotent_and_exposes_provider_error_contract(
    tmp_path: Path,
) -> None:
    engine, factory = await _database(tmp_path)
    task, variant, attempt = _attempt_graph()
    adapter = FakeKlingAdapter(_verified_result("failed"))
    observation = KlingCallbackObservation(
        provider_task_id="remote-task-1",
        status="failed",
        message="provider rejected the video",
        outputs=(),
        raw_payload={
            "id": "remote-task-1",
            "status": "failed",
            "outputs": [],
        },
    )
    async with factory() as session:
        session.add(User(id=USER_ID, username="callback-user", password_hash="disabled"))
        session.add(task)
        await session.commit()

        first = await process_kling_callback(
            session,
            adapter=adapter,
            provider_name="kling_official_api",
            observation=observation,
        )
        second = await process_kling_callback(
            session,
            adapter=adapter,
            provider_name="kling_official_api",
            observation=observation,
        )

        assert first.duplicate is False
        assert second.duplicate is True
        assert attempt.error_message == "provider rejected the video"
        assert attempt.provider_error_retryable is False
        assert attempt.provider_error_details_json == {
            "providerTaskId": "remote-task-1",
            "providerStatus": "failed",
            "source": "verified_callback",
        }
        await session.refresh(task, attribute_names=["assets", "variants"])
        task_read = _build_task_read(
            task,
            100,
            None,
            {variant.id: attempt},
            {},
            {},
            None,
        )
        serialized = task_read.model_dump(by_alias=True)
        assert serialized["variants"][0]["providerErrorMessage"] == ("provider rejected the video")
        assert serialized["variants"][0]["providerErrorRetryable"] is False
        assert serialized["variants"][0]["providerErrorDetails"]["source"] == ("verified_callback")
    await engine.dispose()


@pytest.mark.asyncio
async def test_callback_rejects_status_that_does_not_match_official_query(
    tmp_path: Path,
) -> None:
    engine, factory = await _database(tmp_path)
    task, _variant, _attempt = _attempt_graph()
    async with factory() as session:
        session.add(User(id=USER_ID, username="callback-user", password_hash="disabled"))
        session.add(task)
        await session.commit()
        with pytest.raises(KlingCallbackError, match="does not match") as caught:
            await process_kling_callback(
                session,
                adapter=FakeKlingAdapter(_verified_result("running")),
                provider_name="kling_official_api",
                observation=KlingCallbackObservation(
                    provider_task_id="remote-task-1",
                    status="succeeded",
                    message=None,
                    outputs=(),
                    raw_payload={
                        "id": "remote-task-1",
                        "status": "succeeded",
                    },
                ),
            )
        assert caught.value.status_code == 409
    await engine.dispose()


@pytest.mark.asyncio
async def test_callback_route_accepts_official_top_level_contract(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'callback-route.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    settings = Settings(
        app_env="test",
        database_url=database_url,
        object_store_mode="local",
        artifact_root=tmp_path / "artifacts-callback",
        runner_root=tmp_path / "runner-callback",
        _env_file=None,
    )
    app = create_app(settings)
    adapter = FakeKlingAdapter(_verified_result())
    task, _variant, _attempt = _attempt_graph()
    async with app.router.lifespan_context(app):
        async with app.state.database.session_factory() as session:
            session.add(User(id=USER_ID, username="callback-user", password_hash="disabled"))
            session.add(task)
            await session.commit()
        app.state.kling_adapter = adapter
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/kling/callback",
                json={
                    "id": "remote-task-1",
                    "status": "succeeded",
                    "message": "completed",
                    "create_time": 1785400000,
                    "update_time": 1785400100,
                    "external_id": "local-intent-1",
                    "outputs": [
                        {
                            "type": "video",
                            "url": "https://cdn.example.test/result.mp4",
                        }
                    ],
                    "billing": [{"resource": "video", "quantity": 12}],
                },
            )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "accepted": True,
        "providerTaskId": "remote-task-1",
        "status": "succeeded",
        "duplicate": False,
        "workflowFinalized": False,
    }


@pytest.mark.asyncio
async def test_callback_route_rejects_missing_signature_when_configured(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'callback-auth.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    settings = Settings(
        app_env="test",
        database_url=database_url,
        object_store_mode="local",
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        kling_api_callback_url="https://callback.example.test/kling",
        kling_api_callback_secret="callback-secret-123456",
        _env_file=None,
    )
    app = create_app(settings)
    body = {"id": "missing", "status": "succeeded"}
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            missing = await client.post("/api/v1/kling/callback", json=body)
            assert missing.status_code == 401
            raw = json.dumps(body, separators=(",", ":")).encode()
            signature = hmac.new(b"callback-secret-123456", raw, hashlib.sha256).hexdigest()
            verified = await client.post(
                "/api/v1/kling/callback",
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Kling-Callback-Signature": signature,
                },
            )
            assert verified.status_code != 401


@pytest.mark.asyncio
async def test_element_routes_form_minimum_adapter_contract(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'elements.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    settings = Settings(
        app_env="test",
        database_url=database_url,
        object_store_mode="local",
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        _env_file=None,
    )
    app = create_app(settings)
    adapter = FakeKlingAdapter(_verified_result())
    user_headers = {"X-User-Id": str(USER_ID)}
    admin_headers = {"X-User-Id": str(ADMIN_ID)}

    async with app.router.lifespan_context(app):
        app.state.kling_adapter = adapter
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                "/api/v1/admin/kling/elements",
                headers=admin_headers,
                json={
                    "name": "model",
                    "description": "single-image subject",
                    "imageReferences": [
                        "https://cdn.example.test/front.jpg",
                    ],
                },
            )
            assert created.status_code == 201, created.text
            assert created.json()["id"] == "element-1"

            listed = await client.get("/api/v1/admin/kling/elements", headers=user_headers)
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()["items"]] == ["element-1"]

            fetched = await client.get(
                "/api/v1/admin/kling/elements/element-1",
                headers=user_headers,
            )
            assert fetched.status_code == 200

            forbidden_delete = await client.delete(
                "/api/v1/admin/kling/elements/element-1",
                headers=user_headers,
            )
            assert forbidden_delete.status_code == 403

            deleted = await client.delete(
                "/api/v1/admin/kling/elements/element-1",
                headers=admin_headers,
            )
            assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_element_list_accepts_official_empty_array_shape() -> None:
    from libtv_agent.services.kling_elements import list_elements

    class EmptyElementAdapter:
        async def list_elements(
            self,
            *,
            page_num: int,
            page_size: int,
            official: bool,
        ) -> dict[str, Any]:
            assert (page_num, page_size, official) == (1, 30, False)
            return {"code": 0, "message": "ok", "data": []}

    page = await list_elements(
        EmptyElementAdapter(),
        page_num=1,
        page_size=30,
        official=False,
    )

    assert page == {
        "items": [],
        "pageNum": 1,
        "pageSize": 30,
        "total": 0,
        "official": False,
    }


@pytest.mark.asyncio
async def test_element_list_expands_official_task_results() -> None:
    from libtv_agent.services.kling_elements import list_elements

    class OfficialElementAdapter:
        async def list_elements(
            self,
            *,
            page_num: int,
            page_size: int,
            official: bool,
        ) -> dict[str, Any]:
            assert (page_num, page_size, official) == (1, 30, True)
            return {
                "code": 0,
                "message": "ok",
                "data": [
                    {
                        "task_id": "task-173",
                        "task_status": "succeed",
                        "created_at": "2026-07-29T09:00:00Z",
                        "updated_at": "2026-07-29T09:01:00Z",
                        "task_result": {
                            "elements": [
                                {
                                    "element_id": "element-172",
                                    "name": "Official actor",
                                    "description": "Official preset subject",
                                    "status": "active",
                                    "image": "https://cdn.example.test/official.jpg",
                                    "video": {
                                        "video_url": ("https://cdn.example.test/official.mp4")
                                    },
                                }
                            ]
                        },
                    }
                ],
            }

    page = await list_elements(
        OfficialElementAdapter(),
        page_num=1,
        page_size=30,
        official=True,
    )

    assert page["total"] == 1
    assert page["official"] is True
    assert page["items"] == [
        {
            "id": "element-172",
            "name": "Official actor",
            "description": "Official preset subject",
            "status": "active",
            "imageUrls": ["https://cdn.example.test/official.jpg"],
            "videoUrl": "https://cdn.example.test/official.mp4",
            "voiceId": None,
            "createdAt": "2026-07-29T09:00:00Z",
            "updatedAt": "2026-07-29T09:01:00Z",
            "raw": {
                "element_id": "element-172",
                "name": "Official actor",
                "description": "Official preset subject",
                "status": "active",
                "image": "https://cdn.example.test/official.jpg",
                "video": {"video_url": "https://cdn.example.test/official.mp4"},
            },
        }
    ]
