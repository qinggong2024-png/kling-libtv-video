import pytest
from libtv_agent.adapters.bach_provider import BachApiAdapter
from libtv_agent.adapters.kling_provider import create_kling_adapter
from libtv_agent.config import Settings, _workspace_source_revision


def test_contract_defaults() -> None:
    settings = Settings(_env_file=None)

    assert len(settings.deployment_source_revision) == 64
    assert settings.deployment_source_revision != "unknown"
    assert settings.openai_model == "gpt-5.6-luna"
    assert settings.openai_analysis_fallback_model == "gpt-5.6-terra"
    assert settings.openai_reasoning_effort == "none"
    assert settings.openai_analysis_fallback_reasoning_effort == "low"
    assert settings.openai_analysis_verbosity == "low"
    assert settings.openai_analysis_max_output_tokens == 4000
    assert settings.openai_analysis_fallback_max_output_tokens == 6000
    assert settings.analysis_timeout_for_image_count(4) == 180
    assert settings.analysis_timeout_for_image_count(8) == 360
    assert settings.analysis_timeout_for_image_count(20) == 600
    assert settings.analysis_stale_after_seconds == 660
    assert settings.libtv_adapter_mode == "fake"
    assert settings.libtv_execution_mode == "dry-run"
    assert settings.paid_generation_enabled is False
    assert settings.download_concurrency == 4
    assert settings.technical_validation_concurrency == 2
    assert settings.output_retention_days == 7
    assert settings.kling_provider_backend == "api"
    assert settings.kling_api_base_url == "https://api-beijing.klingai.com"
    assert settings.kling_api_model == "kling-3.0-omni"
    assert settings.kling_api_duration == 10
    assert settings.kling_api_aspect_ratio == "9:16"
    assert settings.kling_api_enabled is False


def test_explicit_deployment_source_revision_overrides_source_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEPLOYMENT_SOURCE_REVISION", "explicit-test-revision")

    settings = Settings(_env_file=None)

    assert settings.deployment_source_revision == "explicit-test-revision"


def test_workspace_source_revision_matches_expected_manifest_shape(tmp_path) -> None:
    (tmp_path / "backend" / "src").mkdir(parents=True)
    (tmp_path / "backend" / "alembic" / "versions").mkdir(parents=True)
    (tmp_path / "backend" / "src" / "app.py").write_text("first", encoding="utf-8")
    (tmp_path / "backend" / "alembic" / "versions" / "001.py").write_text(
        "migration", encoding="utf-8"
    )
    (tmp_path / "backend" / "alembic.ini").write_text("alembic", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("project", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("lock", encoding="utf-8")

    initial = _workspace_source_revision(tmp_path)

    assert len(initial) == 64
    assert initial != "unknown"
    assert _workspace_source_revision(tmp_path) == initial
    (tmp_path / "backend" / "src" / "app.py").write_text("second", encoding="utf-8")
    assert _workspace_source_revision(tmp_path) != initial


def test_kling_api_configuration_selects_independent_provider() -> None:
    settings = Settings(
        kling_provider_backend="api",
        kling_api_enabled=True,
        kling_api_key="fake-test-key",
        kling_api_base_url="https://api-singapore.klingai.com/",
        _env_file=None,
    )

    assert settings.kling_enabled is True
    assert settings.active_kling_provider_name == "kling_official_api"
    assert settings.active_kling_model == "kling-3.0-omni"
    assert settings.kling_api_base_url == "https://api-singapore.klingai.com"
    assert settings.kling_provider_enabled("kling_official_api") is True
    assert settings.kling_provider_enabled("kling_official_cli") is False


def test_wavespeed_configuration_selects_video_provider_without_disabling_kling_recovery() -> None:
    settings = Settings(
        kling_provider_backend="wavespeed",
        kling_api_enabled=True,
        kling_api_key="fake-kling-key",
        wavespeed_enabled=True,
        wavespeed_api_key="fake-wavespeed-key",
        wavespeed_video_model="kwaivgi/kling-video-o3-std/reference-to-video",
        wavespeed_video_duration=8,
        wavespeed_video_aspect_ratio="16:9",
        _env_file=None,
    )

    assert settings.kling_enabled is True
    assert settings.active_kling_provider_name == "wavespeed_video"
    assert settings.active_kling_model == "kwaivgi/kling-video-o3-std/reference-to-video"
    assert settings.active_kling_duration == 8
    assert settings.active_kling_aspect_ratio == "16:9"
    assert settings.kling_provider_submission_enabled("wavespeed_video") is True
    assert settings.kling_provider_submission_enabled("kling_official_api") is True


def test_bach_configuration_selects_bach_video_provider() -> None:
    settings = Settings(
        kling_provider_backend="bach",
        bach_enabled=True,
        bach_access_key="fake-bach-access-key",
        bach_secret_key="fake-bach-secret-key",
        bach_model="bach_i2v_test",
        bach_duration=6,
        bach_aspect_ratio="16:9",
        _env_file=None,
    )

    assert settings.kling_enabled is True
    assert settings.active_kling_provider_name == "bach"
    assert settings.active_kling_model == "bach_i2v_test"
    assert settings.active_kling_duration == 6
    assert settings.active_kling_aspect_ratio == "16:9"
    assert settings.kling_provider_submission_enabled("bach") is True
    assert isinstance(create_kling_adapter(settings), BachApiAdapter)


def test_test_environment_cannot_enable_paid_kling_api_test() -> None:
    with pytest.raises(ValueError, match="cannot enable paid"):
        Settings(
            app_env="test",
            kling_api_enable_paid_integration_test=True,
            _env_file=None,
        )


def test_analysis_stale_threshold_covers_maximum_timeout() -> None:
    with pytest.raises(ValueError, match="maximum OpenAI analysis timeout"):
        Settings(
            openai_analysis_timeout_seconds=10,
            openai_analysis_timeout_max_seconds=20,
            analysis_stale_after_seconds=20,
            _env_file=None,
        )


def test_shared_environment_rejects_default_secrets() -> None:
    settings = Settings(app_env="production", _env_file=None)

    with pytest.raises(ValueError, match="non-default secrets"):
        settings.validate_shared_environment()


def test_lan_shared_authentication_requires_session_secret() -> None:
    settings = Settings(
        app_env="development",
        shared_authentication_enabled=True,
        session_cookie_secure=False,
        _env_file=None,
    )

    with pytest.raises(ValueError, match="non-default session secret"):
        settings.validate_shared_environment()


def test_lan_shared_authentication_allows_explicit_http_cookie_mode() -> None:
    settings = Settings(
        app_env="development",
        shared_authentication_enabled=True,
        session_cookie_secure=False,
        session_secret="lan-session-secret-with-at-least-32-bytes",
        _env_file=None,
    )

    settings.validate_shared_environment()
    assert settings.shared_authentication is True


def test_production_rejects_insecure_session_cookie() -> None:
    settings = Settings(
        app_env="production",
        session_cookie_secure=False,
        session_secret="production-session-secret",
        minio_secret_key="production-minio-secret",
        object_store_prefix="production",
        libtv_workspace_id="production-workspace",
        libtv_project_uuid="production-project",
        _env_file=None,
    )

    with pytest.raises(ValueError, match="secure session cookies"):
        settings.validate_shared_environment()


def test_comma_separated_public_origins_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PUBLIC_ORIGINS", "http://localhost:5173,http://192.168.30.126:5173")

    settings = Settings(_env_file=None)

    assert settings.app_public_origins == [
        "http://localhost:5173",
        "http://192.168.30.126:5173",
    ]


def test_test_environment_cannot_enable_paid_generation() -> None:
    with pytest.raises(ValueError, match="cannot enable paid"):
        Settings(
            app_env="test",
            libtv_execution_mode="live",
            paid_generation_enabled=True,
            _env_file=None,
        )
