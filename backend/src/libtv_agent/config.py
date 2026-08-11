from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path.cwd() / ".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_public_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    deployment_id: str = "libtv-agent-development"
    deployment_source_revision: str = "unknown"
    shared_authentication_enabled: bool = False

    database_url: str = "postgresql+asyncpg://libtv_agent:libtv_agent@localhost:5432/libtv_agent"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "libtv_agent"
    minio_secret_key: str = "change-me-before-shared-use"
    minio_secure: bool = False
    minio_bucket: str = "libtv-agent"
    object_store_prefix: str = "development"
    object_store_mode: Literal["local", "minio"] = "minio"

    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-5.6-luna"
    openai_analysis_fallback_model: str | None = "gpt-5.6-terra"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "none"
    openai_analysis_fallback_reasoning_effort: Literal[
        "none", "low", "medium", "high", "xhigh", "max"
    ] = "low"
    openai_analysis_verbosity: Literal["low", "medium", "high"] = "low"
    openai_analysis_max_output_tokens: int = Field(default=4000, ge=1000, le=128_000)
    openai_analysis_fallback_max_output_tokens: int = Field(default=6000, ge=1000, le=128_000)
    openai_analysis_timeout_seconds: float = Field(default=180.0, gt=0, le=900)
    openai_analysis_timeout_base_image_count: int = Field(default=4, ge=1, le=20)
    openai_analysis_timeout_per_extra_image_seconds: float = Field(default=45.0, ge=0, le=300)
    openai_analysis_timeout_max_seconds: float = Field(default=600.0, gt=0, le=1800)
    analysis_stale_after_seconds: float = Field(default=660.0, gt=0, le=3600)
    analysis_recovery_poll_seconds: float = Field(default=30.0, gt=0, le=300)
    analysis_shutdown_grace_seconds: float = Field(default=15.0, gt=0, le=300)
    materialization_stale_after_seconds: float = Field(default=300.0, gt=0, le=3600)
    feedback_learning_enabled: bool = True
    feedback_learning_llm_enabled: bool = True
    feedback_learning_max_history: int = Field(default=40, ge=1, le=200)
    feedback_learning_max_attempts: int = Field(default=3, ge=1, le=10)
    ai_adapter_mode: Literal["fake", "replay", "openai"] = "fake"
    ai_replay_fixture: Path = Path("backend/tests/fixtures/ai/analysis.json")

    libtv_adapter_mode: Literal["fake", "replay", "real"] = "fake"
    libtv_access_key: str | None = None
    libtv_execution_mode: Literal["dry-run", "prepare-only", "live"] = "dry-run"
    paid_generation_enabled: bool = False
    paid_generation_confirmation: str = ""
    libtv_executable: str = "libtv"
    libtv_config_dir: Path = Path("var/runtime/libtv")
    libtv_auth_check_seconds: float = Field(default=60.0, ge=10, le=3600)
    libtv_download_helper: Path = (
        Path.home() / ".codex" / "skills" / "libtv-cli" / "scripts" / "download-libtv-video.ps1"
    )
    libtv_replay_fixture_dir: Path = Path("backend/tests/fixtures/libtv")
    libtv_workspace_id: str | None = None
    libtv_project_uuid: str | None = None
    fake_libtv_scenario: str = "success"
    # CLI remains recovery-only. New work can be routed to either the Kling
    # official API or WaveSpeed without changing persisted historical attempts.
    kling_provider_backend: Literal["cli", "api", "wavespeed"] = "api"
    kling_cli_enabled: bool = False
    kling_cli_executable: str = "kling"
    kling_cli_provider_name: str = "kling_official_cli"
    kling_cli_default_model: str | None = None
    kling_cli_default_duration: int = Field(default=10, ge=1, le=60)
    kling_cli_default_aspect_ratio: str = "9:16"
    kling_cli_command_timeout_ms: int = Field(default=30_000, ge=1_000, le=600_000)
    kling_cli_query_timeout_ms: int = Field(default=30_000, ge=1_000, le=600_000)
    kling_cli_download_timeout_ms: int = Field(default=300_000, ge=1_000, le=1_800_000)
    kling_cli_global_qps: float = Field(default=4.0, gt=0, le=20)
    kling_cli_max_submit_concurrency: int = Field(default=1, ge=1, le=4)
    kling_cli_max_query_concurrency: int = Field(default=4, ge=1, le=16)
    kling_cli_poll_interval_seconds: float = Field(default=20.0, ge=2, le=300)
    kling_cli_max_poll_interval_seconds: float = Field(default=60.0, ge=2, le=600)
    kling_storyboard_fallback_mode: Literal["disabled", "first_last_frame"] = "disabled"
    kling_cli_capability_cache_seconds: int = Field(default=3600, ge=60, le=86_400)
    kling_enable_paid_integration_test: bool = False
    kling_api_enabled: bool = False
    kling_api_key: str | None = None
    kling_api_base_url: str = "https://api-beijing.klingai.com"
    kling_api_provider_name: str = "kling_official_api"
    kling_api_model: Literal["kling-3.0-omni"] = "kling-3.0-omni"
    kling_api_duration: int = Field(default=10, ge=3, le=15)
    kling_api_aspect_ratio: Literal["16:9", "9:16", "1:1"] = "9:16"
    kling_api_resolution: Literal["720p", "1080p", "4k"] = "1080p"
    kling_api_audio: Literal["native", "original", "off"] = "off"
    kling_api_multi_shot: bool = True
    kling_api_callback_url: str | None = None
    kling_api_request_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    kling_api_task_timeout_seconds: float = Field(default=1800.0, ge=60, le=86_400)
    kling_api_download_timeout_seconds: float = Field(default=300.0, gt=0, le=1800)
    kling_api_max_submit_concurrency: int = Field(default=1, ge=1, le=20)
    kling_api_max_poll_concurrency: int = Field(default=4, ge=1, le=50)
    kling_api_poll_interval_seconds: float = Field(default=20.0, ge=1, le=300)
    kling_api_max_poll_interval_seconds: float = Field(default=60.0, ge=1, le=600)
    kling_api_max_retries: int = Field(default=3, ge=1, le=8)
    kling_api_enable_paid_integration_test: bool = False
    wavespeed_enabled: bool = False
    wavespeed_api_key: str | None = None
    # Populated only from the encrypted administrator configuration. Keeping it
    # separate lets clearing the override fall back to WAVESPEED_API_KEY.
    wavespeed_admin_api_key: str | None = Field(default=None, exclude=True)
    wavespeed_api_base_url: str = "https://api.wavespeed.ai/api/v3"
    wavespeed_provider_name: str = "wavespeed"
    wavespeed_request_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    wavespeed_max_submit_concurrency: int = Field(default=1, ge=1, le=50)
    wavespeed_max_poll_concurrency: int = Field(default=4, ge=1, le=50)
    wavespeed_get_max_retries: int = Field(default=3, ge=1, le=8)
    wavespeed_get_retry_base_seconds: float = Field(default=2.0, ge=2, le=30)
    wavespeed_get_retry_max_seconds: float = Field(default=30.0, ge=2, le=120)
    wavespeed_video_provider_name: str = "wavespeed_video"
    wavespeed_video_model: str = "kwaivgi/kling-video-o3-pro/reference-to-video"
    wavespeed_video_duration: int = Field(default=10, ge=3, le=15)
    wavespeed_video_aspect_ratio: Literal["16:9", "9:16", "1:1"] = "9:16"
    wavespeed_video_sound: bool = False
    wavespeed_video_task_timeout_seconds: float = Field(default=1800.0, ge=60, le=86_400)
    wavespeed_video_download_timeout_seconds: float = Field(default=300.0, gt=0, le=1800)
    wavespeed_video_poll_interval_seconds: float = Field(default=10.0, ge=1, le=300)
    wavespeed_video_max_poll_interval_seconds: float = Field(default=30.0, ge=1, le=600)
    wavespeed_admin_config_file: Path = Path("var/runtime/wavespeed-config.json")
    max_input_image_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    artifact_root: Path = Path("var/artifacts")
    admin_credentials_file: Path = Path("var/runtime/admin-credentials.json")
    kling_admin_config_file: Path = Path("var/runtime/kling-config.json")
    runner_root: Path = Path("var/runner")
    daily_user_points_limit: int = Field(default=5000, ge=1)
    generation_estimated_points: int = Field(default=120, ge=1)
    auto_run_fake_commands: bool = True
    dev_user_id: str = "00000000-0000-0000-0000-000000000001"
    dev_admin_id: str = "00000000-0000-0000-0000-000000000099"

    download_concurrency: int = Field(default=4, ge=1, le=32)
    technical_validation_concurrency: int = Field(default=2, ge=1, le=16)
    output_retention_days: int = Field(default=7, ge=1, le=30)
    session_secret: str = "change-me-before-shared-use"
    session_cookie_name: str = "libtv_session"
    csrf_cookie_name: str = "libtv_csrf"
    session_cookie_secure: bool = True
    session_ttl_hours: int = Field(default=12, ge=1, le=168)

    generation_same_project: int = Field(default=1, ge=1, le=4)
    generation_per_user: int = Field(default=1, ge=1, le=6)
    generation_global: int = Field(default=1, ge=1, le=12)
    unknown_user_window_seconds: int = Field(default=1800, ge=60, le=86_400)
    unknown_user_distinct_task_threshold: int = Field(default=2, ge=2, le=100)
    unknown_provider_window_seconds: int = Field(default=600, ge=60, le=86_400)
    unknown_provider_distinct_task_threshold: int = Field(default=5, ge=3, le=1000)
    unknown_provider_distinct_user_threshold: int = Field(default=3, ge=2, le=1000)
    unknown_provider_min_attempts: int = Field(default=6, ge=3, le=10_000)
    unknown_provider_rate_threshold: float = Field(default=0.5, gt=0, le=1)
    prepared_queue_low_watermark: int = Field(default=12, ge=1, le=1000)
    prepared_queue_high_watermark: int = Field(default=24, ge=2, le=2000)
    global_paused: bool = False
    paid_submissions_paused: bool = True
    auto_confirm_levels: str = "PASS"

    runner_service_name: str = "LibTVProductionRunner"
    runner_service_account: str = "NT SERVICE\\LibTVProductionRunner"
    runner_poll_seconds: float = Field(default=1.0, ge=0.25, le=60)
    runner_metric_sample_seconds: int = Field(default=60, ge=5, le=3600)
    runner_metric_retention_days: int = Field(default=30, ge=1, le=365)
    runner_log_disk_warning_percent: float = Field(default=15.0, ge=1, le=50)
    runner_log_disk_stop_percent: float = Field(default=10.0, ge=1, le=50)
    sse_heartbeat_seconds: int = Field(default=15, ge=2, le=60)

    @field_validator("app_public_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("object_store_prefix")
    @classmethod
    def validate_object_store_prefix(cls, value: str) -> str:
        normalized = value.strip().strip("/").replace("\\", "/")
        if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
            raise ValueError("object_store_prefix must be a normalized relative prefix")
        return normalized

    @model_validator(mode="after")
    def validate_controlled_mvp_limits(self) -> "Settings":
        levels = {part.strip() for part in self.auto_confirm_levels.split(",") if part.strip()}
        if levels - {"PASS"}:
            raise ValueError("only PASS may be configured for automatic confirmation")
        if self.prepared_queue_low_watermark < self.generation_global:
            raise ValueError("prepared queue low watermark must cover global generation capacity")
        if self.prepared_queue_high_watermark < 2 * self.generation_global:
            raise ValueError("prepared queue high watermark must be at least twice global capacity")
        if self.runner_log_disk_stop_percent >= self.runner_log_disk_warning_percent:
            raise ValueError("runner disk stop threshold must be below warning threshold")
        if self.openai_analysis_timeout_max_seconds < self.openai_analysis_timeout_seconds:
            raise ValueError("analysis maximum timeout must cover the base timeout")
        if self.analysis_stale_after_seconds <= self.openai_analysis_timeout_max_seconds:
            raise ValueError(
                "analysis stale threshold must exceed the maximum OpenAI analysis timeout"
            )
        if self.app_env == "test" and (
            self.libtv_execution_mode == "live"
            or self.paid_generation_enabled
            or self.kling_enable_paid_integration_test
            or self.kling_api_enable_paid_integration_test
        ):
            raise ValueError("test environments cannot enable paid generation")
        if self.kling_cli_poll_interval_seconds > self.kling_cli_max_poll_interval_seconds:
            raise ValueError("Kling poll interval cannot exceed its maximum")
        if self.kling_api_poll_interval_seconds > self.kling_api_max_poll_interval_seconds:
            raise ValueError("Kling API poll interval cannot exceed its maximum")
        if (
            self.wavespeed_video_poll_interval_seconds
            > self.wavespeed_video_max_poll_interval_seconds
        ):
            raise ValueError("WaveSpeed video poll interval cannot exceed its maximum")
        if self.kling_api_base_url.rstrip("/") != self.kling_api_base_url:
            self.kling_api_base_url = self.kling_api_base_url.rstrip("/")
        api_url = urlsplit(self.kling_api_base_url)
        official_hosts = {"api-beijing.klingai.com", "api-singapore.klingai.com"}
        loopback_hosts = {"localhost", "127.0.0.1", "::1"}
        official_endpoint = (
            api_url.scheme == "https"
            and api_url.hostname in official_hosts
            and not api_url.username
            and not api_url.password
            and api_url.path in {"", "/"}
            and not api_url.query
            and not api_url.fragment
        )
        local_test_endpoint = (
            self.app_env in {"development", "test"}
            and api_url.scheme in {"http", "https"}
            and api_url.hostname in loopback_hosts
            and not api_url.username
            and not api_url.password
            and api_url.path in {"", "/"}
            and not api_url.query
            and not api_url.fragment
        )
        if not official_endpoint and not local_test_endpoint:
            raise ValueError(
                "Kling API base URL must use an official Kling endpoint; "
                "loopback endpoints are allowed only in development or test"
            )
        self.wavespeed_api_base_url = self.wavespeed_api_base_url.rstrip("/")
        wavespeed_url = urlsplit(self.wavespeed_api_base_url)
        official_wavespeed_endpoint = (
            wavespeed_url.scheme == "https"
            and wavespeed_url.hostname == "api.wavespeed.ai"
            and wavespeed_url.path == "/api/v3"
            and not wavespeed_url.username
            and not wavespeed_url.password
            and not wavespeed_url.query
            and not wavespeed_url.fragment
        )
        local_wavespeed_endpoint = (
            self.app_env in {"development", "test"}
            and wavespeed_url.scheme in {"http", "https"}
            and wavespeed_url.hostname in loopback_hosts
            and not wavespeed_url.username
            and not wavespeed_url.password
            and not wavespeed_url.query
            and not wavespeed_url.fragment
        )
        if not official_wavespeed_endpoint and not local_wavespeed_endpoint:
            raise ValueError(
                "WaveSpeed API base URL must use https://api.wavespeed.ai/api/v3; "
                "loopback endpoints are allowed only in development or test"
            )
        if self.wavespeed_get_retry_base_seconds > self.wavespeed_get_retry_max_seconds:
            raise ValueError("WaveSpeed retry base interval cannot exceed its maximum")
        return self

    @property
    def effective_wavespeed_api_key(self) -> str | None:
        return self.wavespeed_admin_api_key or self.wavespeed_api_key

    @property
    def wavespeed_credential_source(self) -> Literal["admin", "environment", "none"]:
        if self.wavespeed_admin_api_key:
            return "admin"
        if self.wavespeed_api_key:
            return "environment"
        return "none"

    def analysis_timeout_for_image_count(self, image_count: int) -> float:
        extra_images = max(0, image_count - self.openai_analysis_timeout_base_image_count)
        timeout = self.openai_analysis_timeout_seconds + (
            extra_images * self.openai_analysis_timeout_per_extra_image_seconds
        )
        return min(timeout, self.openai_analysis_timeout_max_seconds)

    @property
    def kling_enabled(self) -> bool:
        if self.kling_provider_backend == "wavespeed":
            return self.wavespeed_enabled and bool(self.effective_wavespeed_api_key)
        return self.kling_api_enabled

    @property
    def active_kling_provider_name(self) -> str:
        if self.kling_provider_backend == "wavespeed":
            return self.wavespeed_video_provider_name
        return self.kling_api_provider_name

    @property
    def active_kling_model(self) -> str | None:
        if self.kling_provider_backend == "wavespeed":
            return self.wavespeed_video_model
        return self.kling_api_model

    @property
    def active_kling_duration(self) -> int:
        if self.kling_provider_backend == "wavespeed":
            return self.wavespeed_video_duration
        return self.kling_api_duration

    @property
    def active_kling_aspect_ratio(self) -> str:
        if self.kling_provider_backend == "wavespeed":
            return self.wavespeed_video_aspect_ratio
        return self.kling_api_aspect_ratio

    @property
    def active_video_audio(self) -> str:
        if self.kling_provider_backend == "wavespeed":
            return "native" if self.wavespeed_video_sound else "off"
        return self.kling_api_audio

    @property
    def active_video_multi_shot(self) -> bool:
        return self.kling_api_multi_shot

    @property
    def kling_provider_names(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                (
                    "kling",
                    self.kling_cli_provider_name,
                    self.kling_api_provider_name,
                    self.wavespeed_video_provider_name,
                )
            )
        )

    def kling_poll_interval(self, *, unknown: bool = False) -> float:
        return (
            self.kling_api_max_poll_interval_seconds
            if unknown
            else self.kling_api_poll_interval_seconds
        )

    def kling_poll_interval_for_provider(self, provider: str, *, unknown: bool = False) -> float:
        normalized = provider.strip().lower()
        if normalized == self.wavespeed_video_provider_name.strip().lower():
            return (
                self.wavespeed_video_max_poll_interval_seconds
                if unknown
                else self.wavespeed_video_poll_interval_seconds
            )
        if normalized == self.kling_api_provider_name.strip().lower():
            return (
                self.kling_api_max_poll_interval_seconds
                if unknown
                else self.kling_api_poll_interval_seconds
            )
        return (
            self.kling_cli_max_poll_interval_seconds
            if unknown
            else self.kling_cli_poll_interval_seconds
        )

    def kling_provider_enabled(self, provider: str) -> bool:
        """Return whether a provider may be queried for an existing attempt."""
        normalized = provider.strip().lower()
        if normalized == "kling":
            return self.kling_enabled
        if normalized == self.kling_api_provider_name.strip().lower():
            return self.kling_api_enabled
        if normalized == self.kling_cli_provider_name.strip().lower():
            return self.kling_cli_enabled
        if normalized == self.wavespeed_video_provider_name.strip().lower():
            return self.wavespeed_enabled and bool(self.effective_wavespeed_api_key)
        return False

    def kling_provider_submission_enabled(self, provider: str) -> bool:
        """Return whether a concrete provider can submit its persisted queued work."""
        normalized = provider.strip().lower()
        if normalized == "kling":
            return self.kling_enabled
        if normalized == self.wavespeed_video_provider_name.strip().lower():
            return self.wavespeed_enabled and bool(self.effective_wavespeed_api_key)
        if normalized == self.kling_api_provider_name.strip().lower():
            return self.kling_api_enabled
        return False

    def video_task_timeout_for_provider(self, provider: str) -> float | None:
        normalized = provider.strip().lower()
        if normalized == self.kling_api_provider_name.strip().lower():
            return self.kling_api_task_timeout_seconds
        if normalized == self.wavespeed_video_provider_name.strip().lower():
            return self.wavespeed_video_task_timeout_seconds
        return None

    def validate_shared_environment(self) -> None:
        if (
            self.app_env not in {"staging", "production"}
            and self.shared_authentication
            and self.session_secret == "change-me-before-shared-use"
        ):
            raise ValueError("Shared authentication requires a non-default session secret")
        if self.app_env in {"staging", "production"}:
            unsafe = "change-me-before-shared-use"
            if self.session_secret == unsafe or self.minio_secret_key == unsafe:
                raise ValueError("Shared environments require non-default secrets")
            if self.object_store_prefix == "development":
                raise ValueError(
                    "Shared environments require an environment-specific object prefix"
                )
            if not self.libtv_workspace_id or not self.libtv_project_uuid:
                raise ValueError(
                    "Shared environments require dedicated LibTV workspace and project IDs"
                )
            if not self.session_cookie_secure:
                raise ValueError("Staging and production require secure session cookies")

    @property
    def shared_authentication(self) -> bool:
        return self.shared_authentication_enabled or self.app_env in {"staging", "production"}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_shared_environment()
    return settings
