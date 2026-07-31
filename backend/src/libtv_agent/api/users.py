import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.models import AuditEvent, User, UserSession
from libtv_agent.services.auth import PasswordService
from libtv_agent.services.prompt_presets import add_default_prompt_presets
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/admin/users", tags=["admin"])


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=512)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        username = value.strip()
        if not username or any(character.isspace() for character in username):
            raise ValueError("username cannot be empty or contain whitespace")
        return username


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=12, max_length=512)


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    username: str
    role: UserRole
    isActive: bool
    createdAt: datetime


def require_account_admin(actor: User) -> None:
    if actor.role is not UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "administrator role is required")


def user_response(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        isActive=user.is_active,
        createdAt=user.created_at,
    )


def audit_event(actor_id: uuid.UUID, action: str, user: User, reason: str) -> AuditEvent:
    return AuditEvent(
        actor_id=actor_id,
        action=action,
        entity_type="app_user",
        entity_id=str(user.id),
        reason=reason,
        correlation_id=str(uuid.uuid4()),
        evidence_refs_json=[],
    )


async def get_managed_user(session: Session, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user account was not found")
    if user.role is not UserRole.USER:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "PROTECTED_ACCOUNT",
                "message": "administrator accounts cannot be changed here",
            },
        )
    return user


async def revoke_sessions(session: Session, user_id: uuid.UUID) -> None:
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


@router.get("", response_model=list[AdminUserResponse])
async def list_users(actor: Actor, session: Session) -> list[AdminUserResponse]:
    require_account_admin(actor)
    users = list(await session.scalars(select(User).order_by(User.created_at, User.username)))
    return [user_response(user) for user in users]


@router.post("", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest, actor: Actor, session: Session
) -> AdminUserResponse:
    require_account_admin(actor)
    existing = await session.scalar(select(User.id).where(User.username == payload.username))
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "USERNAME_EXISTS", "message": "username already exists"},
        )
    user = User(
        id=uuid.uuid4(),
        username=payload.username,
        password_hash=PasswordService().hash(payload.password),
        role=UserRole.USER,
        is_active=True,
    )
    session.add(user)
    try:
        await session.flush()
        add_default_prompt_presets(session, user.id)
        session.add(
            audit_event(actor.id, "CREATE_USER", user, "administrator created user account")
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "USERNAME_EXISTS", "message": "username already exists"},
        ) from exc
    await session.refresh(user)
    return user_response(user)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(
    user_id: uuid.UUID,
    payload: ResetPasswordRequest,
    actor: Actor,
    session: Session,
) -> Response:
    require_account_admin(actor)
    user = await get_managed_user(session, user_id)
    if not user.is_active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "ACCOUNT_INACTIVE", "message": "user account is inactive"},
        )
    user.password_hash = PasswordService().hash(payload.password)
    await revoke_sessions(session, user.id)
    session.add(
        audit_event(actor.id, "RESET_USER_PASSWORD", user, "administrator reset user password")
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(user_id: uuid.UUID, actor: Actor, session: Session) -> Response:
    require_account_admin(actor)
    user = await get_managed_user(session, user_id)
    if user.is_active:
        user.is_active = False
        await revoke_sessions(session, user.id)
        session.add(
            audit_event(actor.id, "DEACTIVATE_USER", user, "administrator deactivated user account")
        )
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
