import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from libtv_agent.config import Settings
from libtv_agent.domain.enums import (
    AttemptStatus,
    CommandStatus,
    ConsistencyLevel,
    DownloadStatus,
    ParentTaskPhase,
    ReservationStatus,
    SagaStatus,
    VariantKind,
)
from libtv_agent.domain.models import (
    Asset,
    AuditEvent,
    Base,
    DownloadArtifact,
    GenerationAttempt,
    GenerationCommand,
    GenerationReferenceAsset,
    GenerationVariant,
    MaterializationSaga,
    OperationalMetricSample,
    ParentTask,
    PointsReservation,
    RunnerHost,
    TaskConfirmationVersion,
    User,
)
from libtv_agent.services.observability import (
    operations_snapshot,
    prune_operational_samples,
    record_operational_sample,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

COLLECTOR_PATH = Path(__file__).parents[2] / "scripts" / "collect_phase2_evidence.py"
COLLECTOR_SPEC = importlib.util.spec_from_file_location("phase2_collector", COLLECTOR_PATH)
assert COLLECTOR_SPEC is not None and COLLECTOR_SPEC.loader is not None
COLLECTOR_MODULE = importlib.util.module_from_spec(COLLECTOR_SPEC)
COLLECTOR_SPEC.loader.exec_module(COLLECTOR_MODULE)
collect = COLLECTOR_MODULE.collect
operational_series_evidence = COLLECTOR_MODULE.operational_series_evidence


def _sample(
    host_id: uuid.UUID,
    captured_at: datetime,
    *,
    backlog: int = 1,
    utilization: float = 1.0,
    orphans: int = 0,
    global_paused: bool = False,
    paid_paused: bool = False,
) -> OperationalMetricSample:
    return OperationalMetricSample(
        runner_host_id=host_id,
        deployment_id="test",
        libtv_adapter_mode="real",
        captured_at=captured_at,
        global_slots=1,
        backlog_count=backlog,
        running_count=round(utilization),
        slot_utilization=utilization,
        orphan_process_count=orphans,
        free_disk_percent=90.0,
        global_paused=global_paused,
        paid_submissions_paused=paid_paused,
    )


def test_operational_series_breaks_on_pause_and_large_gap_and_weights_backlog() -> None:
    host_id = uuid.uuid4()
    started = datetime(2026, 7, 27, 0, 0, tzinfo=UTC)
    samples = [
        _sample(host_id, started, utilization=0.5),
        _sample(host_id, started + timedelta(seconds=10), utilization=1.0),
        _sample(host_id, started + timedelta(seconds=20), paid_paused=True),
        _sample(host_id, started + timedelta(seconds=30), utilization=0.25),
        _sample(host_id, started + timedelta(seconds=100), utilization=1.0),
        _sample(host_id, started + timedelta(seconds=110), backlog=0, utilization=0.75),
    ]

    result = operational_series_evidence(samples, max_gap_seconds=30)

    assert result["continuousRunHours"] == pytest.approx(10 / 3600)
    assert result["backloggedSlotUtilization"] == pytest.approx(0.75)
    assert result["evidence"]["backlogIntervalCount"] == 2
    assert result["evidence"]["sampleCount"] == 6


@pytest.mark.asyncio
async def test_operational_sample_records_runtime_and_runner_state(tmp_path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(object_store_mode="local", runner_root=tmp_path, _env_file=None)
    async with factory() as session:
        host = RunnerHost(
            hostname="runner-one",
            os_version="Windows test",
            service_version="test",
            service_instance_id="runner-one-instance",
        )
        session.add(host)
        await session.flush()
        sample = await record_operational_sample(
            session,
            settings,
            host,
            backlog_count=3,
            orphan_process_count=2,
            free_disk_percent=81.5,
        )
        await session.commit()

    assert sample.runner_host_id == host.id
    assert sample.deployment_id == settings.deployment_id
    assert sample.libtv_adapter_mode == settings.libtv_adapter_mode
    assert sample.global_slots == settings.generation_global
    assert sample.backlog_count == 3
    assert sample.orphan_process_count == 2
    assert sample.free_disk_percent == 81.5
    assert sample.paid_submissions_paused is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_operational_sample_retention_removes_only_expired_rows(tmp_path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session:
        host = RunnerHost(
            hostname="runner-retention",
            os_version="Windows test",
            service_version="test",
            service_instance_id="runner-retention-instance",
        )
        session.add(host)
        await session.flush()
        session.add_all(
            [
                _sample(host.id, now - timedelta(days=31)),
                _sample(host.id, now - timedelta(days=1)),
            ]
        )
        await session.commit()

        assert await prune_operational_samples(session, retention_days=30) == 1
        await session.commit()
        remaining = int(
            await session.scalar(select(func.count()).select_from(OperationalMetricSample)) or 0
        )
        assert remaining == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_hard_metrics_are_calculated_from_database_and_process_evidence(
    tmp_path: Path,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid.uuid4()
    first_task_id = uuid.uuid4()
    second_task_id = uuid.uuid4()
    foreign_asset_id = uuid.uuid4()
    variant_id = uuid.uuid4()
    now = datetime.now(UTC)
    async with factory() as session:
        session.add(User(id=user_id, username="metrics", password_hash="disabled"))
        host = RunnerHost(
            hostname="metrics-runner",
            os_version="Windows test",
            service_version="test",
            service_instance_id="metrics-runner-instance",
        )
        session.add(host)
        await session.flush()
        session.add(_sample(host.id, now, backlog=0, orphans=2))
        session.add_all(
            [
                ParentTask(
                    id=first_task_id,
                    user_id=user_id,
                    client_task_id="metrics-1",
                    title="first",
                    asset_count=1,
                ),
                ParentTask(
                    id=second_task_id,
                    user_id=user_id,
                    client_task_id="metrics-2",
                    title="second",
                    asset_count=1,
                ),
            ]
        )
        session.add(
            Asset(
                id=foreign_asset_id,
                parent_task_id=second_task_id,
                order_no=1,
                original_filename="asset.jpg",
                sha256="a" * 64,
                mime_type="image/jpeg",
                width=720,
                height=1280,
            )
        )
        session.add(
            GenerationVariant(
                id=variant_id,
                parent_task_id=first_task_id,
                variant_type=VariantKind.STABLE,
                generation_config_json={},
            )
        )
        session.add_all(
            [
                GenerationAttempt(
                    variant_id=variant_id,
                    intent_hash="duplicate-intent",
                    status=AttemptStatus.FAILED_TERMINAL,
                    launch_started_at=now,
                ),
                GenerationAttempt(
                    variant_id=variant_id,
                    intent_hash="duplicate-intent",
                    status=AttemptStatus.FAILED_TERMINAL,
                    launch_started_at=now,
                ),
            ]
        )
        session.add(
            GenerationReferenceAsset(
                generation_variant_id=variant_id,
                asset_id=foreign_asset_id,
                order_no=1,
                remote_node_key="foreign-image-node",
            )
        )
        await session.commit()

        snapshot = await operations_snapshot(
            session,
            Settings(
                object_store_mode="local",
                runner_root=tmp_path / "runner",
                _env_file=None,
            ),
        )

    assert snapshot["metrics"]["duplicateGenerationTotal"] == 1
    assert snapshot["metrics"]["crossTaskConnectionTotal"] == 1
    assert snapshot["metrics"]["runnerOrphanProcesses"] == 2
    assert snapshot["metricEvidence"]["runnerOrphanProcesses"]["processIds"] == []
    assert any(
        alert["code"] == "DATA_INTEGRITY_ASSET_CONTAMINATION" and alert["severity"] == "CRITICAL"
        for alert in snapshot["alerts"]
    )
    await engine.dispose()


@pytest.mark.asyncio
async def test_pilot_monitoring_exposes_review_queue_measurement_gap_and_critical_integrity_alert(
    tmp_path: Path,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        settings = Settings(
            object_store_mode="local",
            runner_root=tmp_path / "runner",
            deployment_source_revision="pilot-source",
            _env_file=None,
        )
        snapshot = await operations_snapshot(session, settings)
        assert snapshot["humanReviewQueue"] == {
            "productFidelity": 0,
            "humanCritical": 0,
            "finalApproval": 0,
            "total": 0,
        }
        assert snapshot["businessBaseline"]["measurementStatus"] == "MEASUREMENT_GAP"
        assert "generation_attempts" in snapshot["businessBaseline"]["measurementGaps"]
        assert snapshot["runtimeRevisions"]["drift"] is False
        assert {item["severity"] for item in snapshot["alerts"]} <= {
            "INFO",
            "ACTION_REQUIRED",
            "CRITICAL",
        }
    await engine.dispose()


@pytest.mark.asyncio
async def test_operational_metric_units_and_windows_are_explicit(tmp_path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session:
        user = User(id=uuid.uuid4(), username="metric-contract", password_hash="disabled")
        task = ParentTask(
            id=uuid.uuid4(),
            user_id=user.id, client_task_id="metric-contract", title="metrics", asset_count=1
        )
        variant = GenerationVariant(
            parent_task_id=task.id,
            variant_type=VariantKind.STABLE,
            generation_config_json={},
        )
        session.add(user)
        await session.flush()
        session.add(task)
        await session.flush()
        session.add(variant)
        await session.flush()
        attempt = GenerationAttempt(
            variant_id=variant.id,
            status=AttemptStatus.UNKNOWN_AFTER_SUBMIT,
            launch_started_at=now - timedelta(days=1),
            submitted_at=now - timedelta(days=1),
            runner_host_id=None,
        )
        session.add(attempt)
        await session.flush()
        session.add(
            PointsReservation(
                user_id=user.id,
                attempt_id=attempt.id,
                estimated_points=240,
                status=ReservationStatus.RESERVED,
                business_date=now.date(),
            )
        )
        await session.commit()
        snapshot = await operations_snapshot(
            session,
            Settings(object_store_mode="local", runner_root=tmp_path / "runner", _env_file=None),
        )
    assert snapshot["metrics"]["unknownAfterSubmitRate"] == 1.0
    assert snapshot["metrics"]["unknownAfterSubmitWindowDays"] == 7
    assert snapshot["metrics"]["pointsReserved"] == 1
    assert snapshot["metricEvidence"]["pointsReserved"]["unit"] == "generation_reservations"
    await engine.dispose()


@pytest.mark.asyncio
async def test_video_quota_rejections_are_published_separately(tmp_path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        now = datetime.now(UTC)
        session.add_all(
            [
                AuditEvent(
                    action="VIDEO_QUOTA_REJECTED",
                    entity_type="PARENT_TASK",
                    entity_id=str(uuid.uuid4()),
                    reason="daily video quota exceeded",
                    correlation_id=str(uuid.uuid4()),
                    evidence_refs_json=[],
                    created_at=now,
                ),
                AuditEvent(
                    action="IMAGE_QUOTA_REJECTED",
                    entity_type="IMAGE_GENERATION_BATCH",
                    entity_id=str(uuid.uuid4()),
                    reason="daily image quota exceeded",
                    correlation_id=str(uuid.uuid4()),
                    evidence_refs_json=[],
                    created_at=now,
                ),
            ]
        )
        await session.commit()
        snapshot = await operations_snapshot(
            session,
            Settings(object_store_mode="local", runner_root=tmp_path / "runner", _env_file=None),
        )
    assert snapshot["metrics"]["videoQuotaRejectionCount"] == 1
    assert snapshot["metrics"]["imageQuotaRejectionCount"] == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_pilot_runtime_lock_drift_is_critical_and_blocks_paid_path(tmp_path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        from libtv_agent.domain.models import RuntimeConfigVersion

        settings = Settings(
            object_store_mode="local",
            runner_root=tmp_path / "runner",
            deployment_source_revision="current-source",
            _env_file=None,
        )
        session.add(
            RuntimeConfigVersion(
                version=1,
                config_json={
                    "globalPaused": False,
                    "paidSubmissionsPaused": False,
                    "pilotRuntimeLock": {"sourceRevision": "locked-source"},
                },
                change_reason="test",
            )
        )
        await session.commit()
        snapshot = await operations_snapshot(session, settings)
        assert snapshot["runtimeRevisions"]["drift"] is True
        assert any(
            alert["code"] == "PILOT_BLOCKED_RUNTIME_DRIFT" and alert["severity"] == "CRITICAL"
            for alert in snapshot["alerts"]
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_pipeline_performance_reports_stage_latency_and_current_constraint(
    tmp_path: Path,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    variant_id = uuid.uuid4()
    attempt_id = uuid.uuid4()
    now = datetime.now(UTC)
    async with factory() as session:
        session.add(User(id=user_id, username="pipeline", password_hash="disabled"))
        session.add(
            ParentTask(
                id=task_id,
                user_id=user_id,
                client_task_id="pipeline-1",
                title="pipeline metrics",
                asset_count=1,
                phase=ParentTaskPhase.DELIVERABLE,
                analysis_stage="COMPLETED",
                analysis_started_at=now - timedelta(minutes=12),
                analysis_heartbeat_at=now - timedelta(minutes=10),
                created_at=now - timedelta(minutes=13),
            )
        )
        session.add(
            GenerationVariant(
                id=variant_id,
                parent_task_id=task_id,
                variant_type=VariantKind.STABLE,
                generation_config_json={},
                download_status=DownloadStatus.READY,
            )
        )
        session.add(
            GenerationAttempt(
                id=attempt_id,
                variant_id=variant_id,
                status=AttemptStatus.SUCCEEDED,
                process_started_at=now - timedelta(minutes=7),
                completed_at=now - timedelta(minutes=2),
                created_at=now - timedelta(minutes=9),
            )
        )
        session.add_all(
            [
                GenerationCommand(
                    attempt_id=attempt_id,
                    status=CommandStatus.TERMINAL,
                    created_at=now - timedelta(minutes=8),
                    process_started_at=now - timedelta(minutes=7),
                ),
                MaterializationSaga(
                    parent_task_id=task_id,
                    project_uuid="project-pipeline",
                    status=SagaStatus.VERIFIED,
                    created_at=now - timedelta(minutes=10),
                    updated_at=now - timedelta(minutes=8),
                ),
                TaskConfirmationVersion(
                    parent_task_id=task_id,
                    revision=1,
                    analysis_result_hash="a" * 64,
                    stable_prompt_hash="b" * 64,
                    dynamic_prompt_hash="c" * 64,
                    ordered_storyboard_assets_hash="d" * 64,
                    generation_config_hash="e" * 64,
                    confirmed_by=user_id,
                    confirmed_at=now - timedelta(minutes=9),
                ),
                DownloadArtifact(
                    attempt_id=attempt_id,
                    status=DownloadStatus.READY,
                    object_key="outputs/pipeline.mp4",
                    created_at=now,
                ),
            ]
        )
        await session.commit()
        snapshot = await operations_snapshot(
            session,
            Settings(object_store_mode="local", runner_root=tmp_path / "runner", _env_file=None),
        )

    performance = snapshot["pipelinePerformance"]
    assert performance["throughput"] == {
        "completedVideos24h": 1,
        "completedTasks24h": 1,
    }
    assert performance["stages"]["analysis"]["p50Seconds"] == 120.0
    assert performance["stages"]["materialization"]["p95Seconds"] == 120.0
    assert performance["stages"]["queue"]["p50Seconds"] == 60.0
    assert performance["stages"]["generation"]["p50Seconds"] == 300.0
    assert performance["stages"]["delivery"]["p50Seconds"] == 120.0
    assert performance["stages"]["endToEnd"]["p50Seconds"] == 780.0
    assert performance["automationBottleneck"] == "generation"
    assert performance["currentConstraint"] == "IDLE"
    await engine.dispose()


@pytest.mark.asyncio
async def test_phase2_collector_marks_real_scope_and_uses_database_zeroes(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "evidence.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    report = await collect(
        Settings(
            database_url=database_url,
            libtv_adapter_mode="real",
            ai_adapter_mode="openai",
            object_store_mode="local",
            runner_root=tmp_path / "runner",
            _env_file=None,
        )
    )

    assert report["status"] == "COLLECTED"
    assert report["scope"]["realEvidenceEligible"] is True
    assert report["realConsumption"]["openAiRequests"] == 0
    assert report["realConsumption"]["libtvNodeRuns"] == 0
    assert report["controlledMvp"]["continuousRunHours"] is None


@pytest.mark.asyncio
async def test_phase2_collector_calculates_low_risk_auto_completion_cohort(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "low-risk.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid.uuid4()
    async with factory() as session:
        session.add(User(id=user_id, username="low-risk", password_hash="disabled"))
        for index, phase in enumerate(
            [ParentTaskPhase.DELIVERABLE, ParentTaskPhase.ACTION_REQUIRED], start=1
        ):
            task = ParentTask(
                user_id=user_id,
                client_task_id=f"auto-{index}",
                title=f"auto {index}",
                asset_count=1,
                phase=phase,
                consistency_level=ConsistencyLevel.PASS,
            )
            variant = GenerationVariant(
                parent_task=task,
                variant_type=VariantKind.STABLE,
                generation_config_json={},
            )
            variant.attempts.append(
                GenerationAttempt(
                    status=AttemptStatus.SUCCEEDED,
                    launch_started_at=datetime.now(UTC),
                    runner_execution_backend="WINDOWS_COMMAND_HOST",
                )
            )
            session.add(task)
            await session.flush()
            session.add(
                AuditEvent(
                    actor_id=user_id,
                    action="AUTO_CONFIRM_TASK",
                    entity_type="parent_task",
                    entity_id=str(task.id),
                    correlation_id=f"auto-{index}",
                )
            )
        await session.commit()
    await engine.dispose()
    report = await collect(
        Settings(
            database_url=database_url,
            libtv_adapter_mode="real",
            object_store_mode="local",
            runner_root=tmp_path / "runner",
            _env_file=None,
        )
    )

    assert report["acceptanceMetrics"]["lowRiskAutoCompletionRate"] == 0.5
    evidence = report["metricEvidence"]["lowRiskAutoCompletionRate"]
    assert evidence["eligibleParentTaskCount"] == 2
    assert evidence["autoConfirmedDeliverableParentTaskCount"] == 1
