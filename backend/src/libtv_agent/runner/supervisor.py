import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from libtv_agent.adapters.kling_official_cli import KlingCliError, retry_kling_call
from libtv_agent.adapters.kling_provider import (
    create_kling_adapter,
    create_kling_adapter_for_provider,
)
from libtv_agent.adapters.libtv import GenerationResult, LibTVAdapter, LibTVError
from libtv_agent.adapters.object_store import ObjectStore
from libtv_agent.adapters.video_provider import (
    VideoElementReference,
    VideoGenerationRequest,
    VideoProviderAdapter,
)
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
from libtv_agent.services.provider_errors import clear_provider_error, record_provider_error
from libtv_agent.services.provider_routing import ProviderKind, provider_kind
from libtv_agent.services.runtime_control import (
    provider_claims_allowed,
    set_libtv_auth_required,
)
from libtv_agent.services.state_machine import aggregate_parent_phase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _kling_asset_suffix(filename: str, object_key: str | None) -> str:
    for candidate in (object_key, filename):
        suffix = Path(candidate or "").suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png"}:
            return suffix
    return ".jpg"


def _video_execution_backend(provider: str, settings: Settings) -> str:
    normalized = provider.strip().lower()
    if normalized == settings.wavespeed_video_provider_name.strip().lower():
        return "WAVESPEED_VIDEO_API"
    if normalized in {"kling", settings.kling_api_provider_name.strip().lower()}:
        return "KLING_OFFICIAL_API"
    return "KLING_OFFICIAL_CLI"


def _video_timeout_error(provider: str, settings: Settings) -> tuple[str, str]:
    if provider.strip().lower() == settings.wavespeed_video_provider_name.strip().lower():
        return (
            "WAVESPEED_VIDEO_TASK_TIMEOUT",
            "WaveSpeed video task exceeded the configured wait time; "
            "the remote task was not resubmitted",
        )
    return (
        "KLING_API_TASK_TIMEOUT",
        "Kling API task exceeded the configured wait time; the remote task was not resubmitted",
    )


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
        kling_adapter: VideoProviderAdapter | None = None,
    ) -> None:
        self.adapter = adapter
        self.object_store = object_store
        self.settings = settings
        self.owner = owner
        self.kling_adapter = kling_adapter or create_kling_adapter(settings)
        self._kling_adapters: dict[str, VideoProviderAdapter] = {
            self.kling_adapter.get_provider_name().strip().lower(): self.kling_adapter
        }
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

    def replace_kling_adapter(self, adapter: VideoProviderAdapter) -> None:
        self.kling_adapter = adapter
        # Config reloads must also invalidate inactive adapters used to recover
        # persisted tasks; they are recreated from the task's provider name.
        self._kling_adapters = {
            adapter.get_provider_name().strip().lower(): adapter,
        }

    def _kling_adapter_for(self, provider: str) -> VideoProviderAdapter:
        normalized = provider.strip().lower()
        adapter = self._kling_adapters.get(normalized)
        if adapter is None:
            adapter = create_kling_adapter_for_provider(self.settings, provider)
            self._kling_adapters[normalized] = adapter
        return adapter

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
        # LibTV and Kling have different command semantics and paid-operation
        # recovery rules. Claim each provider queue independently so a blocked
        # provider can never head-of-line block the other.
        processed += await self._run_ready_provider(session, "libtv")
        processed += await self._run_ready_provider(session, "kling")
        return processed

    async def _run_ready_provider(
        self, session: AsyncSession, expected_provider: ProviderKind
    ) -> int:
        processed = 0
        provider_names = (
            ("libtv",) if expected_provider == "libtv" else self.settings.kling_provider_names
        )
        while True:
            commands = list(
                await session.scalars(
                    select(GenerationCommand)
                    .join(GenerationAttempt, GenerationAttempt.id == GenerationCommand.attempt_id)
                    .where(
                        GenerationCommand.status == CommandStatus.READY,
                        GenerationAttempt.provider.in_(provider_names),
                    )
                    .order_by(GenerationCommand.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(20)
                )
            )
            command = None
            for candidate in commands:
                candidate_attempt = await session.get(GenerationAttempt, candidate.attempt_id)
                candidate_variant = (
                    await session.get(GenerationVariant, candidate_attempt.variant_id)
                    if candidate_attempt
                    else None
                )
                candidate_task = (
                    await session.get(ParentTask, candidate_variant.parent_task_id)
                    if candidate_variant
                    else None
                )
                if (
                    candidate_attempt
                    and candidate_task
                    and provider_kind(candidate_attempt.provider, self.settings)
                    == expected_provider
                    and await provider_claims_allowed(
                        session,
                        self.settings,
                        candidate_attempt.provider,
                        user_id=candidate_task.user_id,
                    )
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
            if expected_provider == "kling":
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
                download_adapter=(
                    self._kling_adapter_for(attempt.provider)
                    if attempt.provider != "libtv"
                    else None
                ),
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
            kling_adapter = self._kling_adapter_for(attempt.provider)
            provider_result = await kling_adapter.query(attempt.task_id)
            if provider_result.credits_consumed is not None:
                attempt.credits_consumed = provider_result.credits_consumed
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
        if not self.settings.kling_provider_submission_enabled(attempt.provider):
            await self._handle_error(
                session,
                command,
                attempt,
                KlingCliError(
                    "KLING_LEGACY_PROVIDER_RECOVERY_ONLY",
                    "The Kling CLI Provider may only recover an already-submitted historical task",
                ),
            )
            return True
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
                select(Asset).where(Asset.parent_task_id == task.id).order_by(Asset.order_no)
            )
        )
        storyboard_assets = [
            asset for asset in assets if asset.used_for_generation and asset.role != "PRODUCT"
        ]
        product_reference_assets = [asset for asset in assets if asset.role == "PRODUCT"]
        storyboard_paths: list[Path] = []
        product_reference_paths: list[Path] = []
        kling_adapter = self._kling_adapter_for(attempt.provider)
        try:
            for index, asset in enumerate(storyboard_assets, start=1):
                if not asset.object_key:
                    raise KlingCliError(
                        "KLING_INVALID_INPUT",
                        f"Storyboard asset {asset.id} has no source object",
                    )
                suffix = _kling_asset_suffix(asset.original_filename, asset.object_key)
                storyboard_paths.append(
                    await self.object_store.localize(
                        asset.object_key,
                        self.settings.runner_root
                        / "kling"
                        / "inputs"
                        / str(task.id)
                        / f"storyboard-{index}{suffix}",
                    )
                )
            for index, asset in enumerate(product_reference_assets, start=1):
                if not asset.object_key:
                    raise KlingCliError(
                        "KLING_INVALID_INPUT",
                        f"Product reference asset {asset.id} has no source object",
                    )
                suffix = _kling_asset_suffix(asset.original_filename, asset.object_key)
                product_reference_paths.append(
                    await self.object_store.localize(
                        asset.object_key,
                        self.settings.runner_root
                        / "kling"
                        / "inputs"
                        / str(task.id)
                        / f"product-reference-{index}{suffix}",
                    )
                )
            request = VideoGenerationRequest(
                prompt=variant.prompt_text,
                model=attempt.provider_model or self.settings.active_kling_model,
                image_paths=tuple(storyboard_paths),
                duration=int(
                    variant.generation_config_json.get("duration")
                    or variant.generation_config_json.get("durationSeconds")
                    or self.settings.active_kling_duration
                ),
                aspect_ratio=str(
                    variant.generation_config_json.get("aspectRatio")
                    or self.settings.active_kling_aspect_ratio
                ),
                product_reference_paths=tuple(product_reference_paths),
                fallback_mode=str(
                    variant.generation_config_json.get("storyboardFallbackMode")
                    or self.settings.kling_storyboard_fallback_mode
                ),
                task_trace_id=task.id.hex,
                resolution=str(
                    variant.generation_config_json.get("resolution")
                    or self.settings.kling_api_resolution
                ),
                audio=str(
                    variant.generation_config_json.get("audio")
                    or variant.generation_config_json.get("sound")
                    or self.settings.active_video_audio
                ),
                multi_shot=bool(
                    variant.generation_config_json.get(
                        "multiShot",
                        variant.generation_config_json.get(
                            "smartStoryboard",
                            self.settings.active_video_multi_shot,
                        ),
                    )
                ),
                external_task_id=attempt.intent_hash,
                callback_url=self.settings.kling_api_callback_url,
                element_references=tuple(
                    VideoElementReference(
                        element_id=str(element_id),
                        content_id=f"element_{index}",
                    )
                    for index, element_id in enumerate(
                        variant.generation_config_json.get("elementIds") or (),
                        start=1,
                    )
                ),
            )
            command.status = CommandStatus.LAUNCH_STARTED
            command.launch_started_at = datetime.now(UTC)
            attempt.launch_started_at = command.launch_started_at
            await session.commit()
            submission = await kling_adapter.submit(request)
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
        attempt.runner_execution_backend = _video_execution_backend(
            attempt.provider,
            self.settings,
        )
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
        if not any(
            self.settings.kling_provider_enabled(provider)
            for provider in self.settings.kling_provider_names
        ):
            return 0
        now = datetime.now(UTC)
        attempts = list(
            await session.scalars(
                select(GenerationAttempt)
                .where(
                    GenerationAttempt.provider.in_(self.settings.kling_provider_names),
                    GenerationAttempt.status == AttemptStatus.RUNNING,
                )
                .order_by(GenerationAttempt.last_polled_at, GenerationAttempt.created_at)
                .limit(
                    max(
                        self.settings.kling_cli_max_query_concurrency,
                        self.settings.kling_api_max_poll_concurrency,
                    )
                    * 4
                )
            )
        )
        processed = 0
        for attempt in attempts:
            submitted_at = attempt.submitted_at
            if submitted_at is not None:
                if submitted_at.tzinfo is None:
                    submitted_at = submitted_at.replace(tzinfo=UTC)
                task_timeout = self.settings.video_task_timeout_for_provider(attempt.provider)
                if (
                    task_timeout is not None
                    and (now - submitted_at).total_seconds() >= task_timeout
                ):
                    command = await session.scalar(
                        select(GenerationCommand).where(GenerationCommand.attempt_id == attempt.id)
                    )
                    attempt.status = AttemptStatus.UNKNOWN_AFTER_SUBMIT
                    attempt.provider_status = "unknown"
                    error_code, error_message = _video_timeout_error(
                        attempt.provider,
                        self.settings,
                    )
                    record_provider_error(
                        attempt,
                        code=error_code,
                        message=error_message,
                        details={"providerTaskId": attempt.task_id},
                        retryable=True,
                    )
                    if command is not None:
                        command.status = CommandStatus.UNCERTAIN
                    variant = await session.get(GenerationVariant, attempt.variant_id)
                    if variant is not None:
                        variant.generation_status = GenerationStatus.UNKNOWN
                    await session.commit()
                    if variant is not None:
                        await self._aggregate_task(session, variant.id)
                    processed += 1
                    continue
            last_polled = attempt.last_polled_at
            if last_polled is not None:
                if last_polled.tzinfo is None:
                    last_polled = last_polled.replace(tzinfo=UTC)
                poll_interval = self.settings.kling_poll_interval_for_provider(
                    attempt.provider,
                    unknown=attempt.provider_status == "unknown",
                )
                if (now - last_polled).total_seconds() < poll_interval:
                    continue
            command = await session.scalar(
                select(GenerationCommand).where(GenerationCommand.attempt_id == attempt.id)
            )
            if command is None or not attempt.task_id:
                continue
            if not self.settings.kling_provider_enabled(attempt.provider):
                continue
            kling_adapter = self._kling_adapter_for(attempt.provider)
            try:
                result = await retry_kling_call(
                    lambda attempt=attempt, adapter=kling_adapter: adapter.query(
                        attempt.task_id or ""
                    ),
                    attempts=(
                        self.settings.kling_api_max_retries
                        if attempt.provider == self.settings.kling_api_provider_name
                        else 3
                    ),
                )
            except KlingCliError as exc:
                attempt.last_polled_at = datetime.now(UTC)
                record_provider_error(
                    attempt,
                    code=exc.code,
                    message=str(exc),
                    details=getattr(exc, "details", None),
                    retryable=exc.retryable,
                )
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
            if result.status in {"queued", "running", "succeeded"}:
                clear_provider_error(attempt)
            if result.credits_consumed is not None:
                attempt.credits_consumed = result.credits_consumed
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
                record_provider_error(
                    attempt,
                    code="KLING_REMOTE_STATUS_UNKNOWN",
                    message=f"Kling returned unknown status: {result.raw_status or 'empty'}",
                    details={
                        "providerTaskId": attempt.task_id,
                        "rawStatus": result.raw_status,
                    },
                    retryable=True,
                )
                if variant:
                    variant.generation_status = GenerationStatus.UNKNOWN
                await session.commit()
            elif result.status == "failed":
                attempt.provider_status = "failed"
                attempt.completed_at = datetime.now(UTC)
                record_provider_error(
                    attempt,
                    code="KLING_REMOTE_TASK_FAILED",
                    message=result.message or "Kling remote generation failed",
                    details={
                        "providerTaskId": attempt.task_id,
                        "providerStatus": result.raw_status,
                    },
                    retryable=False,
                )
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
                    download_adapter=kling_adapter,
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
        if attempt.provider != "libtv":
            record_provider_error(
                attempt,
                code=error.code,
                message=str(error),
                details=getattr(error, "details", None),
                retryable=getattr(error, "retryable", None),
            )
        else:
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
        if result.payload:
            attempt.raw_response_json = result.payload
        if attempt.provider != "libtv" and not attempt.error_message:
            record_provider_error(
                attempt,
                code="KLING_REMOTE_TASK_FAILED",
                message="Kling remote generation failed",
                details={"providerTaskId": attempt.task_id},
                retryable=False,
            )
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
        clear_provider_error(attempt)
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
            variant.variant_key or variant.variant_type.value,
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
        expected_duration = float(
            variant.generation_config_json.get("duration")
            or variant.generation_config_json.get("durationSeconds")
            or 10
        )
        expected_ratio = {
            "16:9": 16 / 9,
            "9:16": 9 / 16,
            "1:1": 1.0,
        }.get(str(variant.generation_config_json.get("aspectRatio") or "9:16"), 9 / 16)
        allow_audio = str(
            variant.generation_config_json.get("audio")
            or variant.generation_config_json.get("sound")
            or "off"
        ).lower() in {"native", "original", "on", "true"}
        try:
            await download_with_retries(
                download_adapter or self.adapter,
                url=str(result.payload["videoUrl"]),
                destination=destination,
            )
            validation = await technical_validate(
                destination,
                duration_min=max(0.1, expected_duration - 1),
                duration_max=expected_duration + 1,
                target_ratio=expected_ratio,
                allow_audio=allow_audio,
            )
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
