import logging
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.models import Base, User
from libtv_agent.logging_config import RedactingFilter, redact_text
from libtv_agent.services.auth import PasswordService
from sqlalchemy.ext.asyncio import create_async_engine

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")


def shared_settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        app_env="staging",
        database_url=database_url,
        object_store_mode="local",
        object_store_prefix="staging",
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        session_secret="staging-session-secret-not-committed",
        minio_secret_key="staging-minio-secret-not-committed",
        libtv_workspace_id="staging-workspace",
        libtv_project_uuid="staging-project",
        _env_file=None,
    )


@pytest.mark.asyncio
async def test_shared_environment_requires_session_and_csrf(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'auth.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            User.__table__.insert().values(
                id=ADMIN_ID,
                username="controlled-admin",
                password_hash=PasswordService().hash("a-long-local-password"),
                role=UserRole.ADMIN.value,
                is_active=True,
            )
        )
    await engine.dispose()
    app = create_app(shared_settings(database_url, tmp_path))

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            forged = await client.get("/api/v1/auth/me", headers={"X-User-Id": str(ADMIN_ID)})
            assert forged.status_code == 401
            logged_in = await client.post(
                "/api/v1/auth/login",
                json={"username": "controlled-admin", "password": "a-long-local-password"},
            )
            assert logged_in.status_code == 200
            csrf = logged_in.json()["csrfToken"]
            me = await client.get("/api/v1/auth/me")
            assert me.status_code == 200
            assert me.json()["role"] == "ADMIN"
            rejected = await client.post(
                "/api/v1/admin/pause",
                json={
                    "expectedVersion": 1,
                    "scope": "GLOBAL",
                    "paused": True,
                    "reason": "csrf rejection drill",
                },
            )
            assert rejected.status_code == 403
            accepted = await client.post(
                "/api/v1/admin/pause",
                headers={"X-CSRF-Token": csrf},
                json={
                    "expectedVersion": 1,
                    "scope": "GLOBAL",
                    "paused": True,
                    "reason": "authenticated stop drill",
                },
            )
            assert accepted.status_code == 200
            assert accepted.headers["content-security-policy"].startswith("default-src")
            assert accepted.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_lan_http_mode_uses_session_authentication_without_secure_cookie(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'lan-auth.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            User.__table__.insert().values(
                id=ADMIN_ID,
                username="lan-admin",
                password_hash=PasswordService().hash("a-long-local-password"),
                role=UserRole.ADMIN.value,
                is_active=True,
            )
        )
    await engine.dispose()
    settings = Settings(
        app_env="development",
        shared_authentication_enabled=True,
        session_cookie_secure=False,
        session_secret="lan-session-secret-with-at-least-32-bytes",
        database_url=database_url,
        object_store_mode="local",
        object_store_prefix="development",
        artifact_root=tmp_path / "artifacts",
        runner_root=tmp_path / "runner",
        _env_file=None,
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://lan.test") as client:
            forged = await client.get("/api/v1/auth/me", headers={"X-User-Id": str(ADMIN_ID)})
            assert forged.status_code == 401
            logged_in = await client.post(
                "/api/v1/auth/login",
                json={"username": "lan-admin", "password": "a-long-local-password"},
            )
            assert logged_in.status_code == 200
            assert "Secure" not in logged_in.headers["set-cookie"]
            assert (await client.get("/api/v1/auth/me")).status_code == 200


def test_log_redaction_removes_secrets_and_signed_url_tokens() -> None:
    source = (
        "Authorization=Bearer abc.def.ghi api_key=sk-example123456789 "
        "url=https://minio/object?X-Amz-Signature=secret-signature"
    )
    redacted = redact_text(source)

    assert "abc.def.ghi" not in redacted
    assert "sk-example" not in redacted
    assert "secret-signature" not in redacted
    record = logging.LogRecord("test", logging.INFO, __file__, 1, source, (), None)
    assert RedactingFilter().filter(record)
    assert "[REDACTED]" in str(record.msg)
