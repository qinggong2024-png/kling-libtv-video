import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.db import Database
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.models import Base, User, UserSession
from libtv_agent.runner.service_runtime import _load_video_provider_admin_configs
from libtv_agent.services.auth import PasswordService
from sqlalchemy import func, select

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
PASSWORD = "isolated-session-password"
REAL_PROVIDER_OPTIONS = [
    {"ai_adapter_mode": "openai"},
    {"openai_api_key": "isolated-unused-feedback-key"},
    {"libtv_adapter_mode": "real"},
    {"kling_cli_enabled": True},
    {"kling_api_enabled": True},
    {"wavespeed_enabled": True},
    {"bach_enabled": True},
    {"libtv_execution_mode": "live"},
    {"paid_generation_enabled": True},
    {"kling_enable_paid_integration_test": True},
    {"kling_api_enable_paid_integration_test": True},
]
MOCK_PROVIDER_OPTIONS = REAL_PROVIDER_OPTIONS[:7]


def isolated_settings(tmp_path: Path, **options) -> Settings:
    return Settings(
        **{
            "app_env": "development",
            "database_url": "sqlite+aiosqlite:///:memory:",
            "object_store_mode": "local",
            "object_store_prefix": "identity-safety",
            "session_secret": "isolated-session-secret-for-identity-tests",
            "minio_secret_key": "isolated-object-store-secret",
            "libtv_workspace_id": "isolated-workspace",
            "libtv_project_uuid": "isolated-project",
            "artifact_root": tmp_path / "artifacts",
            "runner_root": tmp_path / "runner",
            "admin_credentials_file": tmp_path / "credentials.json",
            "kling_admin_config_file": tmp_path / "kling.json",
            "wavespeed_admin_config_file": tmp_path / "wavespeed.json",
            "bach_admin_config_file": tmp_path / "bach.json",
            **options,
        },
        _env_file=None,
    )


@pytest.fixture(
    params=[
        ("development", True),
        ("test", True),
        ("staging", False),
        ("production", False),
    ],
    ids=["development-shared", "test-shared", "staging", "production"],
)
async def shared_app(request, tmp_path: Path):
    environment, shared_enabled = request.param
    settings = isolated_settings(
        tmp_path, app_env=environment, shared_authentication_enabled=shared_enabled
    )
    app = create_app(settings)
    app.state.database = Database(settings.database_url)
    async with app.state.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with app.state.database.session_factory() as session:
        session.add_all(
            [
                User(
                    id=USER_ID,
                    username="producer",
                    password_hash=PasswordService().hash(PASSWORD),
                    role=UserRole.USER,
                ),
                User(
                    id=ADMIN_ID,
                    username="administrator",
                    password_hash="offline-disabled",
                    role=UserRole.ADMIN,
                ),
            ]
        )
        await session.commit()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://identity.test"
        ) as client:
            yield app, client
    finally:
        await app.state.database.dispose()


async def test_shared_business_reads_require_session_and_ignore_forged_header(shared_app) -> None:
    app, client = shared_app
    for path in (
        "/api/v1/auth/me",
        "/api/v1/tasks",
        "/api/v1/products",
        f"/api/v1/creative-workflow/tasks/{uuid.uuid4()}",
    ):
        for headers in ({}, {"X-User-Id": str(ADMIN_ID)}):
            response = await client.get(path, headers=headers)
            assert response.status_code == 401, (path, response.text)
    async with app.state.database.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(UserSession)) == 0
        assert await session.get(User, uuid.UUID(app.state.settings.dev_user_id)) is None
        assert await session.scalar(select(func.count()).select_from(User)) == 2


async def test_shared_login_cannot_be_changed_or_elevated_by_header(shared_app) -> None:
    app, client = shared_app
    response = await client.post(
        "/api/v1/auth/login", json={"username": "producer", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["userId"] == str(USER_ID)
    for forged in (str(ADMIN_ID), app.state.settings.dev_user_id, "invalid-uuid"):
        me = await client.get("/api/v1/auth/me", headers={"X-User-Id": forged})
        assert me.status_code == 200
        assert me.json()["userId"] == str(USER_ID)
        assert me.json()["role"] == "USER"
        admin = await client.get("/api/v1/admin/users", headers={"X-User-Id": forged})
        assert admin.status_code == 403
    assert (await client.get("/api/v1/tasks")).status_code == 200
    logged_out = await client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": response.json()["csrfToken"]}
    )
    assert logged_out.status_code == 204
    me = await client.get("/api/v1/auth/me", headers={"X-User-Id": str(ADMIN_ID)})
    assert me.status_code == 401


@pytest.mark.parametrize("invalid_state", ["missing", "unknown", "expired", "revoked", "inactive"])
async def test_invalid_shared_session_never_falls_back_to_header(shared_app, invalid_state) -> None:
    app, client = shared_app
    token = "isolated-invalid-session"
    if invalid_state in {"expired", "revoked", "inactive"}:
        now = datetime.now(UTC)
        async with app.state.database.session_factory() as session:
            session.add(
                UserSession(
                    user_id=USER_ID,
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    expires_at=now + timedelta(hours=-1 if invalid_state == "expired" else 1),
                    revoked_at=now if invalid_state == "revoked" else None,
                )
            )
            if invalid_state == "inactive":
                user = await session.get(User, USER_ID)
                user.is_active = False
            await session.commit()
    if invalid_state != "missing":
        client.cookies.set(app.state.settings.session_cookie_name, token)
    me = await client.get("/api/v1/auth/me", headers={"X-User-Id": str(ADMIN_ID)})
    assert me.status_code == 401


async def test_shared_mode_never_creates_fixed_development_users(shared_app) -> None:
    app, client = shared_app
    async with app.state.database.session_factory() as session:
        for user in await session.scalars(select(User)):
            await session.delete(user)
        await session.commit()
    for identity in (app.state.settings.dev_user_id, app.state.settings.dev_admin_id):
        response = await client.get("/api/v1/auth/me", headers={"X-User-Id": identity})
        assert response.status_code == 401
    async with app.state.database.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 0


async def test_shared_mode_hides_development_fixed_identities(shared_app) -> None:
    _, client = shared_app
    response = await client.get("/api/v1/system/status")
    assert response.status_code == 200
    assert response.json()["sharedAuthentication"] is True
    assert response.json()["phaseOneUserId"] is None
    assert response.json()["phaseOneAdminId"] is None


@pytest.mark.parametrize("environment", ["development", "test"])
async def test_only_offline_development_and_test_can_create_fixed_users(
    tmp_path: Path, environment: str
) -> None:
    settings = isolated_settings(tmp_path, app_env=environment)
    app = create_app(settings)
    app.state.database = Database(settings.database_url)
    async with app.state.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://identity.test"
        ) as client:
            assert (await client.get("/api/v1/auth/me")).status_code == 401
            invalid = await client.get("/api/v1/auth/me", headers={"X-User-Id": "invalid"})
            assert invalid.status_code == 401
            unknown = str(uuid.uuid4())
            forbidden = await client.get("/api/v1/auth/me", headers={"X-User-Id": unknown})
            assert forbidden.status_code == 403
            for identity, role in (
                (settings.dev_user_id, "USER"),
                (settings.dev_admin_id, "ADMIN"),
            ):
                response = await client.get("/api/v1/auth/me", headers={"X-User-Id": identity})
                assert response.status_code == 200
                assert response.json()["userId"] == identity
                assert response.json()["role"] == role
            async with app.state.database.session_factory() as session:
                assert await session.scalar(select(func.count()).select_from(User)) == 2
    finally:
        await app.state.database.dispose()


@pytest.mark.parametrize("provider_options", REAL_PROVIDER_OPTIONS)
def test_startup_rejects_real_provider_without_shared_authentication(
    tmp_path: Path, provider_options: dict
) -> None:
    settings = isolated_settings(tmp_path, **provider_options)
    assert settings.offline_authentication is False
    with pytest.raises(ValueError, match="require shared authentication"):
        settings.validate_shared_environment()
    with pytest.raises(ValueError, match="require shared authentication"):
        create_app(settings)


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
@pytest.mark.parametrize("provider_options", REAL_PROVIDER_OPTIONS)
def test_real_provider_configuration_allows_valid_shared_authentication(
    tmp_path: Path, environment: str, provider_options: dict
) -> None:
    settings = isolated_settings(
        tmp_path,
        app_env=environment,
        shared_authentication_enabled=environment == "development",
        **provider_options,
    )
    settings.validate_shared_environment()
    assert settings.shared_authentication is True
    assert settings.offline_authentication is False


@pytest.mark.parametrize("provider_options", MOCK_PROVIDER_OPTIONS)
def test_mock_provider_configuration_keeps_test_offline_compatibility(
    tmp_path: Path, provider_options: dict
) -> None:
    settings = isolated_settings(tmp_path, app_env="test", **provider_options)
    settings.validate_shared_environment()
    assert settings.offline_authentication is True


@pytest.mark.parametrize("paid_options", REAL_PROVIDER_OPTIONS[7:])
def test_test_environment_still_rejects_paid_generation(tmp_path: Path, paid_options: dict) -> None:
    with pytest.raises(ValueError, match="cannot enable paid generation"):
        isolated_settings(tmp_path, app_env="test", **paid_options)


@pytest.mark.parametrize("entrypoint", ["api", "runner", "api-feedback"])
def test_startup_revalidates_real_provider_loaded_from_admin_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entrypoint: str
) -> None:
    settings = isolated_settings(tmp_path)
    module = "libtv_agent.runner.service_runtime" if entrypoint == "runner" else "libtv_agent.app"

    def enable_provider(target: Settings) -> bool:
        if entrypoint == "api-feedback":
            target.openai_api_key = "isolated-unused-feedback-key"
        else:
            target.wavespeed_enabled = True
        return True

    loader = (
        "load_admin_credentials" if entrypoint == "api-feedback" else "load_wavespeed_admin_config"
    )
    monkeypatch.setattr(f"{module}.{loader}", enable_provider)
    with pytest.raises(ValueError, match="require shared authentication"):
        if entrypoint == "runner":
            _load_video_provider_admin_configs(settings)
        else:
            create_app(settings)


@pytest.mark.parametrize(
    "disabled_switch", ["feedback_learning_enabled", "feedback_learning_llm_enabled"]
)
def test_unused_feedback_credentials_do_not_enable_real_provider(
    tmp_path: Path, disabled_switch: str
) -> None:
    settings = isolated_settings(
        tmp_path, openai_api_key="isolated-unused-feedback-key", **{disabled_switch: False}
    )
    settings.validate_shared_environment()
    assert settings.offline_authentication is True


async def test_real_provider_enabled_after_startup_disables_offline_identity(
    tmp_path: Path,
) -> None:
    settings = isolated_settings(tmp_path)
    app = create_app(settings)
    app.state.database = Database(settings.database_url)
    async with app.state.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    settings.ai_adapter_mode = "openai"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://identity.test"
        ) as client:
            response = await client.get(
                "/api/v1/auth/me", headers={"X-User-Id": settings.dev_admin_id}
            )
            assert response.status_code == 401
            async with app.state.database.session_factory() as session:
                assert await session.scalar(select(func.count()).select_from(User)) == 0
    finally:
        await app.state.database.dispose()
