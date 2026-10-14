import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import libtv_agent.creative.provider_submission_persistence  # noqa: F401
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from libtv_agent.adapters.kling_official_cli import KlingCliError
from libtv_agent.adapters.libtv import FakeLibTVAdapter, GenerationResult
from libtv_agent.adapters.video_provider import ProviderSubmissionResult, ProviderTaskResult
from libtv_agent.adapters.wavespeed import WaveSpeedError
from libtv_agent.api import image_generations as routes
from libtv_agent.config import Settings
from libtv_agent.domain.enums import (
    AIUsageReservationStatus,
    AttemptStatus,
    CommandStatus,
    ParentTaskPhase,
    VariantKind,
)
from libtv_agent.domain.models import (
    AIUsageLedger,
    AIUsageReservation,
    Base,
    GenerationAttempt,
    GenerationCommand,
    GenerationVariant,
    ImageGenerationBatch,
    ParentTask,
    User,
)
from libtv_agent.runner.supervisor import RunnerSupervisor
from libtv_agent.services.ai_pricing import AIPricingError, estimate_text_price
from libtv_agent.services.ai_usage import (
    AIUsageLimitExceededError,
    read_ai_quota,
    reserve_priced_ai_usage,
    settle_ai_usage,
)
from libtv_agent.services.image_generations import (
    ImageItemSpec,
    create_batch_record,
    refresh_batch,
    submit_batch,
)
from libtv_agent.services.media_ai_usage import (
    IMAGE_OPERATION,
    MediaAIUsageBlockedError,
    MediaUsageRequest,
    billing_quantity,
    claim_media_submission,
    find_media_usage,
    finish_media_usage,
    image_usage_request,
    media_quote,
    reserve_image_batch,
    reserve_media_batch,
    reserve_video_attempts,
    video_usage_request,
)
from libtv_agent.services.runtime_control import get_runtime_config, update_runtime_config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_creative_provider_requests import workflow as workflow

IMAGE_MODEL = "google/nano-banana-2/text-to-image"
VIDEO_PROVIDER = "kling_official_api"
VIDEO_MODEL = "kling-video-test"


def settings_for(tmp_path, *, price=2_000_000, **overrides):
    prices = []
    for provider, model, unit, rate in (
        ("wavespeed", IMAGE_MODEL, "image", price),
        ("wavespeed", "google/nano-banana-2/edit", "image", price),
        (VIDEO_PROVIDER, VIDEO_MODEL, "video_second", price // 10),
        ("wavespeed_video", VIDEO_MODEL, "video_second", price // 10),
        ("libtv", VIDEO_MODEL, "video_second", price // 10),
        ("openai", "text-test", "input_token", 1),
        ("openai", "text-test", "output_token", 1000),
    ):
        prices.append({
            "provider": provider, "model": model, "unit": unit, "rate_microusd": rate,
            "quantity": 1, "effective_at": "2026-01-01T00:00:00Z",
            "source": "isolated fixture exact rate", "version": "test-v1",
            "reference_only": False, "all_parameters_upper_bound": True,
            **({"trusted_input_token_upper_bound": 1000} if unit == "input_token" else {}),
        })
    return Settings(
        _env_file=None, app_env="test", runner_root=tmp_path / "runner",
        artifact_root=tmp_path / "artifacts", object_store_mode="local",
        wavespeed_enabled=True, wavespeed_api_key="synthetic-only",
        kling_api_enabled=True, paid_submissions_paused=False,
        ai_price_catalog_json=json.dumps({"version": "test-v1", "prices": prices}),
        **overrides,
    )


@pytest.fixture
async def world(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'media-budget.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner = uuid.uuid4()
    async with factory() as session:
        session.add(User(id=owner, username="media-owner", password_hash="disabled"))
        await session.commit()
    yield factory, owner, settings_for(tmp_path)
    await engine.dispose()


class ImageSpy:
    def __init__(self, *, error=None, factory=None):
        self.error = error
        self.factory = factory
        self.submissions = 0
        self.uploads = 0
        self.queries = 0
        self.raw = {"data": {"id": "prediction-1", "status": "processing"}}

    async def upload_media(self, path):
        self.uploads += 1
        return "https://offline.example/reference.png"

    async def submit_prediction(self, model, payload):
        self.submissions += 1
        if self.factory:
            async with self.factory() as verify:
                reservation = await verify.scalar(select(AIUsageReservation).where(
                    AIUsageReservation.operation_type == IMAGE_OPERATION,
                ))
                assert reservation.status == AIUsageReservationStatus.RESERVED
                assert reservation.actual_cost_status == "SUBMISSION_STARTED"
        if self.error:
            raise self.error
        return {"data": {"id": "prediction-1", "status": "created"}}

    async def get_prediction(self, task_id):
        self.queries += 1
        return self.raw


class VideoSpy:
    def __init__(self, *, error=None, factory=None, provider=VIDEO_PROVIDER):
        self.error = error
        self.factory = factory
        self.provider = provider
        self.submissions = 0
        self.queries = 0
        self.result = ProviderTaskResult("failed", "failed", (), {})

    def get_provider_name(self):
        return self.provider

    async def submit(self, request):
        self.submissions += 1
        if self.factory:
            async with self.factory() as verify:
                reservation = await verify.scalar(select(AIUsageReservation).where(
                    AIUsageReservation.operation_type == "AI_VIDEO_SUBMIT",
                ))
                assert reservation.status == AIUsageReservationStatus.RESERVED
                assert reservation.actual_cost_status == "SUBMISSION_STARTED"
        if self.error:
            raise self.error
        return ProviderSubmissionResult("remote-video-1", "queued", None, VIDEO_MODEL, {})

    async def query(self, task_id):
        self.queries += 1
        return self.result


async def image_world(session, owner, *, count=1):
    batch = create_batch_record(
        user_id=owner, idempotency_key=f"batch-{uuid.uuid4()}", request_hash="a" * 64,
        manifest={
            "clientBatchId": "batch", "name": "offline test", "provider": "nanobanana",
            "expectedGenerationCount": count, "aspectRatio": "9:16", "resolution": "2k",
            "outputFormat": "png",
        },
        item_specs=[
            ImageItemSpec(str(index), "outfit", "name", "", "fusion", "front", "label",
                          "Test prompt", ())
            for index in range(count)
        ],
    )
    session.add(batch)
    await session.flush()
    return batch


async def video_world(session, owner, *, provider=VIDEO_PROVIDER):
    task = ParentTask(
        user_id=owner, client_task_id=f"media-{uuid.uuid4()}", title="media", asset_count=0,
        phase=ParentTaskPhase.QUEUED,
    )
    session.add(task)
    await session.flush()
    variant = GenerationVariant(
        parent_task_id=task.id, variant_type=VariantKind.STABLE, prompt_text="Test video",
        generation_config_json={"duration": 10, "modelKey": VIDEO_MODEL},
    )
    session.add(variant)
    await session.flush()
    attempt = GenerationAttempt(
        variant_id=variant.id, provider=provider, provider_model=VIDEO_MODEL,
        status=AttemptStatus.DISPATCH_PENDING, intent_hash=uuid.uuid4().hex,
    )
    session.add(attempt)
    await session.flush()
    command = GenerationCommand(attempt_id=attempt.id, status=CommandStatus.READY)
    session.add(command)
    await session.commit()
    return task, variant, attempt, command


def supervisor(settings, spy, monkeypatch):
    runner = RunnerSupervisor(None, None, settings, kling_adapter=spy)
    monkeypatch.setattr(
        "libtv_agent.runner.supervisor.real_provider_submission_authorized", lambda _: True,
    )
    return runner


async def text_reserve(session, owner, settings, units, key):
    quote = estimate_text_price(
        settings, provider="openai", model="text-test", input_chars=1,
        input_image_count=0, max_output_tokens=units - 1,
    )
    assert quote.risk_units == units
    assert quote.snapshot["input_bound_source"] == "TRUSTED_MODEL_INPUT_TOKEN_UPPER_BOUND"
    result = await reserve_priced_ai_usage(
        session, settings, user_id=owner, task_id=None, operation_type="AI_ANALYSIS",
        quote=quote, input_chars=1, input_image_count=0,
        max_output_tokens=units - 1, idempotency_key=key, request_hash="b" * 64,
    )
    await session.commit()
    return result.reservation


@pytest.mark.parametrize("kind", ["image", "video"])
async def test_shared_50_dollar_pool_text_spend_blocks_media_before_provider(
    world, tmp_path, monkeypatch, kind,
):
    factory, owner, settings = world
    async with factory() as session:
        for index in range(10):
            text = await text_reserve(session, owner, settings, 4900, f"text-{index}")
            await settle_ai_usage(
                session, text.id, status=AIUsageReservationStatus.SETTLED,
                actual_cost_microusd=4_900_000,
            )
            await session.commit()
        if kind == "image":
            batch = await image_world(session, owner)
            with pytest.raises(AIUsageLimitExceededError):
                await reserve_image_batch(session, settings, batch)
            await session.commit()
            spy = ImageSpy()
            await submit_batch(session, batch=batch, adapter=spy, file_paths=[])
            assert spy.submissions == spy.uploads == 0
        else:
            task, _, attempt, command = await video_world(session, owner)
            with pytest.raises(AIUsageLimitExceededError):
                await reserve_video_attempts(session, settings, task, [attempt])
            await session.commit()
            spy = VideoSpy()
            runner = supervisor(settings, spy, monkeypatch)
            await runner._execute(session, command.id)
            assert spy.submissions == 0
            assert attempt.last_error_code == "MEDIA_PRICE_RESERVATION_MISSING"
        quota = await read_ai_quota(session, settings, user_id=owner)
        assert quota["available"] == "1.000"
        assert quota["reserved"] == quota["unknown"] == "0.000"


async def test_text_pending_reservation_and_media_share_daily_allowance(world):
    factory, owner, settings = world
    settings = settings.model_copy(update={"ai_risk_daily_user_limit": 5000})
    async with factory() as session:
        await text_reserve(session, owner, settings, 4000, "pending-text")
        batch = await image_world(session, owner)
        with pytest.raises(AIUsageLimitExceededError):
            await reserve_image_batch(session, settings, batch)
        await session.commit()
        spy = ImageSpy()
        await submit_batch(session, batch=batch, adapter=spy, file_paths=[])
        assert spy.submissions == 0
        assert (await read_ai_quota(session, settings, user_id=owner))["reserved"] == "4.000"


@pytest.mark.parametrize("count,price", [(3, 4_000_000), (1, 5_001_000)])
async def test_full_image_batch_and_single_request_caps_are_atomic(world, tmp_path, count, price):
    factory, owner, _ = world
    settings = settings_for(tmp_path, price=price)
    async with factory() as session:
        batch = await image_world(session, owner, count=count)
        with pytest.raises(AIPricingError):
            await reserve_image_batch(session, settings, batch)
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 0
        spy = ImageSpy()
        await submit_batch(session, batch=batch, adapter=spy, file_paths=[])
        assert spy.submissions == spy.uploads == 0


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize("catalog_change", ["empty", "reference", "expired", "unverified"])
async def test_unknown_reference_and_expired_prices_never_authorize_media(
    world, kind, catalog_change,
):
    factory, owner, settings = world
    catalog = json.loads(settings.ai_price_catalog_json)
    if catalog_change == "empty":
        catalog["prices"] = []
    for price in catalog["prices"]:
        if catalog_change == "reference":
            price["reference_only"] = True
        if catalog_change == "expired":
            price["expires_at"] = "2026-01-02T00:00:00Z"
        if catalog_change == "unverified":
            price.pop("all_parameters_upper_bound")
    settings = settings.model_copy(update={
        "ai_unknown_price_policy": "cap", "ai_price_catalog_json": json.dumps(catalog),
    })
    request = MediaUsageRequest(
        owner, IMAGE_OPERATION if kind == "image" else "AI_VIDEO_SUBMIT", "price-test",
        "wavespeed" if kind == "image" else VIDEO_PROVIDER,
        IMAGE_MODEL if kind == "image" else VIDEO_MODEL,
        kind, 1 if kind == "image" else 10, "a" * 64,
    )
    with pytest.raises(AIPricingError):
        media_quote(settings, request)
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 0


@pytest.mark.parametrize("kind", ["image", "video"])
@pytest.mark.parametrize("catalog_type", ["low_tier", "reference", "unknown"])
async def test_high_resolution_request_cannot_inherit_unsafe_price(
    world, monkeypatch, kind, catalog_type,
):
    factory, owner, settings = world
    catalog = json.loads(settings.ai_price_catalog_json)
    for price in catalog["prices"]:
        if catalog_type == "low_tier":
            price.pop("all_parameters_upper_bound")
            price["source"] = "synthetic 480p/1k silent standard tier only"
        elif catalog_type == "reference":
            price["reference_only"] = True
    if catalog_type == "unknown":
        catalog["prices"] = []
    settings = settings.model_copy(update={
        "ai_unknown_price_policy": "cap", "ai_price_catalog_json": json.dumps(catalog),
    })
    async with factory() as session:
        if kind == "image":
            batch = await image_world(session, owner)
            batch.request_json = {**batch.request_json, "resolution": "4k", "quality": "high"}
            with pytest.raises(AIPricingError):
                await reserve_image_batch(session, settings, batch)
            await session.commit()
            spy = ImageSpy()
            await submit_batch(session, batch=batch, adapter=spy, file_paths=[])
            assert spy.submissions == spy.uploads == 0
        else:
            task, variant, attempt, command = await video_world(session, owner)
            variant.generation_config_json = {
                **variant.generation_config_json, "resolution": "1080p",
                "quality": "high", "sound": "on",
            }
            with pytest.raises(AIPricingError):
                await reserve_video_attempts(session, settings, task, [attempt])
            await session.commit()
            spy = VideoSpy()
            await supervisor(settings, spy, monkeypatch)._execute(session, command.id)
            assert spy.submissions == 0
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 0


@pytest.mark.parametrize("kind", ["image", "video"])
async def test_old_unverified_price_reservation_cannot_start_new_submission(
    world, monkeypatch, kind,
):
    factory, owner, settings = world
    async with factory() as session:
        if kind == "image":
            batch = await image_world(session, owner)
            await reserve_image_batch(session, settings, batch)
            request = image_usage_request(batch, batch.items[0])
        else:
            task, variant, attempt, command = await video_world(session, owner)
            await reserve_video_attempts(session, settings, task, [attempt])
            request = video_usage_request(settings, task, variant, attempt)
        reservation = await find_media_usage(
            session, user_id=owner, operation=request.operation, key=request.key,
        )
        snapshot = json.loads(json.dumps(reservation.pricing_snapshot_json))
        for price in snapshot["prices"].values():
            price.pop("all_parameters_upper_bound")
        reservation.pricing_snapshot_json = snapshot
        await session.commit()
        with pytest.raises(MediaAIUsageBlockedError) as blocked:
            await claim_media_submission(session, request)
        assert blocked.value.code == "MEDIA_PRICE_RESERVATION_INVALID"
        assert reservation.actual_cost_status == "PENDING"
        if kind == "image":
            spy = ImageSpy()
            await submit_batch(session, batch=batch, adapter=spy, file_paths=[])
            assert spy.submissions == spy.uploads == 0
        else:
            spy = VideoSpy()
            await supervisor(settings, spy, monkeypatch)._execute(session, command.id)
            assert spy.submissions == 0


async def test_historical_submitted_receipt_can_settle_without_new_upper_bound_marker(world):
    factory, owner, settings = world
    async with factory() as session:
        batch = await image_world(session, owner)
        await reserve_image_batch(session, settings, batch)
        request = image_usage_request(batch, batch.items[0])
        reservation = await claim_media_submission(session, request)
        snapshot = json.loads(json.dumps(reservation.pricing_snapshot_json))
        snapshot["prices"]["image"].pop("all_parameters_upper_bound")
        reservation.pricing_snapshot_json = snapshot
        await finish_media_usage(
            session, reservation, quantity=1, provider_response_id="historical-prediction",
        )
        await session.commit()
        assert reservation.status == AIUsageReservationStatus.SETTLED
        assert reservation.actual_cost_microusd == 2_000_000


@pytest.mark.parametrize("error", [
    TimeoutError("unknown acceptance"),
    RuntimeError("malformed submission result"),
    WaveSpeedError("ACCEPTED_FAILURE", "accepted", submitted=True),
])
async def test_image_unknown_and_replay_never_submit_twice(world, error):
    factory, owner, settings = world
    async with factory() as session:
        batch = await image_world(session, owner)
        await reserve_image_batch(session, settings, batch)
        await session.commit()
        spy = ImageSpy(error=error, factory=factory)
        await submit_batch(session, batch=batch, adapter=spy, file_paths=[])
        await submit_batch(session, batch=batch, adapter=spy, file_paths=[])
        reservation = await find_media_usage(
            session, user_id=owner, operation=IMAGE_OPERATION,
            key=f"image:{batch.id}:{batch.items[0].id}",
        )
        assert reservation.status == AIUsageReservationStatus.UNKNOWN
        assert batch.items[0].status == "WRITE_UNCERTAIN"
        assert spy.submissions == 1
        await reserve_image_batch(session, settings, batch)
        with pytest.raises(MediaAIUsageBlockedError):
            await claim_media_submission(session, image_usage_request(batch, batch.items[0]))


@pytest.mark.parametrize("error", [
    TimeoutError("unknown acceptance"),
    KlingCliError("ACCEPTED_FAILURE", "accepted", submitted=True),
])
async def test_video_unknown_replay_does_not_submit_again(world, monkeypatch, error):
    factory, owner, settings = world
    async with factory() as session:
        task, _, attempt, command = await video_world(session, owner)
        await reserve_video_attempts(session, settings, task, [attempt])
        await session.commit()
        spy = VideoSpy(error=error, factory=factory)
        runner = supervisor(settings, spy, monkeypatch)
        await runner._execute(session, command.id)
        assert attempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT
        await runner._execute(session, command.id)
        assert spy.submissions == 1
        reservation = await session.scalar(select(AIUsageReservation))
        assert reservation.status == AIUsageReservationStatus.UNKNOWN
        # Even an accidentally reset legacy command cannot bypass the USD claim.
        command.status = CommandStatus.READY
        command.launch_started_at = None
        await session.commit()
        await runner._execute(session, command.id)
        assert spy.submissions == 1


@pytest.mark.parametrize("kind", ["image", "video"])
async def test_reliable_pre_submit_failure_releases_usd(world, monkeypatch, kind):
    factory, owner, settings = world
    async with factory() as session:
        if kind == "image":
            batch = await image_world(session, owner)
            await reserve_image_batch(session, settings, batch)
            await session.commit()
            spy = ImageSpy(error=WaveSpeedError("INVALID", "not sent", submitted=False))
            await submit_batch(session, batch=batch, adapter=spy, file_paths=[])
        else:
            task, _, attempt, command = await video_world(session, owner)
            await reserve_video_attempts(session, settings, task, [attempt])
            await session.commit()
            spy = VideoSpy(error=KlingCliError("INVALID", "not sent", submitted=False))
            await supervisor(settings, spy, monkeypatch)._execute(session, command.id)
        reservation = await session.scalar(select(AIUsageReservation))
        assert reservation.status == AIUsageReservationStatus.RELEASED
        quota = await read_ai_quota(session, settings, user_id=owner)
        assert quota["available"] == "50.000"


@pytest.mark.parametrize("usage", [None, {"image_count": 1}])
async def test_image_background_poll_settles_snapshot_or_keeps_unknown(world, monkeypatch, usage):
    factory, owner, settings = world
    spy = ImageSpy()
    async with factory() as session:
        batch = await image_world(session, owner)
        await reserve_image_batch(session, settings, batch)
        await session.commit()
        await submit_batch(session, batch=batch, adapter=spy, file_paths=[])
        inflight = await session.scalar(select(AIUsageReservation))
        assert inflight.status == AIUsageReservationStatus.RESERVED
        assert inflight.actual_cost_status == "SUBMISSION_STARTED"
        spy.raw = {"data": {
            "status": "completed", "outputs": ["https://offline.example/output.png"],
            **({"usage": usage} if usage else {}),
        }}
        async def materialize(app, output):
            output.object_key = "isolated/output.png"
        monkeypatch.setattr(
            "libtv_agent.services.image_generations._materialize_output", materialize,
        )
        # New live catalog cannot change the stored settlement price.
        settings = settings.model_copy(update={
            "ai_price_catalog_json": '{"version":"v2","prices":[]}',
        })
        app = SimpleNamespace(state=SimpleNamespace(wavespeed_adapter=spy, settings=settings))
        await refresh_batch(session, app=app, batch=batch)
        await refresh_batch(session, app=app, batch=batch)
        reservation = await session.scalar(select(AIUsageReservation))
        assert reservation.status == (
            AIUsageReservationStatus.SETTLED if usage else AIUsageReservationStatus.UNKNOWN
        )
        assert reservation.actual_cost_microusd == (2_000_000 if usage else None)
        assert spy.queries == 1
        assert spy.submissions == 1


@pytest.mark.parametrize("usage", [None, {"video_seconds": 10}])
async def test_video_background_terminal_result_uses_price_snapshot(world, monkeypatch, usage):
    factory, owner, settings = world
    async with factory() as session:
        task, _, attempt, command = await video_world(session, owner)
        await reserve_video_attempts(session, settings, task, [attempt])
        await session.commit()
        spy = VideoSpy(factory=factory)
        runner = supervisor(settings, spy, monkeypatch)
        await runner._execute(session, command.id)
        inflight = await session.scalar(select(AIUsageReservation))
        assert inflight.status == AIUsageReservationStatus.RESERVED
        assert inflight.actual_cost_status == "SUBMISSION_STARTED"
        # A provider FAILED result can still have attributable billed usage.
        spy.result = ProviderTaskResult(
            "failed", "failed", (), {"usage": usage} if usage else {},
        )
        await runner.poll_kling_tasks(session)
        reservation = await session.scalar(select(AIUsageReservation))
        assert reservation.status == (
            AIUsageReservationStatus.SETTLED if usage else AIUsageReservationStatus.UNKNOWN
        )
        assert reservation.actual_cost_microusd == (2_000_000 if usage else None)
        assert spy.submissions == spy.queries == 1


async def test_historical_image_lookup_allowed_but_pending_cannot_submit(world):
    factory, owner, settings = world
    async with factory() as session:
        batch = await image_world(session, owner)
        await session.commit()
        spy = ImageSpy()
        await submit_batch(session, batch=batch, adapter=spy, file_paths=[])
        assert spy.submissions == spy.uploads == 0
        item = batch.items[0]
        item.status = "CREATED"
        item.provider_task_id = "historical-handle"
        await session.commit()
        await refresh_batch(
            session, app=SimpleNamespace(state=SimpleNamespace(wavespeed_adapter=spy)), batch=batch,
        )
        assert spy.queries == 1
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 0


async def test_historical_video_without_budget_is_query_only(world, monkeypatch):
    factory, owner, settings = world
    async with factory() as session:
        _, _, attempt, command = await video_world(session, owner)
        spy = VideoSpy()
        runner = supervisor(settings, spy, monkeypatch)
        await runner._execute(session, command.id)
        assert spy.submissions == 0
        attempt.status = AttemptStatus.RUNNING
        attempt.task_id = "historical-task"
        command.status = CommandStatus.PROCESS_STARTED
        await session.commit()
        await runner.poll_kling_tasks(session)
        assert spy.queries == 1
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 0


@pytest.mark.parametrize("mode", ["fake", "replay"])
async def test_offline_three_images_use_synthetic_capacity_and_settle_zero(world, mode):
    factory, owner, settings = world
    async with factory() as session:
        requests = [
            MediaUsageRequest(
                owner, IMAGE_OPERATION, f"offline-{index}", f"offline:{mode}",
                "synthetic", "image", 1, str(index) * 64, offline=True,
            ) for index in range(3)
        ]
        reservations = await reserve_media_batch(session, settings, requests)
        await session.commit()
        assert sum(item.risk_units for item in reservations) == 3
        assert all(item.estimated_cost_microusd == 0 for item in reservations)
        for request, reservation in zip(requests, reservations, strict=True):
            await claim_media_submission(session, request)
            await finish_media_usage(session, reservation)
        await session.commit()
        quota = await read_ai_quota(session, settings, user_id=owner)
        assert quota["available"] == "50.000"
        assert quota["settled"] == "0.000"


async def test_real_video_does_not_inherit_unrelated_fake_libtv_mode(world):
    factory, owner, settings = world
    async with factory() as session:
        for provider in (VIDEO_PROVIDER, "wavespeed_video"):
            task, variant, attempt, _ = await video_world(session, owner, provider=provider)
            request = video_usage_request(settings, task, variant, attempt)
            assert request.provider == provider
            assert not request.offline
            assert media_quote(settings, request).estimated_cost_microusd == 2_000_000
        task, variant, attempt, _ = await video_world(session, owner, provider="libtv")
        with pytest.raises(AIPricingError, match="actual fake/replay adapter"):
            video_usage_request(settings, task, variant, attempt, adapter=VideoSpy())


async def test_actual_fake_video_backend_reserves_and_settles_zero(world, monkeypatch):
    factory, owner, settings = world
    adapter = FakeLibTVAdapter()
    async with factory() as session:
        task, _, attempt, command = await video_world(session, owner, provider="libtv")
        await reserve_video_attempts(session, settings, task, [attempt], adapter=adapter)
        await session.commit()
        runner = RunnerSupervisor(adapter, None, settings, kling_adapter=VideoSpy())
        # Avoid download/ffmpeg; drive the real completion handler's missing-variant return.
        async def failed_download(*args, **kwargs):
            raise OSError("isolated download disabled")
        monkeypatch.setattr("libtv_agent.runner.supervisor.download_with_retries", failed_download)
        async def run_generation(**kwargs):
            return GenerationResult("SUCCEEDED", {"taskId": "fake", "videoUrl": "fake://video"})
        monkeypatch.setattr(adapter, "run_generation", run_generation)
        await runner._execute(session, command.id)
        reservation = await session.scalar(select(AIUsageReservation))
        assert reservation.status == AIUsageReservationStatus.SETTLED
        assert reservation.actual_cost_microusd == 0
        assert reservation.actual_cost_status == "OFFLINE"


async def test_competing_submission_claims_have_one_winner(world):
    factory, owner, settings = world
    async with factory() as session:
        batch = await image_world(session, owner)
        request = image_usage_request(batch, batch.items[0])
        await reserve_image_batch(session, settings, batch)
        await session.commit()
    async def claim():
        async with factory() as session:
            try:
                await claim_media_submission(session, request)
                return "claimed"
            except MediaAIUsageBlockedError:
                await session.rollback()
                return "blocked"
    assert sorted(await asyncio.gather(claim(), claim())) == ["blocked", "claimed"]
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 1
        assert await session.scalar(
            select(func.count()).select_from(AIUsageLedger).where(
                AIUsageLedger.entry_type == "UNKNOWN",
            )
        ) == 0


async def test_daily_denial_during_image_batch_rolls_back_every_item(world):
    factory, owner, settings = world
    settings = settings.model_copy(update={"ai_risk_daily_user_limit": 5000})
    async with factory() as session:
        batch = await image_world(session, owner, count=3)
        with pytest.raises(AIUsageLimitExceededError):
            await reserve_image_batch(session, settings, batch)
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(AIUsageReservation)) == 0
        assert (await read_ai_quota(session, settings, user_id=owner))["reserved"] == "0.000"
        spy = ImageSpy()
        await submit_batch(session, batch=batch, adapter=spy, file_paths=[])
        assert spy.submissions == spy.uploads == 0


@pytest.mark.parametrize("outcome", ["limited", "unknown"])
async def test_libtv_command_host_boundary_denial_and_unknown_never_relaunch(
    world, monkeypatch, outcome,
):
    factory, owner, settings = world
    settings = settings.model_copy(update={
        "libtv_adapter_mode": "real",
        "ai_risk_daily_user_limit": 1000 if outcome == "limited" else 50_000,
    })
    class HostSpy:
        calls = 0

        def launch_generation(self, *args):
            self.calls += 1
            raise TimeoutError("isolated host acceptance unknown")

    host = HostSpy()
    monkeypatch.setattr(
        "libtv_agent.runner.supervisor.require_paid_generation_authorized", lambda _: None,
    )
    async with factory() as session:
        task, _, attempt, command = await video_world(session, owner, provider="libtv")
        if outcome == "limited":
            with pytest.raises(AIUsageLimitExceededError):
                await reserve_video_attempts(session, settings, task, [attempt])
        else:
            await reserve_video_attempts(session, settings, task, [attempt])
        await session.commit()
        runner = RunnerSupervisor(
            None, None, settings, kling_adapter=VideoSpy(), command_host_manager=host,
        )
        await runner._execute(session, command.id)
        assert host.calls == (1 if outcome == "unknown" else 0)
        await runner._execute(session, command.id)
        assert host.calls == (1 if outcome == "unknown" else 0)
        if outcome == "unknown":
            assert attempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT
            assert (await session.scalar(select(AIUsageReservation))).status == (
                AIUsageReservationStatus.UNKNOWN
            )
        else:
            assert attempt.last_error_code == "MEDIA_PRICE_RESERVATION_MISSING"


async def test_video_crash_after_budget_claim_recovers_unknown_without_provider(
    world, monkeypatch,
):
    factory, owner, settings = world
    async with factory() as session:
        task, variant, attempt, command = await video_world(session, owner)
        await reserve_video_attempts(session, settings, task, [attempt])
        await claim_media_submission(
            session, video_usage_request(settings, task, variant, attempt),
        )
        command.status = CommandStatus.LAUNCH_STARTED
        command.launch_started_at = datetime.now(UTC) - timedelta(days=1)
        command.lease_expires_at = datetime.now(UTC) - timedelta(days=1)
        attempt.status = AttemptStatus.LAUNCHING
        attempt.launch_started_at = command.launch_started_at
        await session.commit()
        spy = VideoSpy()
        runner = supervisor(settings, spy, monkeypatch)
        assert await runner.recover_stale_launch_started_commands(session) == 1
        assert attempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT
        assert (await session.scalar(select(AIUsageReservation))).status == (
            AIUsageReservationStatus.UNKNOWN
        )
        assert spy.submissions == 0
        assert await runner.recover_stale_launch_started_commands(session) == 0
        assert spy.submissions == 0


@pytest.mark.parametrize("usage", [None, {"video_seconds": 10}])
async def test_video_success_settlement_survives_download_failure(world, monkeypatch, usage):
    from libtv_agent.adapters.video_provider import ProviderOutput

    factory, owner, settings = world
    async with factory() as session:
        task, _, attempt, command = await video_world(session, owner)
        await reserve_video_attempts(session, settings, task, [attempt])
        await session.commit()
        spy = VideoSpy()
        runner = supervisor(settings, spy, monkeypatch)
        await runner._execute(session, command.id)
        spy.result = ProviderTaskResult(
            "succeeded", "succeeded", (ProviderOutput("https://offline.example/video.mp4"),),
            {"usage": usage} if usage else {},
        )
        async def failed_download(*args, **kwargs):
            raise OSError("isolated download failure")
        monkeypatch.setattr("libtv_agent.runner.supervisor.download_with_retries", failed_download)
        await runner.poll_kling_tasks(session)
        assert attempt.status == AttemptStatus.SUCCEEDED
        reservation = await session.scalar(select(AIUsageReservation))
        assert reservation.status == (
            AIUsageReservationStatus.SETTLED if usage else AIUsageReservationStatus.UNKNOWN
        )
        assert reservation.actual_cost_microusd == (2_000_000 if usage else None)
        assert spy.submissions == 1


async def test_video_poll_timeout_retains_unknown_without_resubmission(world, monkeypatch):
    factory, owner, settings = world
    async with factory() as session:
        task, _, attempt, command = await video_world(session, owner, provider="wavespeed_video")
        await reserve_video_attempts(session, settings, task, [attempt])
        await session.commit()
        spy = VideoSpy(provider="wavespeed_video")
        runner = supervisor(settings, spy, monkeypatch)
        await runner._execute(session, command.id)
        attempt.submitted_at = datetime.now(UTC) - timedelta(days=1)
        await session.commit()
        await runner.poll_kling_tasks(session)
        assert spy.submissions == 1
        assert spy.queries == 0
        assert attempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT
        assert (await session.scalar(select(AIUsageReservation))).status == (
            AIUsageReservationStatus.UNKNOWN
        )


def test_output_duration_points_and_urls_are_not_billing_usage():
    assert billing_quantity({"duration": 10, "actualPoints": 10}, "video") is None
    assert billing_quantity({"outputs": ["https://offline.example/image.png"]}, "image") is None
    assert billing_quantity({"usage": {"video_seconds": True}}, "video") is None
    assert billing_quantity({"usage": {"video_seconds": -1}}, "video") is None


async def test_image_api_budget_denial_has_zero_provider_calls(world):
    from test_image_quota_concurrency import post

    factory, owner, settings = world
    settings = settings.model_copy(update={"ai_risk_daily_user_limit": 1000})
    async with factory() as session:
        runtime = await get_runtime_config(session, settings)
        config = {
            **runtime.config_json, "internalPilotEnabled": True,
            "pilotUserIds": [str(owner)], "pilotBudgetLimit": 10,
        }
        await update_runtime_config(
            session, settings, config=config, actor_id=owner,
            reason="isolated media budget test", expected_version=runtime.version,
        )
        await session.commit()
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.state.settings = settings
    app.state.database = SimpleNamespace(session_factory=factory)
    app.state.wavespeed_adapter = ImageSpy()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await post(client, owner, "denied")
    assert response.status_code == 429, response.text
    assert app.state.wavespeed_adapter.submissions == app.state.wavespeed_adapter.uploads == 0
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ImageGenerationBatch)) == 0


@pytest.mark.parametrize("outcome", [
    "missing_price", "reference_price", "limited", "missing_usage", "priced_usage",
    "completed_missing_usage",
    "timeout", "not_submitted", "invalid_response",
])
async def test_creative_live_executor_uses_shared_usd_boundary(
    workflow, tmp_path, outcome,
):
    from libtv_agent.services.creative_provider_executor import (
        CreativeExecutionControls,
        CreativeProviderExecutionRejected,
        execute_creative_image,
    )
    from test_creative_provider_executor import _prepared_ticket

    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path,
    )
    catalog = {
        "version": "creative-test-v1", "prices": [{
            "provider": "wavespeed", "model": request.model, "unit": "image",
            "rate_microusd": 100, "quantity": 1, "effective_at": "2026-01-01T00:00:00Z",
            "source": "isolated exact fixture", "version": "creative-test-v1",
            "reference_only": outcome == "reference_price",
            "all_parameters_upper_bound": True,
        }],
    }
    catalog["prices"].extend(
        price for price in json.loads(settings_for(tmp_path).ai_price_catalog_json)["prices"]
        if price["provider"] == "openai"
    )
    if outcome == "missing_price":
        catalog["prices"] = []
    settings = inputs["settings"].model_copy(update={
        "ai_price_catalog_json": json.dumps(catalog),
        "ai_risk_daily_user_limit": 1 if outcome == "limited" else 50_000,
    })
    factory = flow.app.state.database.session_factory

    class CreativeSpy(ImageSpy):
        async def upload_media(self, path, **kwargs):
            return await super().upload_media(path)

        async def submit_prediction(self, model, payload, **kwargs):
            response = await super().submit_prediction(model, payload)
            if outcome == "invalid_response":
                return {}
            if outcome == "priced_usage":
                response["data"]["usage"] = {"image_count": 1}
            if outcome == "completed_missing_usage":
                response["data"]["status"] = "completed"
            return response

    error = TimeoutError("unknown acceptance") if outcome == "timeout" else (
        WaveSpeedError("NOT_SENT", "not sent", submitted=False)
        if outcome == "not_submitted" else None
    )
    spy = CreativeSpy(error=error, factory=factory)
    controls = CreativeExecutionControls(
        mode="live", admin_live_enabled=True, human_confirmed=True,
    )
    kwargs = {
        "task": task, "request": request, "ticket": claim.ticket,
        "preflight": preflight.result, "owner_id": inputs["owner_id"],
        "object_store": inputs["object_store"], "settings": settings, "controls": controls,
        "adapter": spy, "approval": approval, "capability": inputs["capability"],
        "approval_manifest_path": inputs["approval_manifest_path"], "now": inputs["now"],
    }
    async with factory() as session:
        if outcome == "limited":
            await text_reserve(session, task.user_id, settings, 1, "creative-pending-text")
        if outcome in {"missing_price", "reference_price", "limited"}:
            with pytest.raises(CreativeProviderExecutionRejected):
                await execute_creative_image(session, **kwargs)
            assert spy.submissions == spy.uploads == 0
            assert await session.scalar(select(func.count()).select_from(
                AIUsageReservation,
            ).where(AIUsageReservation.operation_type == IMAGE_OPERATION)) == 0
            return
        result = await execute_creative_image(session, **kwargs)
        assert result.status == (
            "UNKNOWN" if outcome in {"timeout", "invalid_response"} else
            "FAILED" if outcome == "not_submitted" else "SUBMITTED"
        )
        reservation = await session.scalar(select(AIUsageReservation).where(
            AIUsageReservation.operation_type == IMAGE_OPERATION,
        ))
        assert reservation.task_id is None
        assert reservation.user_id == task.user_id
        assert reservation.idempotency_key == f"creative-image:{claim.ticket.ticket_id}"
        assert reservation.status == (
            AIUsageReservationStatus.SETTLED if outcome == "priced_usage" else
            AIUsageReservationStatus.RELEASED if outcome == "not_submitted" else
            AIUsageReservationStatus.RESERVED if outcome == "missing_usage" else
            AIUsageReservationStatus.UNKNOWN
        )
        assert reservation.actual_cost_microusd == (
            100 if outcome == "priced_usage" else 0 if outcome == "not_submitted" else None
        )
        with pytest.raises(CreativeProviderExecutionRejected):
            await execute_creative_image(session, **kwargs)
        assert spy.submissions == 1


async def test_creative_ready_ticket_cannot_repeat_unknown_usd_claim(
    workflow, tmp_path,
):
    from libtv_agent.creative.workflow import digest
    from libtv_agent.services.creative_provider_executor import (
        CreativeExecutionControls,
        CreativeProviderExecutionRejected,
        execute_creative_image,
    )
    from test_creative_provider_executor import _prepared_ticket

    flow, task, request, approval, inputs, preflight, claim = await _prepared_ticket(
        workflow, tmp_path,
    )
    settings = inputs["settings"].model_copy(update={
        "ai_price_catalog_json": json.dumps({"version": "v1", "prices": [{
            "provider": "wavespeed", "model": request.model, "unit": "image",
            "rate_microusd": 100, "quantity": 1, "effective_at": "2026-01-01T00:00:00Z",
            "source": "test", "version": "v1", "reference_only": False,
            "all_parameters_upper_bound": True,
        }]}),
    })
    budget = MediaUsageRequest(
        task.user_id, IMAGE_OPERATION, f"creative-image:{claim.ticket.ticket_id}",
        "wavespeed", request.model, "image", 1,
        digest({
            "ticketId": claim.ticket.ticket_id, "requestHash": request.request_hash,
            "owner": str(task.user_id), "imageCount": 1,
        }),
    )
    factory = flow.app.state.database.session_factory
    async with factory() as session:
        reservation = (await reserve_media_batch(session, settings, [budget]))[0]
        await claim_media_submission(session, budget)
        await finish_media_usage(session, reservation)
        await session.commit()
    # Recovery may mark the USD claim UNKNOWN while the ticket is still READY.
    spy = ImageSpy()
    async with factory() as session:
        with pytest.raises(CreativeProviderExecutionRejected) as caught:
            await execute_creative_image(
                session, task=task, request=request, ticket=claim.ticket,
                preflight=preflight.result, owner_id=inputs["owner_id"],
                object_store=inputs["object_store"], settings=settings,
                controls=CreativeExecutionControls(
                    mode="live", admin_live_enabled=True, human_confirmed=True,
                ),
                adapter=spy, approval=approval, capability=inputs["capability"],
                approval_manifest_path=inputs["approval_manifest_path"], now=inputs["now"],
            )
        assert caught.value.code == "MEDIA_SUBMISSION_ALREADY_CLAIMED"
        assert spy.uploads == spy.submissions == 0
