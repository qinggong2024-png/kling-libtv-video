"""Isolated PostgreSQL acceptance on schemas created only by Alembic."""

import asyncio
import json
import os
import socket
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_backend_readiness_repair as repair_tests
import test_g1_cancel_race as cancel_tests
import test_g1_claim_fence as claim_tests
import test_g1_launch_race as launch_tests
from alembic import command as alembic_command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import (
    AIUsageReservationStatus,
    AttemptStatus,
    CommandStatus,
    ReservationStatus,
)
from libtv_agent.domain.models import (
    AIUsageReservation,
    AuditEvent,
    CapacitySlot,
    CreativeTask,
    GenerationAttempt,
    GenerationCommand,
    ImageGenerationOutput,
    ParentTask,
    PointsReservation,
)
from libtv_agent.runner.supervisor import RunnerSupervisor
from libtv_agent.services.ai_pricing import PriceEntry
from libtv_agent.services.database_schema import inspect_database_schema
from libtv_agent.services.media_ai_usage import reserve_video_attempts
from libtv_agent.services.runtime_control import get_runtime_config, update_runtime_config
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_backend_readiness_repair import (
    VideoExecutorDouble,
    create_video,
    install_preparation_double,
    planned,
    qualified_image,
)
from test_image_generation_batches import FakeWaveSpeedAdapter
from test_launch_started_recovery import _stranded_command

test_qualification_boundaries = repair_tests.test_rejected_source_blocks_video_at_every_boundary
test_analysis_recovery = (
    repair_tests.test_analysis_failure_recovers_same_product_workflow_and_creation_key
)
test_package_lineage = repair_tests.test_package_reaches_existing_executors_and_video_lineage
test_package_ownership = repair_tests.test_package_binding_rejects_tampering_and_foreign_owner
test_review_delivery = (
    repair_tests.test_review_queue_ignores_parent_phase_and_approval_retains_quality_gate
)
test_stale_worker = claim_tests.test_old_worker_after_localization_cannot_submit_or_settle
test_claim_owner_fence = claim_tests.test_prelaunch_fence_checks_persisted_claim
test_expired_claim = claim_tests.test_expired_claim_recovers_once_and_fences_old_snapshot
test_launch_recovery_race = launch_tests.test_launch_progress_after_recovery_scan_is_not_overwritten
test_cancel_race = cancel_tests.test_cancel_cannot_overwrite_advanced_task


@pytest.fixture(autouse=True)
def isolate_network(monkeypatch):
    original = socket.socket.connect
    original_pair = socket.socketpair
    creating_pair = False

    def socketpair(*args, **kwargs):
        nonlocal creating_pair
        creating_pair = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            creating_pair = False

    def connect(sock, address):
        if isinstance(address, tuple):
            host, port = address[:2]
            assert host == "127.0.0.1" and (
                port == 15439 or creating_pair
            ), "external connection prohibited"
        return original(sock, address)

    monkeypatch.setattr(socket, "socketpair", socketpair)
    monkeypatch.setattr(socket.socket, "connect", connect)


@pytest.fixture
async def backend(tmp_path, monkeypatch):
    url = os.environ.get("G1_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("requires isolated PostgreSQL at 127.0.0.1:15439/g1_safety")
    parsed = make_url(url)
    assert (parsed.host, parsed.port, parsed.database) == ("127.0.0.1", 15439, "g1_safety")
    schema = "acceptance_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url,
        connect_args={"server_settings": {
            "search_path": schema,
            "statement_timeout": "10000",
            "lock_timeout": "5000",
        }},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=url,
        libtv_adapter_mode="fake",
        director_workflow_mode="live_director",
        object_store_mode="local",
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        wavespeed_enabled=True,
        wavespeed_api_key="synthetic-test-only",
        kling_api_enabled=False,
        global_paused=False,
        paid_submissions_paused=False,
        ai_price_catalog_json=json.dumps({"version": "pg-acceptance", "prices": [
            {
                "provider": provider, "model": model, "unit": unit,
                "rate_microusd": 100, "quantity": 1,
                "effective_at": "2026-01-01T00:00:00Z",
                "source": "synthetic acceptance fixture", "version": "pg-acceptance",
                "reference_only": False,
                **({"all_parameters_upper_bound": True}
                   if "all_parameters_upper_bound" in PriceEntry.model_fields else {}),
            }
            for provider, model, unit in (
                ("wavespeed", "openai/gpt-image-2/edit", "image"),
                ("kling_official_api", "test-video", "video_second"),
            )
        ]}),
    )
    settings.runner_root.mkdir(parents=True)
    database = SimpleNamespace(engine=engine, session_factory=factory, dispose=engine.dispose)
    monkeypatch.setattr("libtv_agent.app.Database", lambda _: database)
    try:
        async with engine.begin() as connection:
            assert connection.dialect.name == "postgresql"
            def migrate(sync_connection):
                config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
                config.attributes["connection"] = sync_connection
                alembic_command.upgrade(config, "head")
                status = inspect_database_schema(sync_connection)
                assert status.ready
                assert status.current_revisions == status.expected_revisions
            await connection.run_sync(migrate)
        app = create_app(settings)
        app.state.wavespeed_adapter = FakeWaveSpeedAdapter()
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                headers = {"X-User-Id": settings.dev_user_id}
                response = await client.get("/api/v1/tasks", headers=headers)
                assert response.status_code == 200, response.text
                async with factory() as session:
                    current = await get_runtime_config(session, settings)
                    await update_runtime_config(
                        session, settings, config={
                            **current.config_json, "internalPilotEnabled": True,
                            "pilotUserIds": [settings.dev_user_id], "pilotBudgetLimit": 100,
                            "generationConcurrency": {
                                **current.config_json["generationConcurrency"],
                                "global": 2, "perUser": 2, "sameProject": 2,
                            },
                        }, actor_id=None, reason="isolated PostgreSQL acceptance",
                        expected_version=current.version,
                    )
                    await session.commit()
                yield client, app, settings, headers
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.fixture
async def world(backend):
    _, app, settings, _ = backend
    return app, app.state.database.session_factory, app.state.wavespeed_adapter, [
        uuid.UUID(settings.dev_user_id), uuid.UUID(settings.dev_admin_id),
    ]


def authorize_test_double(monkeypatch, settings):
    monkeypatch.setattr(
        "libtv_agent.runner.supervisor.real_provider_submission_authorized", lambda _: True,
    )
    monkeypatch.setattr(
        "libtv_agent.services.runtime_control.real_provider_submission_authorized", lambda _: True,
    )
    monkeypatch.setattr(type(settings), "kling_provider_submission_enabled", lambda *_: True)


@pytest.mark.parametrize("command_count", [1, 2])
async def test_two_workers_claim_and_submit_each_command_once(
    backend, tmp_path, monkeypatch, command_count,
):
    _, app, settings, _ = backend
    factory = app.state.database.session_factory
    command_ids = set()
    async with factory() as session:
        for _ in range(command_count):
            task, variant, attempt, command, _ = await _stranded_command(
                session, provider="kling_official_api", lease_expires_at=None,
            )
            command.status = CommandStatus.READY
            attempt.status = AttemptStatus.DISPATCH_PENDING
            attempt.provider_model = "test-video"
            variant.generation_config_json = {"duration": 10}
            await reserve_video_attempts(session, settings, task, [attempt])
            command_ids.add(command.id)
        await session.commit()
    authorize_test_double(monkeypatch, settings)
    first_submitted = asyncio.Event()
    both_submitted = asyncio.Event()
    release = asyncio.Event()
    owners = set()
    seen_commands = []

    class Executor(VideoExecutorDouble):
        def __init__(self, owner):
            super().__init__()
            self.owner = owner

        async def submit(self, request):
            async with factory() as verify:
                commands = list(await verify.scalars(
                    select(GenerationCommand).where(
                        GenerationCommand.claim_owner == self.owner,
                        GenerationCommand.status == CommandStatus.LAUNCH_STARTED,
                    )
                ))
                assert len(commands) == 1
                command = commands[0]
                assert command.id in command_ids
                attempt = await verify.get(GenerationAttempt, command.attempt_id)
                assert attempt.status == AttemptStatus.LAUNCHING
                occupied = await verify.scalar(select(func.count()).select_from(CapacitySlot).where(
                    CapacitySlot.command_id == command.id,
                ))
                assert occupied == 3
                seen_commands.append(command.id)
                owners.add(self.owner)
                first_submitted.set()
            if len(seen_commands) == 2:
                both_submitted.set()
            await asyncio.wait_for(release.wait(), 10)
            result = await super().submit(request)
            result.provider_task_id = "synthetic-" + self.owner
            return result

    workers = []
    for index in range(2):
        worker = RunnerSupervisor(
            app.state.libtv_adapter, app.state.object_store, settings,
            kling_adapter=Executor(f"worker-{index}"),
        )
        worker.owner = f"worker-{index}"
        workers.append(worker)

    async def run(worker):
        async with factory() as session:
            return await worker._run_ready_provider(session, "kling")

    runs = [asyncio.create_task(run(workers[0]))]
    try:
        await asyncio.wait_for(first_submitted.wait(), 8)
        runs.append(asyncio.create_task(run(workers[1])))
        if command_count == 2:
            await asyncio.wait_for(both_submitted.wait(), 8)
        else:
            assert await asyncio.wait_for(asyncio.shield(runs[1]), 3) == 0
    finally:
        release.set()
        results = await asyncio.gather(*runs, return_exceptions=True)
    assert results == ([1, 1] if command_count == 2 else [1, 0]), results
    assert len(owners) == command_count
    assert len(seen_commands) == command_count and set(seen_commands) == command_ids
    async with factory() as verify:
        commands = list(await verify.scalars(select(GenerationCommand)))
        assert all(command.status == CommandStatus.PROCESS_STARTED for command in commands)
        assert await verify.scalar(select(func.count()).select_from(CapacitySlot).where(
            CapacitySlot.command_id.is_not(None),
        )) == 0
        reservations = list(await verify.scalars(select(PointsReservation)))
        assert len(reservations) == command_count
        assert all(reservation.status == ReservationStatus.RESERVED for reservation in reservations)


async def test_revocation_commits_while_worker_materializes(backend, monkeypatch):
    client, app, settings, headers = backend
    context, _, _ = await planned(backend)
    output_id, upload_id = await qualified_image(backend, context)
    install_preparation_double(monkeypatch)
    created = await create_video(backend, context, upload_id)
    assert created.status_code == 201, created.text
    executor = VideoExecutorDouble()
    supervisor = RunnerSupervisor(
        app.state.libtv_adapter, app.state.object_store, settings, kling_adapter=executor,
    )
    authorize_test_double(monkeypatch, settings)
    localizing = asyncio.Event()
    resume = asyncio.Event()
    original = app.state.object_store.localize

    async def materialize(*args, **kwargs):
        localizing.set()
        await asyncio.wait_for(resume.wait(), 8)
        return await original(*args, **kwargs)

    monkeypatch.setattr(app.state.object_store, "localize", materialize)
    factory = app.state.database.session_factory

    async def execute():
        async with factory() as session:
            command = await session.scalar(select(GenerationCommand))
            result = await supervisor._execute(session, command.id)
            attempt = await session.get(GenerationAttempt, command.attempt_id)
            assert result is True
            assert attempt.status == AttemptStatus.FAILED_BEFORE_SUBMIT
            assert attempt.last_error_code == "SOURCE_IMAGE_NOT_QUALIFIED"

    running = asyncio.create_task(execute())
    try:
        await asyncio.wait_for(localizing.wait(), 8)
        response = await asyncio.wait_for(client.put(
            f"/api/v1/image-generation-outputs/{output_id}/quality-decision", headers=headers,
            json={
                "decision": "REJECTED", "productFidelityPass": False,
                "humanCriticalPass": True, "humanReviewSeconds": 5,
                "notes": "synthetic concurrent qualification revocation",
            },
        ), 3)
        assert response.status_code == 200, response.text
    finally:
        resume.set()
        await running
    assert executor.requests == []


@pytest.mark.parametrize("revocation", ["qualification", "lineage", "package"])
async def test_revocation_after_budget_commit_blocks_provider_submit(
    backend, monkeypatch, revocation,
):
    client, app, settings, headers = backend
    context, _, _ = await planned(backend)
    output_id, upload_id = await qualified_image(backend, context)
    install_preparation_double(monkeypatch)
    created = await create_video(backend, context, upload_id)
    assert created.status_code == 201, created.text
    executor = VideoExecutorDouble()
    supervisor = RunnerSupervisor(
        app.state.libtv_adapter, app.state.object_store, settings, kling_adapter=executor,
    )
    authorize_test_double(monkeypatch, settings)
    original = supervisor._claim_video_budget
    reason = {
        "qualification": "SOURCE_IMAGE_NOT_QUALIFIED",
        "lineage": "SOURCE_IMAGE_CHANGED",
        "package": "CREATIVE_WORKFLOW_BLOCKED",
    }[revocation]

    async def claim_then_revoke(*args, **kwargs):
        allowed = await original(*args, **kwargs)
        assert allowed is True
        if revocation == "qualification":
            response = await asyncio.wait_for(client.put(
                f"/api/v1/image-generation-outputs/{output_id}/quality-decision", headers=headers,
                json={
                    "decision": "REJECTED", "productFidelityPass": False,
                    "humanCriticalPass": True, "humanReviewSeconds": 5,
                    "notes": "revoked after budget commit and before provider submission",
                },
            ), 3)
            assert response.status_code == 200, response.text
        else:
            async with app.state.database.session_factory() as writer:
                if revocation == "lineage":
                    output = await writer.get(ImageGenerationOutput, uuid.UUID(output_id))
                    output.sha256 = "f" * 64
                else:
                    workflow = await writer.get(CreativeTask, uuid.UUID(context["workflowId"]))
                    workflow.snapshot_json = {**workflow.snapshot_json, "stopped": True}
                await writer.commit()
        return allowed

    monkeypatch.setattr(supervisor, "_claim_video_budget", claim_then_revoke)
    async with app.state.database.session_factory() as session:
        command = await session.scalar(select(GenerationCommand))
        assert await supervisor._execute(session, command.id) is True
        attempt = await session.get(GenerationAttempt, command.attempt_id)
        assert attempt.status == AttemptStatus.FAILED_BEFORE_SUBMIT
        assert attempt.last_error_code == reason
        task = await session.get(ParentTask, uuid.UUID(created.json()["id"]))
        assert task.phase_reason_code == reason
        assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "VIDEO_SOURCE_BLOCKED",
            AuditEvent.entity_id == str(task.id),
            AuditEvent.reason == reason,
        )) == 1
        budget = await session.scalar(select(AIUsageReservation).where(
            AIUsageReservation.idempotency_key == f"video:{attempt.id}",
        ))
        assert budget.status == AIUsageReservationStatus.RELEASED
        assert budget.actual_cost_status == "NOT_SUBMITTED"
    assert executor.requests == [], "revoked source reached the provider after budget commit"


async def test_active_image_recovery_query_is_postgresql_compatible(backend):
    from libtv_agent.services.image_generations import refresh_active_batches

    _, app, _, _ = backend
    async with app.state.database.session_factory() as session:
        assert await refresh_active_batches(session, app=app) == 0


async def test_active_batches_are_unique_and_limit_applies_to_batches(backend, monkeypatch):
    from libtv_agent.domain.models import ImageGenerationBatch, ImageGenerationItem
    from libtv_agent.services import image_generations
    from libtv_agent.services.image_generations import ImageItemSpec, create_batch_record

    _, app, settings, _ = backend
    factory = app.state.database.session_factory
    async with factory() as seed:
        batches = []
        for index, provider in enumerate(["gpt", "gpt", "fake", "gpt"]):
            batch = create_batch_record(
                user_id=uuid.UUID(settings.dev_user_id),
                idempotency_key=f"active-{index}",
                request_hash=str(index) * 64,
                manifest={
                    "clientBatchId": f"active-{index}", "name": "active batch",
                    "provider": provider, "expectedGenerationCount": 2,
                    "paidSubmissionConsent": True,
                },
                item_specs=[
                    ImageItemSpec(
                        client_task_id=f"item-{number}", outfit_id="test", outfit_name="test",
                        sku="", kind="fusion", view="front", label="test",
                        prompt="preserve garment", reference_file_indexes=(),
                    )
                    for number in range(2)
                ],
            )
            seed.add(batch)
            await seed.flush()
            for item in batch.items:
                item.status = "PROCESSING" if index != 3 else "COMPLETED"
                item.provider_task_id = "synthetic-prediction"
            batches.append(batch.id)
        await seed.commit()
    seen = []

    async def record_refresh(session, *, app, batch):
        seen.append(batch.id)

    monkeypatch.setattr(image_generations, "refresh_batch", record_refresh)
    async with factory() as session:
        assert await image_generations.refresh_active_batches(session, app=app, limit=1) == 1
        assert seen == [batches[0]]
        seen.clear()
        assert await image_generations.refresh_active_batches(session, app=app, limit=10) == 2
        assert seen == batches[:2]
        assert await session.scalar(select(func.count()).select_from(ImageGenerationBatch)) == 4
        assert await session.scalar(select(func.count()).select_from(ImageGenerationItem)) == 8
