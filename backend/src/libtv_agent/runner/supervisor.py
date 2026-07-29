import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from libtv_agent.adapters.kling_official_cli import (
    KlingCliError,
    KlingOfficialCliAdapter,
    retry_kling_call,
)
from libtv_agent.adapters.libtv import GenerationResult, LibTVAdapter, LibTVError
from libtv_agent.adapters.object_store import ObjectStore
from libtv_agent.adapters.video_provider import VideoGenerationRequest
from libtv_agent.config import Settings
from libtv_agent.domain.contracts import delivery_filename
from libtv_agent.domain.enums import (
    AttemptStatus,
    BillingSource,
    ChargeStatus,
    CommandStatus,
    DownloadStatus,
    GenerationStatus,
    ParentTaskPhase,
    ValidationStatus,
)
from libtv_agent.domain.models import (
    Asset,
    DownloadArtifact,
    GenerationAttempt,
    GenerationCommand,
    GenerationVariant,
    ParentTask,
    PointsReservation,
    ValidationResult,
)
from libtv_agent.runner.command_host_manager import CommandHostManager
from libtv_agent.services.capacity import acquire_capacity, release_capacity, renew_capacity
from libtv_agent.services.generation_safety import (
    PaidGenerationBlockedError,
    require_paid_generation_authorized,
)
from libtv_agent.services.media import download_with_retries, technical_validate
from libtv_agent.services.points import business_date, settle_points
from libtv_agent.services.runtime_control import (
    provider_claims_allowed,
    set_libtv_auth_required,
)
from libtv_agent.services.state_machine import aggregate_parent_phase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessIdentity:
    command_host_id: str
    process_id: int
    process_started_at: str
    nonce: str
    executable_hash: str
    command_hash: str


def process_identity_matches(expected: ProcessIdentity, observed: ProcessIdentity) -> bool:
    return expected == observed


def classify_recovery(
    *,
    launch_started: bool,
    command_host_alive: bool,
    identity_matches: bool,
    terminal_result_valid: bool,
    host_restarted: bool,
    log_writable: bool = True,
) -> str:
    if terminal_result_valid:
        return "TERMINAL"
    if host_restarted and launch_started:
        return "RECOVERY_AUDIT"
    if command_host_alive and identity_matches:
        return "RUNNING"
    if command_host_alive and not identity_matches:
        return "MANUAL_REVIEW"
    if launch_started or not log_writable:
        return "UNKNOWN"
    return "READY"


class RunnerSupervisor:
    def __init__(
        self,
        adapter: LibTVAdapter,
        object_store: ObjectStore,
        settings: Settings,
        owner: str = "phase-one-runner",
        command_host_manager: CommandHostManager | None = None,
        kling_adapter: KlingOfficialCliAdapter | None = None,
    ) -> None:
        self.adapter = adapter
        self.object_store = object_store
        self.settings = settings
        self.owner = owner
        self.kling_adapter = kling_adapter or KlingOfficialCliAdapter(settings)
        self.command_host_manager = command_host_manager or CommandHostManager(
            settings.runner_root / "command-hosts",
            Path(__file__).resolve().parents[4],
            settings.libtv_executable,
            execution_mode=settings.libtv_execution_mode,
            paid_generation_enabled=settings.paid_generation_enabled,
            paid_generation_confirmation=settings.paid_generation_confirmation,
            app_env=settings.app_env,
            libtv_config_dir=settings.libtv_config_dir,
        )

    async def _release_capacity_if_charge_classified(
        self,
        session: AsyncSession,
        command: GenerationCommand,
        attempt: GenerationAttempt,
    ) -> bool:
        if attempt.charge_status == ChargeStatus.UNKNOWN:
            return False
        await release_capacity(session, command.id)
        return True

    async def run_ready(self, session: AsyncSession) -> int:
        processed = 0
        processed += await self.resume_incomplete_downloads(session)
        await self.observe_command_hosts(session)
        processed += await self.poll_kling_tasks(session)
        while True:
            commands = list(
                await session.scalars(
                    select(GenerationCommand)
                    .join(GenerationAttempt, GenerationAttempt.id == GenerationCommand.attempt_id)
                    .where(GenerationCommand.status == CommandStatus.READY)
                    .order_by(GenerationCommand.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(20)
                )
            )
            command = None
            for candidate in commands:
                candidate_attempt = await session.get(GenerationAttempt, candidate.attempt_id)
                if candidate_attempt and await provider_claims_allowed(
                    session, self.settings, candidate_attempt.provider
                ):
                    command = candidate
                    break
            if command is None:
                break
            lease = await acquire_capacity(session, self.settings, command)
            if lease is None:
                await session.rollback()
                break
            command.status = CommandStatus.CLAIMED
            command.claim_owner = self.owner
            command.lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
            attempt = await session.get(GenerationAttempt, command.attempt_id)
            if attempt is None or attempt.status != AttemptStatus.DISPATCH_PENDING:
                command.status = CommandStatus.CANCELLED
                await release_capacity(session, command.id)
                await session.commit()
                continue
            attempt.status = AttemptStatus.LAUNCHING
            attempt.state_version += 1
            await session.commit()
            terminal = await self._execute(session, command.id)
            if attempt.provider != "libtv":
                await release_capacity(session, command.id)
                await session.commit()
            elif terminal:
                await self._release_capacity_if_charge_classified(session, command, attempt)
                await session.commit()
            processed += 1
        return processed

    async def resume_incomplete_downloads(self, session: AsyncSession) -> int:
        variants = list(
            await session.scalars(
                select(GenerationVariant)
                .where(GenerationVariant.download_status == DownloadStatus.DOWNLOADING)
                .order_by(GenerationVariant.created_at)
                .limit(10)
            )
        )
        for variant in variants:
            await self._aggregate_task(session, variant.id)

        resumed = 0
        for variant in variants:
            attempt = await session.scalar(
                select(GenerationAttempt)
                .where(GenerationAttempt.variant_id == variant.id)
                .order_by(GenerationAttempt.created_at.desc())
                .limit(1)
            )
            if attempt is None:
                continue
            command = await session.scalar(
                select(GenerationCommand).where(GenerationCommand.attempt_id == attempt.id)
            )
            if command is None:
                continue
            payload = dict(attempt.raw_response_json or {})
            output_url = str(payload.get("videoUrl") or attempt.output_url or "")
            if not output_url:
                variant.download_status = DownloadStatus.FAILED
                variant.validation_status = ValidationStatus.FAILED
                attempt.last_error_code = "DOWNLOAD_SOURCE_MISSING"
                await session.commit()
                await self._aggregate_task(session, variant.id)
                resumed += 1
                continue
            payload["videoUrl"] = output_url
            await self._handle_success(
                session,
                command,
                attempt,
                GenerationResult(status="SUCCEEDED", payload=payload),
                download_adapter=self.kling_adapter if attempt.provider != "libtv" else None,
                generation_status=(
                    variant.generation_status
                    if variant.generation_status
                    in {
                        GenerationStatus.SUCCEEDED,
                        GenerationStatus.PARTIAL,
                    }
                    else GenerationStatus.SUCCEEDED
                ),
            )
            resumed += 1
        return resumed

    async def reconcile_attempt(self, session: AsyncSession, attempt_id: uuid.UUID) -> str:
        attempt = await session.get(GenerationAttempt, attempt_id)
        if attempt is None or attempt.status != AttemptStatus.UNKNOWN_AFTER_SUBMIT:
            raise ValueError("attempt is not UNKNOWN_AFTER_SUBMIT")
        command = await session.scalar(
            select(GenerationCommand).where(GenerationCommand.attempt_id == attempt.id)
        )
        if command is None:
            raise ValueError("generation command is missing")
        if attempt.provider != "libtv":
            if not attempt.task_id:
                raise ValueError("Kling generationId is missing")
            provider_result = await self.kling_adapter.query(attempt.task_id)
            result = GenerationResult(
                status=provider_result.status.upper(),
                payload={
                    **provider_result.raw_response,
                    "taskId": attempt.task_id,
                    "videoUrl": provider_result.outputs[0].url if provider_result.outputs else None,
                },
            )
        else:
            result = await self.adapter.query_node_result(
                project_uuid=attempt.project_uuid or "",
                node_key=attempt.video_node_key or "",
            )
        if result.status == "SUCCEEDED":
            await self._handle_success(session, command, attempt, result)
            await self._release_capacity_if_charge_classified(session, command, attempt)
            await session.commit()
        elif result.status == "FAILED":
            await self._handle_terminal_failure(session, command, attempt, result)
            await self._release_capacity_if_charge_classified(session, command, attempt)
            await session.commit()
        return result.status

    async def _execute(self, session: AsyncSession, command_id: uuid.UUID) -> bool:
        command = await session.get(GenerationCommand, command_id)
        if command is None:
            return True
        attempt = await session.get(GenerationAttempt, command.attempt_id)
        if attempt is None:
            return True
        if attempt.provider != "libtv":
            return await self._execute_kling(session, command, attempt)
        if self.settings.libtv_adapter_mode == "real":
            try:
                require_paid_generation_authorized(self.settings)
            except PaidGenerationBlockedError as exc:
                await self._handle_error(
                    session,
                    command,
                    attempt,
                    LibTVError(exc.code, str(exc)),
                )
                return True
        command.status = CommandStatus.LAUNCH_STARTED
        command.launch_started_at = datetime.now(UTC)
        attempt.launch_started_at = command.launch_started_at
        await session.commit()
        if self.settings.libtv_adapter_mode == "real":
            try:
                manifest = self.command_host_manager.launch_generation(
                    str(command.id), attempt.project_uuid or "", attempt.video_node_key or ""
                )
            except Exception as exc:
                await self._handle_error(
                    session,
                    command,
                    attempt,
                    LibTVError(
                        "COMMAND_HOST_LAUNCH_UNCERTAIN",
                        str(exc),
                        submitted=True,
                        uncertain=True,
                    ),
                )
                return False
            command.status = CommandStatus.PROCESS_STARTED
            command.process_started_at = datetime.now(UTC)
            attempt.process_started_at = command.process_started_at
            attempt.status = AttemptStatus.RUNNING
            attempt.state_version += 1
            attempt.runner_execution_backend = "WINDOWS_COMMAND_HOST"
            attempt.runner_execution_ref = str(
                self.command_host_manager.manifest_path(str(command.id))
            )
            attempt.runner_process_id = manifest.pid
            attempt.runner_process_started_at = datetime.fromtimestamp(
                manifest.process_started_at, tz=UTC
            )
            attempt.runner_process_nonce = manifest.nonce
            attempt.runner_executable_hash = manifest.executable_hash
            attempt.runner_command_hash = manifest.command_hash
            attempt.stdout_ref = manifest.stdout_file
            attempt.stderr_ref = manifest.stderr_file
            attempt.terminal_result_ref = manifest.result_file
            variant = await session.get(GenerationVariant, attempt.variant_id)
            if variant is not None:
                variant.generation_status = GenerationStatus.RUNNING
            await session.commit()
            await self._aggregate_task(session, attempt.variant_id)
            return False
        command.status = CommandStatus.PROCESS_STARTED
        command.process_started_at = datetime.now(UTC)
        attempt.process_started_at = command.process_started_at
        attempt.status = AttemptStatus.RUNNING
        attempt.state_version += 1
        attempt.runner_execution_backend = (
            "FAKE_IN_PROCESS" if self.settings.libtv_adapter_mode == "fake" else "REPLAY_IN_PROCESS"
        )
        attempt.runner_execution_ref = str(command.id)
        variant = await session.get(GenerationVariant, attempt.variant_id)
        if variant is not None:
            variant.generation_status = GenerationStatus.RUNNING
        await session.commit()
        await self._aggregate_task(session, attempt.variant_id)
        working_directory = self.settings.runner_root / str(command.id)
        working_directory.mkdir(parents=True, exist_ok=True)
        try:
            result = await self.adapter.run_generation(
                project_uuid=attempt.project_uuid or "",
                node=attempt.video_node_key or "",
                working_directory=working_directory,
            )
        except LibTVError as exc:
            await self._handle_error(session, command, attempt, exc)
            return True
        if result.status != "SUCCEEDED":
            await self._handle_terminal_failure(session, command, attempt, result)
            return True
        await self._handle_success(session, command, attempt, result)
        return True

    async def _execute_kling(
        self,
        session: AsyncSession,
        command: GenerationCommand,
        attempt: GenerationAttempt,
    ) -> bool:
        variant = await session.get(GenerationVariant, attempt.variant_id)
        if variant is None:
            await self._handle_error(
                session,
                command,
                attempt,
                KlingCliError("KLING_INVALID_INPUT", "generation variant is unavailable"),
            )
            return True
        task = await session.get(ParentTask, variant.parent_task_id)
        if task is None:
            await self._handle_error(
                session,
                command,
                attempt,
                KlingCliError("KLING_INVALID_INPUT", "parent task is unavailable"),
            )
            return True
        assets = list(
            await session.scalars(
                select(Asset)
                .where(
                    Asset.parent_task_id == task.id,
                    Asset.used_for_generation.is_(True),
                )
                .order_by(Asset.order_no)
            )
        )
        paths: list[Path] = []
        try:
            for asset in assets:
                if not asset.object_key:
                    raise KlingCliError(
                        "KLING_INVALID_INPUT",
                        f"Storyboard asset {asset.id} has no source object",
                    )
                suffix = Path(asset.original_filename).suffix.lower()
                if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                    suffix = ".jpg"
                paths.append(
                    await self.object_store.localize(
                        asset.object_key,
                        self.settings.runner_root
                        / "kling"
                        / "inputs"
                        / str(task.id)
                        / f"asset-{asset.order_no}{suffix}",
                    )
                )
            request = VideoGenerationRequest(
                prompt=variant.prompt_text,
                model=attempt.provider_model or self.settings.kling_cli_default_model,
                image_paths=tuple(paths),
                duration=int(
                    variant.generation_config_json.get("duration")
                    or self.settings.kling_cli_default_duration
                ),
                aspect_ratio=str(
                    variant.generation_config_json.get("aspectRatio")
                    or self.settings.kling_cli_default_aspect_ratio
                ),
                fallback_mode=str(
                    variant.generation_config_json.get("storyboardFallbackMode")
                    or self.settings.kling_storyboard_fallback_mode
                ),
                task_trace_id=task.id.hex,
            )
            command.status = CommandStatus.LAUNCH_STARTED
            command.launch_started_at = datetime.now(UTC)
            attempt.launch_started_at = command.launch_started_at
            await session.commit()
            submission = await self.kling_adapter.submit(request)
        except KlingCliError as exc:
            await self._handle_error(session, command, attempt, exc)
            return True

        now = datetime.now(UTC)
        attempt.task_id = submission.provider_task_id
        attempt.provider_model = submission.provider_model
        attempt.provider_status = "queued"
        attempt.provider_raw_status = submission.raw_status
        attempt.submitted_at = now
        attempt.last_polled_at = None
        attempt.credits_consumed = submission.credits_consumed
        attempt.raw_response_json = submission.raw_response
        attempt.status = AttemptStatus.RUNNING
        attempt.state_version += 1
        attempt.charge_status = (
            ChargeStatus.CHARGED
            if submission.credits_consumed is not None
            else ChargeStatus.UNKNOWN
        )
        if submission.credits_consumed is not None:
            attempt.billing_source = BillingSource.TASK_BILLING
        attempt.runner_execution_backend = "KLING_OFFICIAL_CLI"
        attempt.runner_execution_ref = submission.provider_task_id
        command.status = CommandStatus.PROCESS_STARTED
        command.process_started_at = now
        command.lease_expires_at = None
        variant.generation_status = GenerationStatus.RUNNING
        task.phase = ParentTaskPhase.GENERATING
        task.state_version += 1
        await session.commit()
        return False

    async def poll_kling_tasks(self, session: AsyncSession) -> int:
        if not self.settings.kling_cli_enabled:
            return 0
        now = datetime.now(UTC)
        attempts = list(
            await session.scalars(
                select(GenerationAttempt)
                .where(
                    GenerationAttempt.provider == self.settings.kling_cli_provider_name,
                    GenerationAttempt.status == AttemptStatus.RUNNING,
                )
                .order_by(GenerationAttempt.last_polled_at, GenerationAttempt.created_at)
                .limit(self.settings.kling_cli_max_query_concurrency * 4)
            )
        )
        processed = 0
        for attempt in attempts:
            last_polled = attempt.last_polled_at
            if last_polled is not None:
                if last_polled.tzinfo is None:
                    last_polled = last_polled.replace(tzinfo=UTC)
                poll_interval = (
                    self.settings.kling_cli_max_poll_interval_seconds
                    if attempt.provider_status == "unknown"
                    else self.settings.kling_cli_poll_interval_seconds
                )
                if (now - last_polled).total_seconds() < poll_interval:
                    continue
            command = await session.scalar(
                select(GenerationCommand).where(GenerationCommand.attempt_id == attempt.id)
            )
            if command is None or not attempt.task_id:
                continue
            try:
                result = await retry_kling_call(
                    lambda attempt=attempt: self.kling_adapter.query(attempt.task_id or ""),
                    attempts=3,
                )
            except KlingCliError as exc:
                attempt.last_polled_at = datetime.now(UTC)
                attempt.last_error_code = exc.code
                attempt.error_message = str(exc)
                if not exc.retryable:
                    attempt.status = AttemptStatus.UNKNOWN_AFTER_SUBMIT
                    attempt.provider_status = "unknown"
                    command.status = CommandStatus.UNCERTAIN
                    variant = await session.get(GenerationVariant, attempt.variant_id)
                    if variant:
                        variant.generation_status = GenerationStatus.UNKNOWN
                        await self._aggregate_task(session, variant.id)
                await session.commit()
                processed += 1
                continue

            attempt.last_polled_at = datetime.now(UTC)
            attempt.provider_status = result.status
            attempt.provider_raw_status = result.raw_status
            attempt.raw_response_json = result.raw_response
            variant = await session.get(GenerationVariant, attempt.variant_id)
            if result.status in {"queued", "running"}:
                if variant:
                    variant.generation_status = GenerationStatus.RUNNING
                await session.commit()
                if variant:
                    await self._aggregate_task(session, variant.id)
            elif result.status == "unknown":
                logger.warning(
                    "Kling task returned an unknown status",
                    extra={
                        "attempt_id": str(attempt.id),
                        "raw_status": result.raw_status,
                    },
                )
                attempt.last_error_code = "KLING_REMOTE_STATUS_UNKNOWN"
                if variant:
                    variant.generation_status = GenerationStatus.UNKNOWN
                await session.commit()
            elif result.status == "failed":
                attempt.provider_status = "failed"
                attempt.completed_at = datetime.now(UTC)
                attempt.error_message = "Kling remote generation failed"
                await self._handle_terminal_failure(
                    session,
                    command,
                    attempt,
                    GenerationResult(
                        status="FAILED",
                        payload={
                            **result.raw_response,
                            "taskId": attempt.task_id,
                        },
                    ),
                )
            else:
                output = result.outputs[0]
                attempt.output_url = output.url
                attempt.completed_at = datetime.now(UTC)
                await self._handle_success(
                    session,
                    command,
                    attempt,
                    GenerationResult(
                        status="SUCCEEDED",
                        payload={
                            **result.raw_response,
                            "taskId": attempt.task_id,
                            "videoUrl": output.url,
                            "actualPoints": attempt.credits_consumed,
                            "billingSource": "TASK_BILLING",
                        },
                    ),
                    download_adapter=self.kling_adapter,
                    generation_status=(
                        GenerationStatus.PARTIAL
                        if result.status == "partial"
                        else GenerationStatus.SUCCEEDED
                    ),
                )
            processed += 1
        return processed

    async def observe_command_hosts(self, session: AsyncSession) -> int:
        if self.settings.libtv_adapter_mode != "real":
            return 0
        commands = list(
            await session.scalars(
                select(GenerationCommand).where(
                    GenerationCommand.status == CommandStatus.PROCESS_STARTED,
                    GenerationCommand.attempt_id.in_(
                        select(GenerationAttempt.id).where(GenerationAttempt.provider == "libtv")
                    ),
                )
            )
        )
        observed = 0
        for command in commands:
            attempt = await session.get(GenerationAttempt, command.attempt_id)
            if attempt is None:
                continue
            try:
                state = self.command_host_manager.observe(str(command.id))
            except (OSError, ValueError):
                state = None
            if state is not None and state.status == "RUNNING":
                await renew_capacity(session, command.id)
                await session.commit()
                await self._aggregate_task(session, attempt.variant_id)
                observed += 1
                continue
            if state is not None and state.status == "TERMINAL" and state.terminal_result:
                terminal = state.terminal_result
                if terminal.get("ok"):
                    result = GenerationResult(**terminal["result"])
                    if result.status == "SUCCEEDED":
                        await self._handle_success(session, command, attempt, result)
                    else:
                        await self._handle_terminal_failure(session, command, attempt, result)
                    await self._release_capacity_if_charge_classified(session, command, attempt)
                    await session.commit()
                else:
                    error_payload = terminal.get("error")
                    if isinstance(error_payload, dict):
                        terminal_error = LibTVError(
                            str(error_payload.get("code") or "COMMAND_HOST_TERMINAL_ERROR"),
                            str(error_payload.get("message") or "command-host failed"),
                            submitted=bool(error_payload.get("submitted")),
                            uncertain=bool(error_payload.get("uncertain")),
                        )
                    else:
                        terminal_error = LibTVError(
                            "COMMAND_HOST_TERMINAL_ERROR",
                            str(error_payload or "command-host failed"),
                            submitted=True,
                            uncertain=True,
                        )
                    await self._handle_error(
                        session,
                        command,
                        attempt,
                        terminal_error,
                    )
            else:
                code = f"COMMAND_HOST_{state.status}" if state is not None else "COMMAND_HOST_LOST"
                await self._handle_error(
                    session,
                    command,
                    attempt,
                    LibTVError(
                        code,
                        "command-host identity or result is uncertain",
                        submitted=True,
                        uncertain=True,
                    ),
                )
            observed += 1
        return observed

    async def _handle_error(
        self,
        session: AsyncSession,
        command: GenerationCommand,
        attempt: GenerationAttempt,
        error: LibTVError | KlingCliError,
    ) -> None:
        if error.code == "LIBTV_AUTH_REQUIRED":
            await set_libtv_auth_required(
                session,
                self.settings,
                required=True,
                reason="automatic pause: LibTV CLI reported an expired login",
            )
        reservation = await session.scalar(
            select(PointsReservation).where(PointsReservation.attempt_id == attempt.id)
        )
        if error.submitted or error.uncertain:
            attempt.status = AttemptStatus.UNKNOWN_AFTER_SUBMIT
            attempt.charge_status = ChargeStatus.UNKNOWN
            command.status = CommandStatus.UNCERTAIN
            if reservation:
                await settle_points(
                    session, reservation, actual_points=None, charge_status=ChargeStatus.UNKNOWN
                )
            variant = await session.get(GenerationVariant, attempt.variant_id)
            if variant:
                variant.generation_status = GenerationStatus.UNKNOWN
        else:
            attempt.status = AttemptStatus.FAILED_BEFORE_SUBMIT
            command.status = CommandStatus.TERMINAL
            if reservation:
                await settle_points(
                    session, reservation, actual_points=None, charge_status=ChargeStatus.NOT_CHARGED
                )
            variant = await session.get(GenerationVariant, attempt.variant_id)
            if variant:
                variant.generation_status = GenerationStatus.FAILED
        attempt.last_error_code = error.code
        attempt.error_message = str(error)
        if attempt.provider != "libtv":
            attempt.provider_status = "unknown" if error.submitted or error.uncertain else "failed"
        attempt.state_version += 1
        await session.commit()
        await self._aggregate_task(session, attempt.variant_id)

    async def _handle_terminal_failure(
        self,
        session: AsyncSession,
        command: GenerationCommand,
        attempt: GenerationAttempt,
        result: GenerationResult,
    ) -> None:
        attempt.status = AttemptStatus.FAILED_TERMINAL
        attempt.task_id = str(result.payload.get("taskId") or "")
        attempt.last_error_code = (
            "KLING_REMOTE_TASK_FAILED"
            if attempt.provider != "libtv"
            else "GENERATION_TERMINAL_FAILED"
        )
        attempt.provider_status = "failed"
        attempt.completed_at = attempt.completed_at or datetime.now(UTC)
        attempt.raw_response_json = result.payload
        command.status = CommandStatus.TERMINAL
        reservation = await session.scalar(
            select(PointsReservation).where(PointsReservation.attempt_id == attempt.id)
        )
        if reservation:
            if attempt.provider != "libtv":
                charge_status = attempt.charge_status
            else:
                charge_status = (
                    ChargeStatus.UNKNOWN
                    if self.settings.libtv_adapter_mode == "real"
                    else ChargeStatus.NOT_CHARGED
                )
            attempt.charge_status = charge_status
            await settle_points(
                session, reservation, actual_points=None, charge_status=charge_status
            )
        variant = await session.get(GenerationVariant, attempt.variant_id)
        if variant:
            variant.generation_status = GenerationStatus.FAILED
        await session.commit()
        await self._aggregate_task(session, attempt.variant_id)

    async def _handle_success(
        self,
        session: AsyncSession,
        command: GenerationCommand,
        attempt: GenerationAttempt,
        result: GenerationResult,
        *,
        download_adapter: object | None = None,
        generation_status: GenerationStatus = GenerationStatus.SUCCEEDED,
    ) -> None:
        attempt.status = AttemptStatus.SUCCEEDED
        attempt.task_id = str(result.payload.get("taskId") or "")
        attempt.provider_status = (
            "partial" if generation_status == GenerationStatus.PARTIAL else "succeeded"
        )
        attempt.completed_at = attempt.completed_at or datetime.now(UTC)
        attempt.output_url = str(result.payload.get("videoUrl") or attempt.output_url or "")
        attempt.raw_response_json = result.payload
        actual_points = result.payload.get("actualPoints")
        billing_source = result.payload.get("billingSource")
        has_attributable_billing = (
            isinstance(actual_points, int)
            and not isinstance(actual_points, bool)
            and actual_points >= 0
            and billing_source in {"TASK_BILLING", "PRICE_SNAPSHOT"}
        )
        if attempt.provider == "libtv" and self.settings.libtv_adapter_mode != "real":
            has_attributable_billing = True
            actual_points = None
            billing_source = "PRICE_SNAPSHOT"
        elif attempt.provider != "libtv":
            has_attributable_billing = attempt.credits_consumed is not None
            actual_points = attempt.credits_consumed
            billing_source = "TASK_BILLING" if has_attributable_billing else None
        attempt.charge_status = (
            ChargeStatus.CHARGED if has_attributable_billing else ChargeStatus.UNKNOWN
        )
        attempt.billing_source = BillingSource(billing_source) if has_attributable_billing else None
        command.status = CommandStatus.TERMINAL
        command.lease_expires_at = None
        variant = await session.get(GenerationVariant, attempt.variant_id)
        if variant is None:
            return
        variant.generation_status = generation_status
        variant.download_status = DownloadStatus.DOWNLOADING
        await session.commit()
        await self._aggregate_task(session, variant.id)
        task = await session.get(ParentTask, variant.parent_task_id)
        if task is None:
            return
        filename = delivery_filename(
            business_date().isoformat(),
            str(task.user_id),
            str(task.id),
            variant.variant_type.value,
            variant.revision,
        )
        destination = self.settings.runner_root / "downloads" / str(task.id) / filename
        existing_artifact = await session.scalar(
            select(DownloadArtifact)
            .where(
                DownloadArtifact.attempt_id == attempt.id,
                DownloadArtifact.status == DownloadStatus.READY,
            )
            .order_by(DownloadArtifact.revision.desc())
            .limit(1)
        )
        if existing_artifact is not None:
            variant.download_status = DownloadStatus.READY
            await session.commit()
            await self._aggregate_task(session, variant.id)
            return
        try:
            await download_with_retries(
                download_adapter or self.adapter,
                url=str(result.payload["videoUrl"]),
                destination=destination,
            )
            validation = await technical_validate(destination)
        except Exception:
            variant.download_status = DownloadStatus.FAILED
            variant.validation_status = ValidationStatus.FAILED
            attempt.last_error_code = "DOWNLOAD_RETRYABLE"
            await session.commit()
            await self._aggregate_task(session, variant.id)
            return
        attempt.local_output_path = str(destination)
        object_key = await self.object_store.put_file(
            destination,
            f"users/{task.user_id}/outputs/{task.id}/{filename}",
            "video/mp4",
        )
        artifact = DownloadArtifact(
            attempt_id=attempt.id,
            status=DownloadStatus.READY,
            object_key=object_key,
            sha256=validation.sha256,
            size_bytes=validation.size_bytes,
            duration_seconds=validation.duration_seconds,
            width=validation.width,
            height=validation.height,
            has_audio=validation.has_audio,
        )
        session.add(artifact)
        variant.download_status = DownloadStatus.READY
        variant.validation_status = (
            ValidationStatus.PASSED if validation.passed else ValidationStatus.FAILED
        )
        session.add(
            ValidationResult(
                attempt_id=attempt.id,
                status=variant.validation_status,
                coverage="TECHNICAL",
                rule_version="1.0.0",
                issue_codes_json=list(validation.issue_codes),
                summary="Technical validation passed"
                if validation.passed
                else "Technical validation failed",
            )
        )
        reservation = await session.scalar(
            select(PointsReservation).where(PointsReservation.attempt_id == attempt.id)
        )
        if reservation:
            await settle_points(
                session,
                reservation,
                actual_points=(
                    reservation.estimated_points if actual_points is None else int(actual_points)
                )
                if has_attributable_billing
                else None,
                charge_status=attempt.charge_status,
            )
        await session.commit()
        await self._aggregate_task(session, variant.id)

    async def _aggregate_task(self, session: AsyncSession, variant_id: uuid.UUID) -> None:
        variant = await session.get(GenerationVariant, variant_id)
        if variant is None:
            return
        task = await session.get(ParentTask, variant.parent_task_id)
        if task is None:
            return
        variants = list(
            await session.scalars(
                select(GenerationVariant).where(GenerationVariant.parent_task_id == task.id)
            )
        )
        next_phase = aggregate_parent_phase(variants)
        if task.phase != next_phase:
            task.phase = next_phase
            task.state_version += 1
            await session.commit()
