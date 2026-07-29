from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

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
    openai_model: str = "gpt-5.6-terra"
    openai_analysis_fallback_model: str | None = "gpt-5.6-sol"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    openai_analysis_timeout_seconds: float = Field(default=180.0, gt=0, le=900)
    openai_analysis_timeout_base_image_count: int = Field(default=4, ge=1, le=20)
    openai_analysis_timeout_per_extra_image_seconds: float = Field(default=45.0, ge=0, le=300)
    openai_analysis_timeout_max_seconds: float = Field(default=600.0, gt=0, le=1800)
    analysis_stale_after_seconds: float = Field(default=660.0, gt=0, le=3600)
    analysis_recovery_poll_seconds: float = Field(default=30.0, gt=0, le=300)
    analysis_shutdown_grace_seconds: float = Field(default=15.0, gt=0, le=300)
    materialization_stale_after_seconds: float = Field(default=300.0, gt=0, le=3600)
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
    max_input_image_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    artifact_root: Path = Path("var/artifacts")
    admin_credentials_file: Path = Path("var/runtime/admin-credentials.json")
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
        ):
            raise ValueError("test environments cannot enable paid generation")
        if self.kling_cli_poll_interval_seconds > self.kling_cli_max_poll_interval_seconds:
            raise ValueError("Kling poll interval cannot exceed its maximum")
        return self

    def analysis_timeout_for_image_count(self, image_count: int) -> float:
        extra_images = max(0, image_count - self.openai_analysis_timeout_base_image_count)
        timeout = self.openai_analysis_timeout_seconds + (
            extra_images * self.openai_analysis_timeout_per_extra_image_seconds
        )
        return min(timeout, self.openai_analysis_timeout_max_seconds)

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
