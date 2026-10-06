import asyncio
import logging
import os
import platform
import socket
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from libtv_agent.adapters.kling_provider import create_kling_adapter
from libtv_agent.adapters.libtv import LibTVAdapter, LibTVError, create_libtv_adapter
from libtv_agent.adapters.object_store import create_object_store
from libtv_agent.config import Settings
from libtv_agent.db import Database
from libtv_agent.domain.enums import RunnerHostStatus
from libtv_agent.domain.models import AuditEvent, RunnerHost
from libtv_agent.runner.command_host_manager import CommandHostManager
from libtv_agent.runner.supervisor import RunnerSupervisor
from libtv_agent.services.bach_config import (
    bach_admin_config_signature,
    load_bach_admin_config,
)
from libtv_agent.services.confirmation import auto_confirm_pass_tasks
from libtv_agent.services.confirmation_recovery import (
    recover_stale_batch_confirmation_claims,
    recover_stale_confirmation_claims,
)
from libtv_agent.services.idempotency import release_stale_idempotency_claims
from libtv_agent.services.kling_config import (
    kling_admin_config_signature,
    load_kling_admin_config,
)
from libtv_agent.services.observability import (
    operational_backlog_count,
    prune_operational_samples,
    record_operational_sample,
)
from libtv_agent.services.runtime_control import (
    get_runtime_config,
    set_libtv_auth_required,
    update_runtime_config,
)
from libtv_agent.services.wavespeed_config import (
    load_wavespeed_admin_config,
    wavespeed_admin_config_signature,
)
from sqlalchemy import select

logger = logging.getLogger(__name__)


def _video_provider_admin_config_signatures(
    settings: Settings,
) -> tuple[tuple[int, int] | None, tuple[int, int] | None, tuple[int, int] | None]:
    return (
        kling_admin_config_signature(settings),
        wavespeed_admin_config_signature(settings),
        bach_admin_config_signature(settings),
    )


def _load_video_provider_admin_configs(
    settings: Settings,
) -> tuple[tuple[int, int] | None, tuple[int, int] | None, tuple[int, int] | None]:
    load_kling_admin_config(settings)
    load_wavespeed_admin_config(settings)
    load_bach_admin_config(settings)
    return _video_provider_admin_config_signatures(settings)


def _atomic_service_instance_id(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return path.read_text(encoding="ascii").strip()
    value = str(uuid.uuid4())
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(value, encoding="ascii")
    temporary.replace(path)
    return value


async def _freeze_for_disk(session, settings: Settings, reason: str) -> None:
    current = await get_runtime_config(session, settings)
    if current is None:
        return
    config = dict(current.config_json)
    config["globalPaused"] = True
    config["paidSubmissionsPaused"] = True
    if config == current.config_json:
        return
    await update_runtime_config(
        session,
        settings,
        config=config,
        actor_id=None,
        reason=reason,
        expected_version=current.version,
    )


async def _refresh_libtv_auth_state(
    session,
    adapter: LibTVAdapter,
    settings: Settings,
) -> bool:
    if settings.libtv_adapter_mode != "real":
        return True
    try:
        await adapter.check_account()
    except LibTVError as exc:
        if exc.code != "LIBTV_AUTH_REQUIRED":
            logger.warning(
                "LibTV account health check failed without changing auth state: %s",
                exc.code,
            )
            current = await get_runtime_config(session, settings)
            return bool(current and not current.config_json.get("libtvAuthRequired", False))
        await set_libtv_auth_required(
            session,
            settings,
            required=True,
            reason="automatic pause: LibTV account health check requires login",
        )
        return False
    await set_libtv_auth_required(
        session,
        settings,
        required=False,
        reason="LibTV account health check recovered after administrator login",
    )
    return True


async def run_service_loop(stopping: Event, project_root: Path) -> None:
    os.chdir(project_root)
    settings = Settings()
    settings.validate_shared_environment()
    provider_config_signatures = _load_video_provider_admin_configs(settings)
    database = Database(settings.database_url)
    adapter = create_libtv_adapter(settings)
    kling_adapter = create_kling_adapter(settings)
    object_store = create_object_store(settings)
    manager = CommandHostManager(
        settings.runner_root / "command-hosts",
        project_root,
        settings.libtv_executable,
        execution_mode=settings.libtv_execution_mode,
        paid_generation_enabled=settings.paid_generation_enabled,
        paid_generation_confirmation=settings.paid_generation_confirmation,
        app_env=settings.app_env,
        libtv_config_dir=settings.libtv_config_dir,
    )
    manager.ensure_layout()
    service_instance_id = _atomic_service_instance_id(settings.runner_root / "service-instance-id")
    supervisor = RunnerSupervisor(
        adapter,
        object_store,
        settings,
        owner=service_instance_id,
        command_host_manager=manager,
        kling_adapter=kling_adapter,
    )
    last_auth_check = 0.0
    last_metric_sample = 0.0
    last_metric_retention = 0.0
    last_idempotency_sweep = 0.0
    last_launch_recovery = 0.0
    last_orphan_signature: tuple[int, ...] = ()
    try:
        while not stopping.is_set():
            try:
                current_provider_config_signatures = _video_provider_admin_config_signatures(
                    settings
                )
                if current_provider_config_signatures != provider_config_signatures:
                    provider_config_signatures = _load_video_provider_admin_configs(settings)
                    kling_adapter = create_kling_adapter(settings)
                    supervisor.replace_kling_adapter(kling_adapter)
                disk = manager.disk_status(
                    settings.runner_log_disk_warning_percent,
                    settings.runner_log_disk_stop_percent,
                )
                orphans = manager.find_orphan_processes()
                async with database.session_factory() as session:
                    now = time.monotonic()
                    if now - last_auth_check >= settings.libtv_auth_check_seconds:
                        await _refresh_libtv_auth_state(session, adapter, settings)
                        last_auth_check = now
                    host = await session.scalar(
                        select(RunnerHost).where(
                            RunnerHost.service_instance_id == service_instance_id
                        )
                    )
                    status = {
                        "OK": RunnerHostStatus.ONLINE,
                        "WARNING": RunnerHostStatus.WARNING,
                        "STOP": RunnerHostStatus.PAUSED,
                    }[disk["status"]]
                    if host is None:
                        host = RunnerHost(
                            hostname=socket.gethostname(),
                            os_version=platform.platform(),
                            protocol_version=1,
                            service_version="0.2.0",
                            service_instance_id=service_instance_id,
                        )
                        session.add(host)
                        await session.flush()
                    host.status = status
                    host.last_heartbeat_at = datetime.now(UTC)
                    host.free_disk_percent = float(disk["freePercent"])
                    orphan_signature = tuple(sorted(orphans))
                    if orphan_signature:
                        host.status = RunnerHostStatus.WARNING
                        if orphan_signature != last_orphan_signature:
                            session.add(
                                AuditEvent(
                                    actor_id=None,
                                    action="RUNNER_ORPHAN_DETECTED",
                                    entity_type="runner_host",
                                    entity_id=service_instance_id,
                                    reason=f"{len(orphans)} unowned command-host process(es)",
                                    correlation_id=str(uuid.uuid4()),
                                    evidence_refs_json=[],
                                )
                            )
                    last_orphan_signature = orphan_signature
                    if disk["status"] == "STOP":
                        backlog_count = await operational_backlog_count(session)
                        await _freeze_for_disk(
                            session,
                            settings,
                            "automatic stop: runner log volume below disk threshold",
                        )
                        await supervisor.observe_command_hosts(session)
                    else:
                        runtime = await get_runtime_config(session, settings)
                        global_limit = int(
                            (runtime.config_json if runtime else {})
                            .get("generationConcurrency", {})
                            .get("global", 1)
                        )
                        await auto_confirm_pass_tasks(
                            session,
                            adapter,
                            object_store,
                            settings,
                            kling_adapter=kling_adapter,
                            limit=global_limit,
                        )
                        backlog_count = await operational_backlog_count(session)
                        await supervisor.run_ready(session)
                    if now - last_launch_recovery >= 60:
                        # Sits outside the STOP branch on purpose: nothing here submits new
                        # work, it only resolves commands the previous runner abandoned at
                        # LAUNCH_STARTED. Those keep occupying uq_attempt_active_intent, so
                        # the affected task cannot be retried until they are settled.
                        recovered = await supervisor.recover_stale_launch_started_commands(
                            session
                        )
                        if recovered:
                            logger.warning(
                                "resolved commands abandoned between LAUNCH_STARTED and "
                                "PROCESS_STARTED",
                                extra={"count": recovered},
                            )
                        last_launch_recovery = now
                    if now - last_metric_sample >= settings.runner_metric_sample_seconds:
                        await record_operational_sample(
                            session,
                            settings,
                            host,
                            backlog_count=backlog_count,
                            orphan_process_count=len(orphans),
                            free_disk_percent=float(disk["freePercent"]),
                        )
                        last_metric_sample = now
                    if now - last_metric_retention >= 24 * 60 * 60:
                        await prune_operational_samples(
                            session, settings.runner_metric_retention_days
                        )
                        last_metric_retention = now
                    if now - last_idempotency_sweep >= 5 * 60:
                        # Confirmation work is handed to a background job that outlives
                        # the HTTP request owning the idempotency claim. A request that
                        # dies before settling leaves the key at response_status=0, and
                        # every replay then answers 409 IDEMPOTENCY_REQUEST_IN_PROGRESS
                        # for ever. Nothing else in the system ever looks at those rows.
                        confirmation_recovery = await recover_stale_confirmation_claims(
                            session, settings
                        )
                        batch_confirmation_recovery = (
                            await recover_stale_batch_confirmation_claims(session, settings)
                        )
                        released = await release_stale_idempotency_claims(session)
                        if (
                            released
                            or any(confirmation_recovery.values())
                            or any(batch_confirmation_recovery.values())
                        ):
                            logger.warning(
                                "recovered stale idempotency claims",
                                extra={
                                    "released": released,
                                    "confirmation_recovery": confirmation_recovery,
                                    "batch_confirmation_recovery": batch_confirmation_recovery,
                                },
                            )
                        last_idempotency_sweep = now
                    await session.commit()
            except Exception:
                logger.exception("runner service cycle failed")
            await asyncio.to_thread(stopping.wait, settings.runner_poll_seconds)
    finally:
        await database.dispose()
