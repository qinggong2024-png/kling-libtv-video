import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.models import Base, User
from libtv_agent.services.auth import PasswordService
from sqlalchemy.ext.asyncio import create_async_engine

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ADMIN_PASSWORD = "admin-password-1234"
USER_PASSWORD = "initial-password-1234"


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


async def login(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()["csrfToken"]


@pytest.mark.asyncio
async def test_admin_manages_user_account_lifecycle(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'users.db').as_posix()}"
    engine = create_async_engine(database_url)
    password_service = PasswordService()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            User.__table__.insert(),
            [
                {
                    "id": ADMIN_ID,
                    "username": "owner",
                    "password_hash": password_service.hash(ADMIN_PASSWORD),
                    "role": UserRole.ADMIN.value,
                    "is_active": True,
                },
                {
                    "id": USER_ID,
                    "username": "producer-one",
                    "password_hash": password_service.hash(USER_PASSWORD),
                    "role": UserRole.USER.value,
                    "is_active": True,
                },
            ],
        )
    await engine.dispose()

    app = create_app(shared_settings(database_url, tmp_path))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with (
            AsyncClient(transport=transport, base_url="https://test") as admin_client,
            AsyncClient(transport=transport, base_url="https://test") as user_client,
        ):
            admin_csrf = await login(admin_client, "owner", ADMIN_PASSWORD)
            await login(user_client, "producer-one", USER_PASSWORD)

            forbidden = await user_client.get("/api/v1/admin/users")
            assert forbidden.status_code == 403

            initial = await admin_client.get("/api/v1/admin/users")
            assert initial.status_code == 200
            assert [(row["username"], row["role"]) for row in initial.json()] == [
                ("owner", "ADMIN"),
                ("producer-one", "USER"),
            ]

            weak_password = await admin_client.post(
                "/api/v1/admin/users",
                headers={"X-CSRF-Token": admin_csrf},
                json={"username": "producer-two", "password": "too-short"},
            )
            assert weak_password.status_code == 422

            created = await admin_client.post(
                "/api/v1/admin/users",
                headers={"X-CSRF-Token": admin_csrf},
                json={"username": "producer-two", "password": "second-password-1234"},
            )
            assert created.status_code == 201
            assert created.json()["role"] == "USER"
            assert created.json()["isActive"] is True
            created_user_id = created.json()["id"]

            duplicate = await admin_client.post(
                "/api/v1/admin/users",
                headers={"X-CSRF-Token": admin_csrf},
                json={"username": "producer-two", "password": "second-password-5678"},
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["detail"]["code"] == "USERNAME_EXISTS"

            protected = await admin_client.delete(
                f"/api/v1/admin/users/{ADMIN_ID}", headers={"X-CSRF-Token": admin_csrf}
            )
            assert protected.status_code == 409
            assert protected.json()["detail"]["code"] == "PROTECTED_ACCOUNT"

            reset = await admin_client.post(
                f"/api/v1/admin/users/{USER_ID}/reset-password",
                headers={"X-CSRF-Token": admin_csrf},
                json={"password": "replacement-password-1234"},
            )
            assert reset.status_code == 204
            assert (await user_client.get("/api/v1/auth/me")).status_code == 401
            assert (
                await user_client.post(
                    "/api/v1/auth/login",
                    json={"username": "producer-one", "password": USER_PASSWORD},
                )
            ).status_code == 401
            await login(user_client, "producer-one", "replacement-password-1234")

            deactivated = await admin_client.delete(
                f"/api/v1/admin/users/{USER_ID}", headers={"X-CSRF-Token": admin_csrf}
            )
            assert deactivated.status_code == 204
            assert (await user_client.get("/api/v1/auth/me")).status_code == 401
            assert (
                await user_client.post(
                    "/api/v1/auth/login",
                    json={
                        "username": "producer-one",
                        "password": "replacement-password-1234",
                    },
                )
            ).status_code == 401

            users = await admin_client.get("/api/v1/admin/users")
            user_rows = {row["id"]: row for row in users.json()}
            assert user_rows[str(USER_ID)]["isActive"] is False
            assert user_rows[created_user_id]["isActive"] is True

            audit = await admin_client.get("/api/v1/admin/audit")
            actions = {row["action"] for row in audit.json()}
            assert {"CREATE_USER", "RESET_USER_PASSWORD", "DEACTIVATE_USER"} <= actions
