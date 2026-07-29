import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from libtv_agent.config import Settings  # noqa: E402
from libtv_agent.db import Database  # noqa: E402
from libtv_agent.domain.enums import (  # noqa: E402
    AttemptStatus,
    ConsistencyLevel,
    DownloadStatus,
    ParentTaskPhase,
    VariantKind,
)
from libtv_agent.domain.models import (  # noqa: E402
    Asset,
    AuditEvent,
    CanvasProject,
    DownloadArtifact,
    GenerationAttempt,
    GenerationReferenceAsset,
    GenerationVariant,
    OperationalMetricSample,
    ParentTask,
    PointsReservation,
)
from libtv_agent.services.observability import operations_snapshot  # noqa: E402
from sqlalchemy import distinct, func, or_, select  # noqa: E402


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def operational_series_evidence(
    samples: list[OperationalMetricSample], *, max_gap_seconds: float
) -> dict[str, object]:
    by_host: dict[object, list[OperationalMetricSample]] = defaultdict(list)
    for sample in samples:
        by_host[sample.runner_host_id].append(sample)

    longest_seconds = 0.0
    backlog_weighted_seconds = 0.0
    backlog_observed_seconds = 0.0
    backlog_interval_count = 0
    active_sample_count = 0
    timestamps: list[datetime] = []
    for host_samples in by_host.values():
        ordered = sorted(host_samples, key=lambda item: _utc(item.captured_at))
        timestamps.extend(_utc(item.captured_at) for item in ordered)
        run_seconds = 0.0
        previous: OperationalMetricSample | None = None
        for sample in ordered:
            active = not sample.global_paused and not sample.paid_submissions_paused
            if active:
                active_sample_count += 1
            if previous is None:
                previous = sample
                continue
            gap_seconds = (_utc(sample.captured_at) - _utc(previous.captured_at)).total_seconds()
            previous_active = not previous.global_paused and not previous.paid_submissions_paused
            continuous = previous_active and active and 0 < gap_seconds <= max_gap_seconds
            if continuous:
                run_seconds += gap_seconds
                longest_seconds = max(longest_seconds, run_seconds)
                if previous.backlog_count > 0:
                    backlog_weighted_seconds += previous.slot_utilization * gap_seconds
                    backlog_observed_seconds += gap_seconds
                    backlog_interval_count += 1
            else:
                run_seconds = 0.0
            previous = sample

    return {
        "continuousRunHours": longest_seconds / 3600 if active_sample_count else None,
        "backloggedSlotUtilization": (
            backlog_weighted_seconds / backlog_observed_seconds
            if backlog_observed_seconds
            else None
        ),
        "evidence": {
            "source": "operational_metric_sample",
            "sampleCount": len(samples),
            "activeSampleCount": active_sample_count,
            "runnerHostCount": len(by_host),
            "observedFrom": min(timestamps).isoformat() if timestamps else None,
            "observedTo": max(timestamps).isoformat() if timestamps else None,
            "maximumAcceptedGapSeconds": max_gap_seconds,
            "continuousRunCalculation": (
                "maximum same-runner sum of consecutive heartbeat intervals; global/paid "
                "pause or an interval above the accepted gap resets the sequence"
            ),
            "backlogIntervalCount": backlog_interval_count,
            "backlogObservedSeconds": backlog_observed_seconds,
            "backloggedUtilizationCalculation": (
                "time-weighted slot_utilization over valid active intervals whose "
                "starting sample has backlog_count > 0"
            ),
        },
    }


async def collect(settings: Settings) -> dict[str, object]:
    database = Database(settings.database_url)
    try:
        async with database.session_factory() as session:
            snapshot = await operations_snapshot(session, settings)
            real_libtv_scope = settings.libtv_adapter_mode == "real"
            launched = GenerationAttempt.launch_started_at.is_not(None)
            real_runner = GenerationAttempt.runner_execution_backend == "WINDOWS_COMMAND_HOST"
            real_filter = (launched, real_runner)
            launched_total = int(
                await session.scalar(
                    select(func.count()).select_from(GenerationAttempt).where(*real_filter)
                )
                or 0
            )
            succeeded_total = int(
                await session.scalar(
                    select(func.count())
                    .select_from(GenerationAttempt)
                    .where(*real_filter, GenerationAttempt.status == AttemptStatus.SUCCEEDED)
                )
                or 0
            )
            parent_total = int(
                await session.scalar(
                    select(func.count(distinct(GenerationVariant.parent_task_id)))
                    .select_from(GenerationAttempt)
                    .join(GenerationVariant, GenerationVariant.id == GenerationAttempt.variant_id)
                    .where(*real_filter)
                )
                or 0
            )
            user_total = int(
                await session.scalar(
                    select(func.count(distinct(ParentTask.user_id)))
                    .select_from(GenerationAttempt)
                    .join(GenerationVariant, GenerationVariant.id == GenerationAttempt.variant_id)
                    .join(ParentTask, ParentTask.id == GenerationVariant.parent_task_id)
                    .where(*real_filter)
                )
                or 0
            )
            variant_counts = {}
            for kind in VariantKind:
                variant_counts[kind.value] = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(GenerationAttempt)
                        .join(
                            GenerationVariant,
                            GenerationVariant.id == GenerationAttempt.variant_id,
                        )
                        .where(
                            *real_filter,
                            GenerationAttempt.status == AttemptStatus.SUCCEEDED,
                            GenerationVariant.variant_type == kind,
                        )
                    )
                    or 0
                )
            duplicate_real_groups = (
                select(
                    GenerationAttempt.intent_hash.label("intent_hash"),
                    func.count(GenerationAttempt.id).label("attempt_count"),
                )
                .where(
                    *real_filter,
                    GenerationAttempt.intent_hash.is_not(None),
                )
                .group_by(GenerationAttempt.intent_hash)
                .having(func.count(GenerationAttempt.id) > 1)
                .subquery()
            )
            duplicate_formal_generations = int(
                await session.scalar(
                    select(func.coalesce(func.sum(duplicate_real_groups.c.attempt_count - 1), 0))
                )
                or 0
            )
            consumed_points = int(
                await session.scalar(
                    select(func.coalesce(func.sum(PointsReservation.actual_points), 0))
                    .join(
                        GenerationAttempt,
                        GenerationAttempt.id == PointsReservation.attempt_id,
                    )
                    .where(
                        *real_filter,
                        PointsReservation.actual_points.is_not(None),
                    )
                )
                or 0
            )
            openai_requests = int(
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "OPENAI_ANALYSIS_REQUEST_STARTED")
                )
                or 0
            )
            cross_user = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ParentTask)
                    .join(
                        CanvasProject,
                        CanvasProject.project_uuid == ParentTask.assigned_project_uuid,
                    )
                    .where(ParentTask.user_id != CanvasProject.user_id)
                )
                or 0
            )
            asset_order_errors = int(
                await session.scalar(
                    select(func.count())
                    .select_from(GenerationReferenceAsset)
                    .join(Asset, Asset.id == GenerationReferenceAsset.asset_id)
                    .where(GenerationReferenceAsset.order_no != Asset.order_no)
                )
                or 0
            )
            points_bypasses = int(
                await session.scalar(
                    select(func.count())
                    .select_from(GenerationAttempt)
                    .outerjoin(
                        PointsReservation,
                        PointsReservation.attempt_id == GenerationAttempt.id,
                    )
                    .where(*real_filter, PointsReservation.id.is_(None))
                )
                or 0
            )
            unknown = int(
                await session.scalar(
                    select(func.count())
                    .select_from(GenerationAttempt)
                    .where(
                        *real_filter,
                        GenerationAttempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT,
                    )
                )
                or 0
            )
            rate_limited = int(
                await session.scalar(
                    select(func.count())
                    .select_from(GenerationAttempt)
                    .where(
                        *real_filter,
                        or_(
                            GenerationAttempt.last_error_code == "RATE_LIMITED",
                            GenerationAttempt.last_error_code == "SYSTEM_RATE_LIMITED",
                        ),
                    )
                )
                or 0
            )
            artifacts = list(
                await session.scalars(
                    select(DownloadArtifact)
                    .join(GenerationAttempt, GenerationAttempt.id == DownloadArtifact.attempt_id)
                    .where(*real_filter, GenerationAttempt.status == AttemptStatus.SUCCEEDED)
                )
            )
            decoded = sum(
                item.status == DownloadStatus.READY
                and item.sha256 is not None
                and item.width is not None
                and item.height is not None
                and item.duration_seconds is not None
                for item in artifacts
            )
            duration_ok = sum(
                item.duration_seconds is not None and 9.0 <= item.duration_seconds <= 11.0
                for item in artifacts
            )
            ratio_ok = sum(
                item.width is not None
                and item.height is not None
                and item.height > 0
                and abs((item.width / item.height) - (9 / 16)) / (9 / 16) <= 0.01
                for item in artifacts
            )
            time_bounds = (
                await session.execute(
                    select(
                        func.min(GenerationAttempt.launch_started_at),
                        func.max(GenerationAttempt.updated_at),
                    ).where(*real_filter)
                )
            ).one()
            observed_span_hours = None
            if time_bounds[0] is not None and time_bounds[1] is not None:
                observed_span_hours = (time_bounds[1] - time_bounds[0]).total_seconds() / 3600
            operational_samples = list(
                await session.scalars(
                    select(OperationalMetricSample)
                    .where(
                        OperationalMetricSample.deployment_id == settings.deployment_id,
                        OperationalMetricSample.libtv_adapter_mode == "real",
                    )
                    .order_by(
                        OperationalMetricSample.runner_host_id,
                        OperationalMetricSample.captured_at,
                    )
                )
            )
            series = operational_series_evidence(
                operational_samples,
                max_gap_seconds=max(30.0, float(settings.runner_poll_seconds * 3)),
            )
            low_risk_task_ids = set(
                await session.scalars(
                    select(distinct(ParentTask.id))
                    .join(GenerationVariant, GenerationVariant.parent_task_id == ParentTask.id)
                    .join(GenerationAttempt, GenerationAttempt.variant_id == GenerationVariant.id)
                    .where(
                        ParentTask.consistency_level == ConsistencyLevel.PASS,
                        GenerationAttempt.launch_started_at.is_not(None),
                        GenerationAttempt.runner_execution_backend == "WINDOWS_COMMAND_HOST",
                    )
                )
            )
            delivered_low_risk_task_ids = (
                set(
                    await session.scalars(
                        select(ParentTask.id).where(
                            ParentTask.id.in_(low_risk_task_ids),
                            ParentTask.phase == ParentTaskPhase.DELIVERABLE,
                        )
                    )
                )
                if low_risk_task_ids
                else set()
            )
            automatically_confirmed_ids = {
                item
                for item in await session.scalars(
                    select(AuditEvent.entity_id).where(
                        AuditEvent.action == "AUTO_CONFIRM_TASK",
                        AuditEvent.entity_type == "parent_task",
                    )
                )
            }
            auto_deliverable_total = len(
                {str(item) for item in low_risk_task_ids & delivered_low_risk_task_ids}
                & automatically_confirmed_ids
            )
            low_risk_auto_completion_rate = _ratio(auto_deliverable_total, len(low_risk_task_ids))
            eligible = real_libtv_scope
            return {
                "schemaVersion": "1.0",
                "status": "COLLECTED" if eligible else "INELIGIBLE_NON_REAL_ADAPTER",
                "generatedAt": datetime.now(UTC).isoformat(),
                "scope": {
                    "libtvAdapterMode": settings.libtv_adapter_mode,
                    "aiAdapterMode": settings.ai_adapter_mode,
                    "realEvidenceEligible": eligible,
                },
                "realConsumption": {
                    "openAiRequests": openai_requests
                    if settings.ai_adapter_mode == "openai"
                    else None,
                    "openAiRequestEvidence": "audit_event OPENAI_ANALYSIS_REQUEST_STARTED",
                    "libtvNodeRuns": launched_total if eligible else None,
                    "videosGenerated": succeeded_total if eligible else None,
                    "libtvPoints": consumed_points if eligible else None,
                },
                "controlledMvp": {
                    "parentTasks": parent_total if eligible else None,
                    "videos": succeeded_total if eligible else None,
                    "users": user_total if eligible else None,
                    "stableVideos": variant_counts[VariantKind.STABLE.value] if eligible else None,
                    "dynamicVideos": variant_counts[VariantKind.DYNAMIC.value]
                    if eligible
                    else None,
                    "sameProjectConcurrency": (
                        snapshot["runtime"]["config"]
                        .get("generationConcurrency", {})
                        .get("sameProject")
                    )
                    if eligible
                    else None,
                    "globalConcurrency": (
                        snapshot["runtime"]["config"].get("generationConcurrency", {}).get("global")
                    )
                    if eligible
                    else None,
                    "observedSpanHours": observed_span_hours if eligible else None,
                    "continuousRunHours": series["continuousRunHours"] if eligible else None,
                    "continuousRunEvidence": series["evidence"],
                },
                "acceptanceMetrics": {
                    "duplicateFormalGenerations": duplicate_formal_generations
                    if eligible
                    else None,
                    "crossParentTaskConnections": snapshot["metrics"]["crossTaskConnectionTotal"]
                    if eligible
                    else None,
                    "crossUserProjectAllocations": cross_user if eligible else None,
                    "assetOrderErrors": asset_order_errors if eligible else None,
                    "pointsReservationBypasses": points_bypasses if eligible else None,
                    "videoDecodeSuccessRate": _ratio(decoded, succeeded_total)
                    if eligible
                    else None,
                    "targetDurationCompliance": _ratio(duration_ok, succeeded_total)
                    if eligible
                    else None,
                    "aspectRatioCompliance": _ratio(ratio_ok, succeeded_total)
                    if eligible
                    else None,
                    "unknownAfterSubmitRate": _ratio(unknown, launched_total) if eligible else None,
                    "systemRateLimitRate": _ratio(rate_limited, launched_total)
                    if eligible
                    else None,
                    "backloggedSlotUtilization": series["backloggedSlotUtilization"]
                    if eligible
                    else None,
                    "lowRiskAutoCompletionRate": low_risk_auto_completion_rate
                    if eligible
                    else None,
                },
                "metricEvidence": {
                    **snapshot["metricEvidence"],
                    "duplicateFormalGenerations": {
                        "source": "generation_attempt.intent_hash",
                        "runnerExecutionBackend": "WINDOWS_COMMAND_HOST",
                        "launchedOnly": True,
                        "calculation": "sum(attempt_count - 1) grouped by intent_hash",
                    },
                    "crossParentTaskConnections": {
                        "source": (
                            "generation_reference_asset joined to generation_variant and asset"
                        ),
                        "count": snapshot["metrics"]["crossTaskConnectionTotal"],
                        "calculation": (
                            "count where generation_variant.parent_task_id != asset.parent_task_id"
                        ),
                    },
                    "crossUserProjectAllocations": {
                        "source": "parent_task joined to canvas_project",
                        "count": cross_user,
                        "calculation": "count where parent_task.user_id != canvas_project.user_id",
                    },
                    "assetOrderErrors": {
                        "source": "generation_reference_asset joined to asset",
                        "count": asset_order_errors,
                        "calculation": "count where reference order_no != asset order_no",
                    },
                    "pointsReservationBypasses": {
                        "source": (
                            "launched WINDOWS_COMMAND_HOST generation_attempt left join "
                            "points_reservation"
                        ),
                        "count": points_bypasses,
                        "calculation": "count launched real attempts without a reservation row",
                    },
                    "videoDecodeSuccessRate": {
                        "source": "download_artifact for succeeded real attempts",
                        "numerator": decoded,
                        "denominator": succeeded_total,
                        "calculation": (
                            "READY artifact with hash, dimensions, and duration / succeeded"
                        ),
                    },
                    "targetDurationCompliance": {
                        "source": "download_artifact.duration_seconds",
                        "numerator": duration_ok,
                        "denominator": succeeded_total,
                        "calculation": "artifacts in [9.0, 11.0] seconds / succeeded",
                    },
                    "aspectRatioCompliance": {
                        "source": "download_artifact.width + height",
                        "numerator": ratio_ok,
                        "denominator": succeeded_total,
                        "calculation": "artifacts within 1 percent of 9:16 / succeeded",
                    },
                    "unknownAfterSubmitRate": {
                        "source": "generation_attempt.status",
                        "numerator": unknown,
                        "denominator": launched_total,
                        "runnerExecutionBackend": "WINDOWS_COMMAND_HOST",
                    },
                    "systemRateLimitRate": {
                        "source": "generation_attempt.last_error_code",
                        "numerator": rate_limited,
                        "denominator": launched_total,
                        "acceptedCodes": ["RATE_LIMITED", "SYSTEM_RATE_LIMITED"],
                    },
                    "backloggedSlotUtilization": series["evidence"],
                    "lowRiskAutoCompletionRate": {
                        "source": (
                            "parent_task + generation_variant + generation_attempt + audit_event"
                        ),
                        "eligibleParentTaskCount": len(low_risk_task_ids),
                        "autoConfirmedDeliverableParentTaskCount": auto_deliverable_total,
                        "calculation": (
                            "AUTO_CONFIRM_TASK and final DELIVERABLE divided by PASS parent tasks "
                            "with a launched WINDOWS_COMMAND_HOST attempt"
                        ),
                    },
                },
            }
    finally:
        await database.engine.dispose()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = Settings()
    try:
        report = await collect(settings)
        exit_code = 0
    except Exception as exc:
        report = {
            "schemaVersion": "1.0",
            "status": "BLOCKED",
            "generatedAt": datetime.now(UTC).isoformat(),
            "errorType": type(exc).__name__,
            "error": str(exc),
        }
        exit_code = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
