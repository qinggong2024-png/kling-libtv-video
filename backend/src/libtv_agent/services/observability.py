from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from libtv_agent.config import Settings
from libtv_agent.domain.enums import (
    AttemptStatus,
    ChargeStatus,
    CommandStatus,
    DownloadStatus,
    ParentTaskPhase,
    ReservationStatus,
    SagaStatus,
)
from libtv_agent.domain.models import (
    Asset,
    AuditEvent,
    CanvasProject,
    DownloadArtifact,
    GenerationAttempt,
    GenerationCommand,
    GenerationFeedback,
    GenerationReferenceAsset,
    GenerationVariant,
    ImageGenerationOutput,
    MaterializationSaga,
    OperationalMetricSample,
    ParentTask,
    PointsReservation,
    RunnerHost,
    TaskConfirmationVersion,
)
from libtv_agent.services.runtime_control import get_runtime_config
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

INTEGRITY_METRIC_CACHE_SECONDS = 60.0
_integrity_metric_cache: dict[object, tuple[float, int, int]] = {}


def _normalized_timestamp(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _elapsed_seconds(started_at: datetime | None, completed_at: datetime | None) -> float | None:
    if started_at is None or completed_at is None:
        return None
    elapsed = (
        _normalized_timestamp(completed_at) - _normalized_timestamp(started_at)
    ).total_seconds()
    return elapsed if elapsed >= 0 else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 1)


def _stage_summary(values: list[float]) -> dict[str, float | int | None]:
    return {
        "sampleCount": len(values),
        "p50Seconds": _percentile(values, 0.50),
        "p95Seconds": _percentile(values, 0.95),
    }


async def _pipeline_performance(session: AsyncSession) -> dict[str, Any]:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=7)
    day_cutoff = now - timedelta(hours=24)

    analysis_rows = list(
        await session.execute(
            select(ParentTask.analysis_started_at, ParentTask.analysis_heartbeat_at).where(
                ParentTask.analysis_started_at >= cutoff,
                ParentTask.analysis_heartbeat_at.is_not(None),
                ParentTask.analysis_stage.in_(["COMPLETED", "FAILED", "STALE_RECOVERED"]),
            )
        )
    )
    confirmation_rows = list(
        await session.execute(
            select(ParentTask.analysis_heartbeat_at, TaskConfirmationVersion.confirmed_at)
            .join(
                TaskConfirmationVersion,
                TaskConfirmationVersion.parent_task_id == ParentTask.id,
            )
            .where(
                TaskConfirmationVersion.confirmed_at >= cutoff,
                ParentTask.analysis_stage == "COMPLETED",
                ParentTask.analysis_heartbeat_at.is_not(None),
            )
        )
    )
    materialization_rows = list(
        await session.execute(
            select(MaterializationSaga.created_at, MaterializationSaga.updated_at).where(
                MaterializationSaga.updated_at >= cutoff,
                MaterializationSaga.status.in_(
                    [SagaStatus.VERIFIED, SagaStatus.MANUAL_REVIEW, SagaStatus.WRITE_UNCERTAIN]
                ),
            )
        )
    )
    queue_rows = list(
        await session.execute(
            select(GenerationCommand.created_at, GenerationCommand.process_started_at).where(
                GenerationCommand.created_at >= cutoff,
                GenerationCommand.process_started_at.is_not(None),
            )
        )
    )
    generation_rows = list(
        await session.execute(
            select(
                GenerationAttempt.submitted_at,
                GenerationAttempt.process_started_at,
                GenerationAttempt.completed_at,
            ).where(
                GenerationAttempt.completed_at >= cutoff,
                GenerationAttempt.completed_at.is_not(None),
            )
        )
    )
    delivery_rows = list(
        await session.execute(
            select(GenerationAttempt.completed_at, DownloadArtifact.created_at)
            .join(DownloadArtifact, DownloadArtifact.attempt_id == GenerationAttempt.id)
            .where(
                DownloadArtifact.created_at >= cutoff,
                DownloadArtifact.status == DownloadStatus.READY,
                GenerationAttempt.completed_at.is_not(None),
            )
        )
    )
    end_to_end_rows = list(
        await session.execute(
            select(ParentTask.id, ParentTask.created_at, DownloadArtifact.created_at)
            .join(GenerationVariant, GenerationVariant.parent_task_id == ParentTask.id)
            .join(GenerationAttempt, GenerationAttempt.variant_id == GenerationVariant.id)
            .join(DownloadArtifact, DownloadArtifact.attempt_id == GenerationAttempt.id)
            .where(
                ParentTask.phase == ParentTaskPhase.DELIVERABLE,
                DownloadArtifact.status == DownloadStatus.READY,
                DownloadArtifact.created_at >= cutoff,
            )
        )
    )

    stage_values = {
        "analysis": [
            elapsed
            for started, completed in analysis_rows
            if (elapsed := _elapsed_seconds(started, completed)) is not None
        ],
        "confirmation": [
            elapsed
            for started, completed in confirmation_rows
            if (elapsed := _elapsed_seconds(started, completed)) is not None
        ],
        "materialization": [
            elapsed
            for started, completed in materialization_rows
            if (elapsed := _elapsed_seconds(started, completed)) is not None
        ],
        "queue": [
            elapsed
            for started, completed in queue_rows
            if (elapsed := _elapsed_seconds(started, completed)) is not None
        ],
        "generation": [
            elapsed
            for submitted, process_started, completed in generation_rows
            if (elapsed := _elapsed_seconds(submitted or process_started, completed)) is not None
        ],
        "delivery": [
            elapsed
            for started, completed in delivery_rows
            if (elapsed := _elapsed_seconds(started, completed)) is not None
        ],
    }
    completed_by_task: dict[object, tuple[datetime, datetime]] = {}
    for task_id, created_at, artifact_created_at in end_to_end_rows:
        existing = completed_by_task.get(task_id)
        if existing is None or _normalized_timestamp(artifact_created_at) > _normalized_timestamp(
            existing[1]
        ):
            completed_by_task[task_id] = (created_at, artifact_created_at)
    stage_values["endToEnd"] = [
        elapsed
        for started, completed in completed_by_task.values()
        if (elapsed := _elapsed_seconds(started, completed)) is not None
    ]
    stages = {name: _stage_summary(values) for name, values in stage_values.items()}

    automation_candidates = {
        name: summary["p95Seconds"]
        for name, summary in stages.items()
        if name not in {"confirmation", "endToEnd"} and summary["p95Seconds"] is not None
    }
    automation_bottleneck = (
        max(automation_candidates, key=automation_candidates.get) if automation_candidates else None
    )
    completed_videos_24h = int(
        await session.scalar(
            select(func.count())
            .select_from(DownloadArtifact)
            .where(
                DownloadArtifact.status == DownloadStatus.READY,
                DownloadArtifact.created_at >= day_cutoff,
            )
        )
        or 0
    )
    completed_tasks_24h = sum(
        _normalized_timestamp(completed) >= day_cutoff
        for _, completed in completed_by_task.values()
    )
    phase_rows = list(
        await session.execute(
            select(ParentTask.phase, func.count(ParentTask.id)).group_by(ParentTask.phase)
        )
    )
    phase_counts = {phase.value: int(count) for phase, count in phase_rows}
    downloading = int(
        await session.scalar(
            select(func.count())
            .select_from(GenerationVariant)
            .where(GenerationVariant.download_status == DownloadStatus.DOWNLOADING)
        )
        or 0
    )

    return {
        "windowDays": 7,
        "stages": stages,
        "automationBottleneck": automation_bottleneck,
        "throughput": {
            "completedVideos24h": completed_videos_24h,
            "completedTasks24h": completed_tasks_24h,
        },
        "backlog": {
            "analysis": phase_counts.get(ParentTaskPhase.ANALYZING.value, 0),
            "confirmation": phase_counts.get(ParentTaskPhase.AWAITING_CONFIRMATION.value, 0),
            "materialization": phase_counts.get(ParentTaskPhase.PREPARING.value, 0),
            "queued": phase_counts.get(ParentTaskPhase.QUEUED.value, 0),
            "generation": phase_counts.get(ParentTaskPhase.GENERATING.value, 0),
            "delivery": downloading,
        },
    }


async def _business_baseline(session: AsyncSession) -> dict[str, Any]:
    job_count = int(await session.scalar(select(func.count()).select_from(ParentTask)) or 0)
    generated_video_count = int(
        await session.scalar(
            select(func.count())
            .select_from(GenerationVariant)
            .where(GenerationVariant.generation_status.in_(["SUCCEEDED", "PARTIAL"]))
        )
        or 0
    )
    final_deliverable_count = int(
        await session.scalar(
            select(func.count())
            .select_from(ParentTask)
            .where(ParentTask.phase == ParentTaskPhase.DELIVERABLE)
        )
        or 0
    )
    approved_variants = list(
        await session.scalars(
            select(GenerationVariant).where(GenerationVariant.final_approval_status == "APPROVED")
        )
    )
    total_variants = int(
        await session.scalar(select(func.count()).select_from(GenerationVariant)) or 0
    )
    regeneration_count = int(
        await session.scalar(
            select(func.count())
            .select_from(GenerationVariant)
            .where(GenerationVariant.revision > 1)
        )
        or 0
    )
    attempt_rows = list(
        await session.execute(
            select(
                GenerationAttempt.status,
                GenerationAttempt.credits_consumed,
                GenerationAttempt.submitted_at,
                GenerationAttempt.completed_at,
            )
        )
    )
    failed_statuses = {
        AttemptStatus.FAILED_BEFORE_SUBMIT,
        AttemptStatus.FAILED_TERMINAL,
        AttemptStatus.UNKNOWN_AFTER_SUBMIT,
        AttemptStatus.NEEDS_MANUAL_REVIEW,
    }
    failure_count = sum(status in failed_statuses for status, *_ in attempt_rows)
    waiting_seconds = [
        elapsed
        for _, _, started, completed in attempt_rows
        if (elapsed := _elapsed_seconds(started, completed)) is not None
    ]
    generation_cost = sum(int(cost or 0) for _, cost, *_ in attempt_rows)
    image_reviews = list(
        await session.scalars(
            select(ImageGenerationOutput).where(ImageGenerationOutput.reviewed_at.is_not(None))
        )
    )
    reviewed_variants = list(
        await session.scalars(
            select(GenerationVariant).where(GenerationVariant.final_approved_at.is_not(None))
        )
    )
    reviewed_items = [*image_reviews, *reviewed_variants]
    review_seconds = sum(float(item.human_review_seconds or 0) for item in reviewed_items)
    product_fidelity_failures = sum(
        (item.quality_gates_json or {}).get("PRODUCT_FIDELITY", {}).get("outcome") == "FAIL"
        for item in reviewed_items
    )
    feedback_rows = list(await session.scalars(select(GenerationFeedback)))
    critical_reason_codes = {
        "GARMENT_DISTORTED",
        "COLOR_INACCURATE",
        "LOGO_TEXT_INCORRECT",
        "FACE_HAND_ARTIFACT",
        "PRODUCT_UNCLEAR",
    }
    approved_ids = {item.id for item in approved_variants}
    critical_escapes = sum(
        feedback.variant_id in approved_ids
        and feedback.value.value == "DISLIKE"
        and bool(set(feedback.reason_codes_json or []) & critical_reason_codes)
        for feedback in feedback_rows
    )
    review_count = len(reviewed_items)
    attempt_total = len(attempt_rows)
    succeeded_count = sum(status == AttemptStatus.SUCCEEDED for status, *_ in attempt_rows)
    retry_count = sum(
        status in failed_statuses or status == AttemptStatus.UNKNOWN_AFTER_SUBMIT
        for status, *_ in attempt_rows
    )
    measurement_gaps = []
    if not review_count:
        measurement_gaps.append("human_review")
    if not attempt_total:
        measurement_gaps.append("generation_attempts")
    return {
        "status": "MEASURED" if review_count else "BASELINE_DATA_MISSING",
        "productionJobCount": job_count,
        "generatedVideoCount": generated_video_count,
        "finalDeliverableCount": final_deliverable_count,
        "firstPassDeliverableRate": (
            sum(item.revision == 1 for item in approved_variants) / len(approved_variants)
            if approved_variants
            else None
        ),
        "humanReviewMinutes": round(review_seconds / 60, 2),
        "humanMinutesPerDeliverable": (
            round(review_seconds / 60 / final_deliverable_count, 2)
            if final_deliverable_count
            else None
        ),
        "averageWaitingSeconds": (
            round(sum(waiting_seconds) / len(waiting_seconds), 1) if waiting_seconds else None
        ),
        "failureRate": failure_count / len(attempt_rows) if attempt_rows else None,
        "regenerationRate": regeneration_count / total_variants if total_variants else None,
        "generationCostCredits": generation_cost,
        "costCreditsPerDeliverable": (
            generation_cost / final_deliverable_count if final_deliverable_count else None
        ),
        "criticalQualityEscapeRate": (
            critical_escapes / len(approved_variants) if approved_variants else None
        ),
        "productFidelityFailureRate": (
            product_fidelity_failures / review_count if review_count else None
        ),
        "qualityReviewSampleCount": review_count,
        "criticalQualityEscapeCount": critical_escapes,
        "productFidelityFailureCount": product_fidelity_failures,
        "generationSuccessRate": succeeded_count / attempt_total if attempt_total else None,
        "retryRate": retry_count / attempt_total if attempt_total else None,
        "measurementStatus": "MEASUREMENT_GAP" if measurement_gaps else "MEASURED",
        "measurementGaps": measurement_gaps,
    }


async def _human_review_queue(session: AsyncSession) -> dict[str, int]:
    """Expose required human gates as a queue, so operators do not poll for work."""
    final_approval = int(
        await session.scalar(
            select(func.count())
            .select_from(ParentTask)
            .where(ParentTask.phase == ParentTaskPhase.AWAITING_FINAL_APPROVAL)
        )
        or 0
    )
    action_required = int(
        await session.scalar(
            select(func.count())
            .select_from(ParentTask)
            .where(ParentTask.phase == ParentTaskPhase.ACTION_REQUIRED)
        )
        or 0
    )
    product_fidelity = int(
        await session.scalar(
            select(func.count())
            .select_from(ImageGenerationOutput)
            .where(
                ImageGenerationOutput.reviewed_at.is_(None),
                ImageGenerationOutput.qualification_status == "PENDING",
            )
        )
        or 0
    )
    return {
        "productFidelity": product_fidelity,
        "humanCritical": action_required,
        "finalApproval": final_approval,
        "total": product_fidelity + action_required + final_approval,
    }


def _runtime_revisions(settings: Settings, config: dict[str, Any]) -> dict[str, Any]:
    current = {
        "sourceRevision": settings.deployment_source_revision,
        "schemaRevision": config.get("schemaRevision"),
        "configRevision": config.get("configRevision"),
        "runtimeVersion": config.get("runtimeVersion"),
    }
    locked = config.get("pilotRuntimeLock") or {}
    compared = {key: value for key, value in current.items() if value is not None}
    drift = bool(locked) and any(
        locked.get(key) not in (None, value) for key, value in compared.items()
    )
    return {"current": current, "locked": locked or None, "drift": drift}


async def operational_backlog_count(session: AsyncSession) -> int:
    prepared = int(
        await session.scalar(
            select(func.count())
            .select_from(GenerationAttempt)
            .where(GenerationAttempt.status == AttemptStatus.PREPARED)
        )
        or 0
    )
    ready = int(
        await session.scalar(
            select(func.count())
            .select_from(GenerationCommand)
            .where(GenerationCommand.status == CommandStatus.READY)
        )
        or 0
    )
    return prepared + ready


async def record_operational_sample(
    session: AsyncSession,
    settings: Settings,
    host: RunnerHost,
    *,
    backlog_count: int,
    orphan_process_count: int,
    free_disk_percent: float,
) -> OperationalMetricSample:
    runtime = await get_runtime_config(session, settings)
    config = runtime.config_json if runtime else {}
    global_slots = int(config.get("generationConcurrency", {}).get("global", 1))
    running_count = int(
        await session.scalar(
            select(func.count())
            .select_from(GenerationAttempt)
            .where(GenerationAttempt.status.in_([AttemptStatus.LAUNCHING, AttemptStatus.RUNNING]))
        )
        or 0
    )
    sample = OperationalMetricSample(
        runner_host_id=host.id,
        deployment_id=settings.deployment_id,
        libtv_adapter_mode=settings.libtv_adapter_mode,
        captured_at=datetime.now(UTC),
        global_slots=global_slots,
        backlog_count=max(0, backlog_count),
        running_count=max(0, running_count),
        slot_utilization=min(1.0, running_count / global_slots) if global_slots else 0.0,
        orphan_process_count=max(0, orphan_process_count),
        free_disk_percent=free_disk_percent,
        global_paused=bool(config.get("globalPaused", True)),
        paid_submissions_paused=bool(config.get("paidSubmissionsPaused", True)),
    )
    session.add(sample)
    return sample


async def prune_operational_samples(session: AsyncSession, retention_days: int) -> int:
    result = await session.execute(
        delete(OperationalMetricSample).where(
            OperationalMetricSample.captured_at < datetime.now(UTC) - timedelta(days=retention_days)
        )
    )
    return int(result.rowcount or 0)


async def _integrity_metrics(session: AsyncSession) -> tuple[int, int]:
    cache_key = session.get_bind()
    now = time.monotonic()
    cached = _integrity_metric_cache.get(cache_key)
    if cached is not None and now - cached[0] < INTEGRITY_METRIC_CACHE_SECONDS:
        return cached[1], cached[2]
    duplicate_groups = (
        select(
            GenerationAttempt.intent_hash.label("intent_hash"),
            func.count(GenerationAttempt.id).label("attempt_count"),
        )
        .where(
            GenerationAttempt.intent_hash.is_not(None),
            GenerationAttempt.launch_started_at.is_not(None),
        )
        .group_by(GenerationAttempt.intent_hash)
        .having(func.count(GenerationAttempt.id) > 1)
        .subquery()
    )
    duplicate_generation_total = int(
        await session.scalar(
            select(func.coalesce(func.sum(duplicate_groups.c.attempt_count - 1), 0))
        )
        or 0
    )
    cross_task_connection_total = int(
        await session.scalar(
            select(func.count())
            .select_from(GenerationReferenceAsset)
            .join(
                GenerationVariant,
                GenerationVariant.id == GenerationReferenceAsset.generation_variant_id,
            )
            .join(Asset, Asset.id == GenerationReferenceAsset.asset_id)
            .where(GenerationVariant.parent_task_id != Asset.parent_task_id)
        )
        or 0
    )
    _integrity_metric_cache[cache_key] = (
        now,
        duplicate_generation_total,
        cross_task_connection_total,
    )
    return duplicate_generation_total, cross_task_connection_total


async def _recent_orphan_process_count(session: AsyncSession, settings: Settings) -> int:
    recent_after = datetime.now(UTC) - timedelta(
        seconds=max(120, settings.runner_metric_sample_seconds * 3)
    )
    latest_by_host = (
        select(
            OperationalMetricSample.runner_host_id,
            func.max(OperationalMetricSample.captured_at).label("latest_at"),
        )
        .where(OperationalMetricSample.captured_at >= recent_after)
        .group_by(OperationalMetricSample.runner_host_id)
        .subquery()
    )
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(OperationalMetricSample.orphan_process_count), 0)).join(
                latest_by_host,
                (latest_by_host.c.runner_host_id == OperationalMetricSample.runner_host_id)
                & (latest_by_host.c.latest_at == OperationalMetricSample.captured_at),
            )
        )
        or 0
    )


async def operations_snapshot(session: AsyncSession, settings: Settings) -> dict[str, Any]:
    window_started_at = datetime.now(UTC) - timedelta(days=7)
    runtime = await get_runtime_config(session, settings)
    config = runtime.config_json if runtime else {}

    attempt_counts = (
        await session.execute(
            select(
                func.count(GenerationAttempt.id),
                func.sum(case((GenerationAttempt.status == AttemptStatus.PREPARED, 1), else_=0)),
                func.sum(
                    case(
                        (GenerationAttempt.status == AttemptStatus.DISPATCH_PENDING, 1),
                        else_=0,
                    )
                ),
                func.sum(case((GenerationAttempt.status == AttemptStatus.RUNNING, 1), else_=0)),
                func.sum(
                    case(
                        (GenerationAttempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT, 1),
                        else_=0,
                    )
                ),
                func.sum(
                    case((GenerationAttempt.charge_status == ChargeStatus.UNKNOWN, 1), else_=0)
                ),
            )
        )
    ).one()
    prepared = int(attempt_counts[1] or 0)
    dispatch_pending = int(attempt_counts[2] or 0)
    running = int(attempt_counts[3] or 0)
    unknown = int(attempt_counts[4] or 0)
    charged_unknown = int(attempt_counts[5] or 0)
    command_ready = int(
        await session.scalar(
            select(func.count())
            .select_from(GenerationCommand)
            .where(GenerationCommand.status == CommandStatus.READY)
        )
        or 0
    )
    global_slots = int(config.get("generationConcurrency", {}).get("global", 1))
    utilization = min(1.0, running / global_slots) if global_slots else 0.0
    # This baseline counts generations; summing historical 120-point rows with
    # current 1-generation rows would mix units. Retain legacy keys with explicit units.
    reservation_rows = await session.execute(
        select(
            PointsReservation.status,
            func.count(PointsReservation.id),
        ).group_by(PointsReservation.status)
    )
    reservations = {
        status.value: 0
        for status in (
            ReservationStatus.RESERVED,
            ReservationStatus.SETTLED,
            ReservationStatus.UNCERTAIN,
        )
    }
    reservations.update({status.value: int(total or 0) for status, total in reservation_rows})
    duplicate_generation_total, cross_task_connection_total = await _integrity_metrics(session)
    pipeline_performance = await _pipeline_performance(session)
    business_baseline = await _business_baseline(session)
    human_review_queue = await _human_review_queue(session)
    runtime_revisions = _runtime_revisions(settings, config)
    pipeline_backlog = pipeline_performance["backlog"]
    if config.get("globalPaused", True):
        current_constraint = "GLOBAL_PAUSED"
    elif running >= global_slots:
        current_constraint = "GENERATION_CAPACITY"
    elif command_ready:
        current_constraint = "RUNNER_DISPATCH"
    elif pipeline_backlog["confirmation"]:
        current_constraint = "CONFIRMATION"
    elif pipeline_backlog["materialization"] or pipeline_backlog["queued"]:
        current_constraint = "MATERIALIZATION"
    elif pipeline_backlog["analysis"]:
        current_constraint = "ANALYSIS"
    elif pipeline_backlog["delivery"]:
        current_constraint = "DELIVERY"
    else:
        current_constraint = "IDLE"
    pipeline_performance["currentConstraint"] = current_constraint
    orphan_process_count = await _recent_orphan_process_count(session, settings)
    launched_window = int(
        await session.scalar(
            select(func.count())
            .select_from(GenerationAttempt)
            .where(
                (
                    GenerationAttempt.submitted_at.is_not(None)
                    | GenerationAttempt.launch_started_at.is_not(None)
                ),
                (GenerationAttempt.submitted_at >= window_started_at)
                | (GenerationAttempt.launch_started_at >= window_started_at),
            )
        )
        or 0
    )
    unknown_window = int(
        await session.scalar(
            select(func.count())
            .select_from(GenerationAttempt)
            .where(
                GenerationAttempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT,
                (GenerationAttempt.submitted_at >= window_started_at)
                | (GenerationAttempt.launch_started_at >= window_started_at),
            )
        )
        or 0
    )
    active_runner_hosts = int(
        await session.scalar(
            select(func.count(func.distinct(GenerationAttempt.runner_host_id))).where(
                GenerationAttempt.runner_host_id.is_not(None),
                GenerationAttempt.status.in_([AttemptStatus.LAUNCHING, AttemptStatus.RUNNING]),
            )
        )
        or 0
    )
    delivery_failures = int(
        await session.scalar(
            select(func.count())
            .select_from(DownloadArtifact)
            .where(
                DownloadArtifact.status == DownloadStatus.FAILED,
                DownloadArtifact.updated_at >= window_started_at,
            )
        )
        or 0
    )
    image_quota_rejections = int(
        await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == "IMAGE_QUOTA_REJECTED",
                AuditEvent.created_at >= window_started_at,
            )
        )
        or 0
    )
    video_quota_rejections = int(
        await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == "VIDEO_QUOTA_REJECTED",
                AuditEvent.created_at >= window_started_at,
            )
        )
        or 0
    )
    alerts: list[dict[str, str]] = []
    if config.get("libtvAuthRequired", False):
        alerts.append(
            {
                "severity": "ACTION_REQUIRED",
                "code": "LIBTV_AUTH_REQUIRED",
                "action": "RUN_REFRESH_LIBTV_LOGIN",
            }
        )
    active = running + dispatch_pending + unknown
    if unknown >= 2 or (active and unknown / active > 0.10):
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "UNKNOWN_THRESHOLD_EXCEEDED",
                "action": "PAUSE_NEW_PAID_SUBMISSIONS",
            }
        )
    queue = config.get("preparedQueue", {})
    if command_ready + prepared < int(queue.get("lowWatermark", 0)):
        alerts.append(
            {
                "severity": "INFO",
                "code": "PREPARED_QUEUE_BELOW_LOW_WATERMARK",
                "action": "OBSERVE_MATERIALIZATION_CAPACITY",
            }
        )
    if runtime_revisions["drift"]:
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "PILOT_BLOCKED_RUNTIME_DRIFT",
                "action": "PAUSE_NEW_PAID_SUBMISSIONS",
            }
        )
    if cross_task_connection_total:
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "DATA_INTEGRITY_ASSET_CONTAMINATION",
                "action": "PAUSE_NEW_PAID_SUBMISSIONS",
            }
        )
    if charged_unknown:
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "PAID_STATE_UNCERTAIN",
                "action": "RECONCILE_BEFORE_RETRY",
            }
        )
    runners = list(await session.scalars(select(RunnerHost).order_by(RunnerHost.hostname)))
    canvases = list(await session.scalars(select(CanvasProject).order_by(CanvasProject.created_at)))
    return {
        "runtime": {
            "version": runtime.version if runtime else None,
            "config": config,
        },
        "runtimeRevisions": runtime_revisions,
        "queues": {
            "prepared": prepared,
            "generation": command_ready + dispatch_pending,
            "running": running,
            "unknown": unknown,
        },
        "metrics": {
            "duplicateGenerationTotal": duplicate_generation_total,
            "crossTaskConnectionTotal": cross_task_connection_total,
            "unknownAfterSubmitRate": unknown_window / launched_window if launched_window else 0.0,
            "unknownAfterSubmitWindowDays": 7,
            "generationSlotUtilization": utilization,
            "runnerActiveCommandHosts": active_runner_hosts,
            "runnerOrphanProcesses": orphan_process_count,
            "pointsReserved": reservations[ReservationStatus.RESERVED.value],
            "pointsConsumed": reservations[ReservationStatus.SETTLED.value],
            "pointsUncertain": reservations[ReservationStatus.UNCERTAIN.value],
            "deliveryFailureCount": delivery_failures,
            "imageQuotaRejectionCount": image_quota_rejections,
            "videoQuotaRejectionCount": video_quota_rejections,
        },
        "metricEvidence": {
            "duplicateGenerationTotal": {
                "source": "generation_attempt.intent_hash + launch_started_at",
                "calculation": "sum(attempt_count - 1) grouped by launched intent_hash",
            },
            "crossTaskConnectionTotal": {
                "source": "generation_reference_asset joined to generation_variant and asset",
                "calculation": "count where variant.parent_task_id != asset.parent_task_id",
            },
            "runnerOrphanProcesses": {
                "source": "latest operational metric sample from each active runner",
                "processIds": [],
            },
            "unknownAfterSubmitRate": {
                "source": "generation_attempt submitted_at/launch_started_at and status",
                "calculation": (
                    "unknown-after-submit attempts / launched attempts in the last 7 days"
                ),
                "windowDays": 7,
            },
            "pointsReserved": {"unit": "generation_reservations", "source": "points_reservation"},
            "pointsConsumed": {"unit": "generation_reservations", "source": "points_reservation"},
            "pointsUncertain": {"unit": "generation_reservations", "source": "points_reservation"},
            "deliveryFailureCount": {
                "source": "download_artifact.status=FAILED",
                "windowDays": 7,
            },
            "imageQuotaRejectionCount": {
                "source": "audit_event.action=IMAGE_QUOTA_REJECTED",
                "windowDays": 7,
            },
        },
        "runners": [
            {
                "id": str(item.id),
                "hostname": item.hostname,
                "status": item.status.value,
                "freeDiskPercent": item.free_disk_percent,
                "lastHeartbeatAt": item.last_heartbeat_at.isoformat(),
            }
            for item in runners
        ],
        "canvases": [
            {
                "projectUuid": item.project_uuid,
                "userId": str(item.user_id),
                "mutationState": item.mutation_state.value,
                "executionState": item.execution_state.value,
                "preparedVideos": item.prepared_video_count,
            }
            for item in canvases
        ],
        "points": {**reservations, "chargeUnknownAttempts": charged_unknown},
        "pipelinePerformance": pipeline_performance,
        "businessBaseline": business_baseline,
        "humanReviewQueue": human_review_queue,
        "alerts": alerts,
    }
