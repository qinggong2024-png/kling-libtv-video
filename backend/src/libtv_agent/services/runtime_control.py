from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from libtv_agent.config import Settings
from libtv_agent.domain.enums import AttemptStatus
from libtv_agent.domain.models import (
    AuditEvent,
    GenerationAttempt,
    GenerationVariant,
    ParentTask,
    RuntimeConfigVersion,
)
from libtv_agent.services.generation_safety import (
    paid_generation_authorized,
    real_provider_submission_authorized,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class RuntimeControlBlockedError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class UnknownSubmissionRisk:
    block_provider: bool
    block_user: bool
    provider_attempt_count: int
    provider_unknown_task_count: int
    provider_unknown_user_count: int
    user_unknown_task_count: int


_RISK_ASSESSED_STATUSES = {
    AttemptStatus.LAUNCHING,
    AttemptStatus.RUNNING,
    AttemptStatus.SUCCEEDED,
    AttemptStatus.FAILED_TERMINAL,
    AttemptStatus.UNKNOWN_AFTER_SUBMIT,
}


def _provider_names(provider: str, settings: Settings) -> tuple[str, ...]:
    normalized = provider.strip().lower()
    if normalized == "libtv":
        return ("libtv",)
    if normalized in {name.strip().lower() for name in settings.kling_provider_names}:
        return settings.kling_provider_names
    return (provider,)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def assess_unknown_submission_risk(
    session: AsyncSession,
    settings: Settings,
    provider: str,
    *,
    user_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> UnknownSubmissionRisk:
    """Evaluate recent UNKNOWN bursts without mutating global runtime state.

    A user circuit is isolated to one provider and requires UNKNOWN outcomes
    from multiple parent tasks. The provider circuit additionally requires a
    multi-user burst and a minimum sample size, so one user's stale UNKNOWN
    cannot stop unrelated work.
    """

    evaluated_at = now or datetime.now(UTC)
    provider_cutoff = evaluated_at - timedelta(seconds=settings.unknown_provider_window_seconds)
    user_cutoff = evaluated_at - timedelta(seconds=settings.unknown_user_window_seconds)
    earliest_cutoff = min(provider_cutoff, user_cutoff)
    event_at = func.coalesce(
        GenerationAttempt.submitted_at,
        GenerationAttempt.launch_started_at,
        GenerationAttempt.updated_at,
        GenerationAttempt.created_at,
    )
    rows = list(
        await session.execute(
            select(
                GenerationAttempt.status,
                ParentTask.id,
                ParentTask.user_id,
                event_at.label("event_at"),
            )
            .join(GenerationVariant, GenerationVariant.id == GenerationAttempt.variant_id)
            .join(ParentTask, ParentTask.id == GenerationVariant.parent_task_id)
            .where(
                GenerationAttempt.provider.in_(_provider_names(provider, settings)),
                GenerationAttempt.status.in_(_RISK_ASSESSED_STATUSES),
                event_at >= earliest_cutoff,
            )
        )
    )

    provider_rows = [row for row in rows if _as_utc(row.event_at) >= provider_cutoff]
    provider_unknown_rows = [
        row for row in provider_rows if row.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT
    ]
    provider_unknown_tasks = {row.id for row in provider_unknown_rows}
    provider_unknown_users = {row.user_id for row in provider_unknown_rows}
    provider_attempt_count = len(provider_rows)
    provider_unknown_rate = (
        len(provider_unknown_rows) / provider_attempt_count if provider_attempt_count else 0.0
    )
    block_provider = (
        provider_attempt_count >= settings.unknown_provider_min_attempts
        and len(provider_unknown_tasks) >= settings.unknown_provider_distinct_task_threshold
        and len(provider_unknown_users) >= settings.unknown_provider_distinct_user_threshold
        and provider_unknown_rate >= settings.unknown_provider_rate_threshold
    )

    user_unknown_tasks: set[uuid.UUID] = set()
    if user_id is not None:
        user_unknown_tasks = {
            row.id
            for row in rows
            if row.user_id == user_id
            and _as_utc(row.event_at) >= user_cutoff
            and row.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT
        }
    block_user = (
        user_id is not None
        and len(user_unknown_tasks) >= settings.unknown_user_distinct_task_threshold
    )
    return UnknownSubmissionRisk(
        block_provider=block_provider,
        block_user=block_user,
        provider_attempt_count=provider_attempt_count,
        provider_unknown_task_count=len(provider_unknown_tasks),
        provider_unknown_user_count=len(provider_unknown_users),
        user_unknown_task_count=len(user_unknown_tasks),
    )


def _raise_for_unknown_risk(risk: UnknownSubmissionRisk) -> None:
    if risk.block_provider:
        raise RuntimeControlBlockedError(
            "PROVIDER_UNKNOWN_CIRCUIT_OPEN",
            "recent UNKNOWN outcomes indicate a provider-wide incident; "
            "only this provider is paused",
        )
    if risk.block_user:
        raise RuntimeControlBlockedError(
            "USER_PROVIDER_UNKNOWN_CIRCUIT_OPEN",
            "recent UNKNOWN outcomes for this user and provider require reconciliation",
        )


def default_runtime_config(settings: Settings) -> dict[str, Any]:
    return {
        "globalPaused": settings.global_paused,
        "paidSubmissionsPaused": settings.paid_submissions_paused,
        "internalPilotEnabled": False,
        "pilotUserIds": [],
        "pilotBudgetLimit": 0,
        "pilotSubmittedCount": 0,
        "libtvAuthRequired": False,
        "generationConcurrency": {
            "sameProject": settings.generation_same_project,
            "perUser": settings.generation_per_user,
            "global": settings.generation_global,
        },
        "preparedQueue": {
            "lowWatermark": settings.prepared_queue_low_watermark,
            "highWatermark": settings.prepared_queue_high_watermark,
        },
        "promptConfirmationRequired": True,
        "autoConfirmLevels": ["PASS"],
    }


def validate_runtime_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(config)
    normalized.setdefault("internalPilotEnabled", False)
    normalized.setdefault("pilotUserIds", [])
    normalized.setdefault("pilotBudgetLimit", 0)
    normalized.setdefault("pilotSubmittedCount", 0)
    concurrency = normalized.get("generationConcurrency")
    queue = normalized.get("preparedQueue")
    if not isinstance(concurrency, dict) or not isinstance(queue, dict):
        raise ValueError("generationConcurrency and preparedQueue are required")
    limits = {"sameProject": 4, "perUser": 6, "global": 12}
    for key, maximum in limits.items():
        value = concurrency.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= maximum:
            raise ValueError(f"{key} must be between 1 and {maximum}")
    low = queue.get("lowWatermark")
    high = queue.get("highWatermark")
    if not isinstance(low, int) or not isinstance(high, int):
        raise ValueError("prepared queue watermarks must be integers")
    if low < concurrency["global"]:
        raise ValueError("lowWatermark must cover global concurrency")
    if high < 2 * concurrency["global"]:
        raise ValueError("highWatermark must be at least twice global concurrency")
    for key in ("globalPaused", "paidSubmissionsPaused", "internalPilotEnabled"):
        if not isinstance(normalized.get(key), bool):
            raise ValueError(f"{key} must be boolean")
    pilot_user_ids = normalized.get("pilotUserIds")
    if (
        not isinstance(pilot_user_ids, list)
        or any(not isinstance(value, str) or not value.strip() for value in pilot_user_ids)
    ):
        raise ValueError("pilotUserIds must be a list of non-empty strings")
    if len(pilot_user_ids) != len(set(pilot_user_ids)):
        raise ValueError("pilotUserIds must not contain duplicates")
    for key in ("pilotBudgetLimit", "pilotSubmittedCount"):
        value = normalized.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{key} must be a non-negative integer")
    if normalized["pilotSubmittedCount"] > normalized["pilotBudgetLimit"]:
        raise ValueError("pilotSubmittedCount cannot exceed pilotBudgetLimit")
    # Existing runtime-config rows predate LibTV account health tracking.
    normalized.setdefault("libtvAuthRequired", False)
    if not isinstance(normalized["libtvAuthRequired"], bool):
        raise ValueError("libtvAuthRequired must be boolean")
    # Existing runtime-config rows predate this setting. Preserve their safe behavior.
    normalized.setdefault("promptConfirmationRequired", True)
    if not isinstance(normalized["promptConfirmationRequired"], bool):
        raise ValueError("promptConfirmationRequired must be boolean")
    if normalized.get("autoConfirmLevels") != ["PASS"]:
        raise ValueError("only PASS may enter automatic confirmation")
    return normalized


async def reserve_internal_pilot_budget(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    units: int,
) -> RuntimeConfigVersion | None:
    """Atomically admit a real pilot submission and consume its budget.

    Development and test adapters intentionally bypass this gate. Production
    defaults remain closed until an administrator explicitly configures the
    pilot switch, allow-list, and non-zero budget.
    """

    if settings.app_env in {"development", "test"}:
        return await get_runtime_config(session, settings)
    if units < 1:
        raise ValueError("pilot budget units must be positive")
    current = await get_runtime_config(session, settings)
    if current is None:
        raise RuntimeControlBlockedError("RUNTIME_CONFIG_MISSING", "runtime config is unavailable")
    config = deepcopy(current.config_json)
    if not config.get("internalPilotEnabled", False):
        raise RuntimeControlBlockedError(
            "INTERNAL_PILOT_DISABLED",
            "internal pilot submissions are not enabled",
        )
    if str(user_id) not in config.get("pilotUserIds", []):
        raise RuntimeControlBlockedError(
            "INTERNAL_PILOT_USER_NOT_ALLOWED",
            "the account is not allow-listed for the internal pilot",
        )
    limit = int(config.get("pilotBudgetLimit", 0))
    used = int(config.get("pilotSubmittedCount", 0))
    if used + units > limit:
        raise RuntimeControlBlockedError(
            "PILOT_BUDGET_EXCEEDED",
            "the internal pilot submission budget has been reached",
        )
    config["pilotSubmittedCount"] = used + units
    return await update_runtime_config(
        session,
        settings,
        config=config,
        actor_id=None,
        reason=f"internal pilot admission for {units} unit(s)",
        expected_version=current.version,
    )


async def get_runtime_config(
    session: AsyncSession, settings: Settings, *, create: bool = True
) -> RuntimeConfigVersion | None:
    current = await session.scalar(
        select(RuntimeConfigVersion).order_by(RuntimeConfigVersion.version.desc()).limit(1)
    )
    if current is None and create:
        current = RuntimeConfigVersion(
            version=1,
            config_json=validate_runtime_config(default_runtime_config(settings)),
            change_reason="initial controlled MVP safety defaults",
        )
        session.add(current)
        await session.flush()
    return current


async def update_runtime_config(
    session: AsyncSession,
    settings: Settings,
    *,
    config: dict[str, Any],
    actor_id: uuid.UUID | None,
    reason: str,
    expected_version: int | None = None,
    rolled_back_from: int | None = None,
) -> RuntimeConfigVersion:
    current = await session.scalar(
        select(RuntimeConfigVersion)
        .order_by(RuntimeConfigVersion.version.desc())
        .with_for_update()
        .limit(1)
    )
    if current is None:
        current = await get_runtime_config(session, settings)
    if current is None:
        raise RuntimeError("runtime config could not be initialized")
    if expected_version is not None and current.version != expected_version:
        raise ValueError(f"runtime config version is {current.version}, not {expected_version}")
    validated = validate_runtime_config(config)
    next_version = RuntimeConfigVersion(
        version=current.version + 1,
        config_json=validated,
        changed_by=actor_id,
        change_reason=reason,
        rolled_back_from=rolled_back_from,
    )
    session.add(next_version)
    session.add(
        AuditEvent(
            actor_id=actor_id,
            action="UPDATE_RUNTIME_CONFIG",
            entity_type="runtime_config_version",
            entity_id=str(next_version.version),
            from_state=str(current.version),
            to_state=str(next_version.version),
            reason=reason,
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[],
        )
    )
    await session.flush()
    return next_version


async def rollback_runtime_config(
    session: AsyncSession,
    settings: Settings,
    *,
    target_version: int,
    actor_id: uuid.UUID,
    reason: str,
    expected_version: int,
) -> RuntimeConfigVersion:
    target = await session.scalar(
        select(RuntimeConfigVersion).where(RuntimeConfigVersion.version == target_version)
    )
    if target is None:
        raise ValueError("target runtime config version does not exist")
    return await update_runtime_config(
        session,
        settings,
        config=target.config_json,
        actor_id=actor_id,
        reason=reason,
        expected_version=expected_version,
        rolled_back_from=target_version,
    )


async def set_libtv_auth_required(
    session: AsyncSession,
    settings: Settings,
    *,
    required: bool,
    reason: str,
) -> RuntimeConfigVersion | None:
    current = await get_runtime_config(session, settings)
    if current is None:
        return None
    config = deepcopy(current.config_json)
    config["libtvAuthRequired"] = required
    if config == current.config_json:
        return current
    return await update_runtime_config(
        session,
        settings,
        config=config,
        actor_id=None,
        reason=reason,
        expected_version=current.version,
    )


async def ensure_paid_submission_allowed(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: uuid.UUID | None = None,
) -> None:
    if settings.libtv_adapter_mode != "real":
        return
    if not paid_generation_authorized(settings):
        raise RuntimeControlBlockedError(
            "PAID_GENERATION_BLOCKED",
            "paid generation requires live mode, the explicit enable switch, and confirmation",
        )
    current = await get_runtime_config(session, settings)
    if current is None:
        raise RuntimeControlBlockedError("RUNTIME_CONFIG_MISSING", "runtime config is unavailable")
    if current.config_json["globalPaused"]:
        raise RuntimeControlBlockedError("GLOBAL_PAUSED", "global generation pause is active")
    if current.config_json.get("libtvAuthRequired", False):
        raise RuntimeControlBlockedError(
            "LIBTV_AUTH_REQUIRED", "LibTV login has expired; administrator login is required"
        )
    if current.config_json["paidSubmissionsPaused"]:
        raise RuntimeControlBlockedError("PAID_SUBMISSIONS_PAUSED", "paid confirmations are paused")
    _raise_for_unknown_risk(
        await assess_unknown_submission_risk(
            session,
            settings,
            "libtv",
            user_id=user_id,
        )
    )


async def ensure_provider_submission_allowed(
    session: AsyncSession,
    settings: Settings,
    provider: str,
    *,
    user_id: uuid.UUID | None = None,
) -> None:
    if provider == "libtv":
        await ensure_paid_submission_allowed(session, settings, user_id=user_id)
        return
    if provider not in settings.kling_provider_names:
        raise RuntimeControlBlockedError(
            "PROVIDER_UNSUPPORTED", f"unsupported generation provider: {provider}"
        )
    if not real_provider_submission_authorized(settings):
        raise RuntimeControlBlockedError(
            "PAID_GENERATION_BLOCKED",
            "real provider submissions require live mode, the explicit enable switch, "
            "and the exact confirmation phrase",
        )
    if not settings.kling_provider_submission_enabled(provider):
        raise RuntimeControlBlockedError(
            "KLING_CAPABILITY_UNSUPPORTED",
            "New Kling submissions require the enabled official API Provider",
        )
    current = await get_runtime_config(session, settings)
    if current is None:
        raise RuntimeControlBlockedError("RUNTIME_CONFIG_MISSING", "runtime config is unavailable")
    if current.config_json["globalPaused"]:
        raise RuntimeControlBlockedError("GLOBAL_PAUSED", "global generation pause is active")
    if current.config_json["paidSubmissionsPaused"]:
        raise RuntimeControlBlockedError("PAID_SUBMISSIONS_PAUSED", "paid confirmations are paused")
    _raise_for_unknown_risk(
        await assess_unknown_submission_risk(
            session,
            settings,
            provider,
            user_id=user_id,
        )
    )


async def generation_claims_allowed(session: AsyncSession, settings: Settings) -> bool:
    if settings.libtv_adapter_mode == "real" and not paid_generation_authorized(settings):
        return False
    current = await get_runtime_config(session, settings)
    return bool(
        current
        and not current.config_json["globalPaused"]
        and not current.config_json.get("libtvAuthRequired", False)
    )


async def provider_claims_allowed(
    session: AsyncSession,
    settings: Settings,
    provider: str,
    *,
    user_id: uuid.UUID | None = None,
) -> bool:
    current = await get_runtime_config(session, settings)
    if current is None or current.config_json["globalPaused"]:
        return False
    if provider == "libtv":
        if not await generation_claims_allowed(session, settings):
            return False
        risk = await assess_unknown_submission_risk(
            session,
            settings,
            provider,
            user_id=user_id,
        )
        return not risk.block_provider and not risk.block_user
    if (
        provider not in settings.kling_provider_names
        or not settings.kling_provider_submission_enabled(provider)
    ):
        return False
    if not real_provider_submission_authorized(settings):
        return False
    risk = await assess_unknown_submission_risk(
        session,
        settings,
        provider,
        user_id=user_id,
    )
    return not risk.block_provider and not risk.block_user
