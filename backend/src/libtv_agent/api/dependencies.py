import hashlib
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from libtv_agent.db import get_session
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.models import User, UserSession
from libtv_agent.services.prompt_presets import add_default_prompt_presets
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

Session = Annotated[AsyncSession, Depends(get_session)]


async def get_actor(
    session: Session,
    request: Request,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> User:
    settings = request.app.state.settings
    if settings.shared_authentication:
        token = request.cookies.get(settings.session_cookie_name)
        if not token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authenticated session is required")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        user = await session.scalar(
            select(User)
            .join(UserSession, UserSession.user_id == User.id)
            .where(
                UserSession.token_hash == token_hash,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > datetime.now(UTC),
                User.is_active.is_(True),
            )
        )
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session is invalid or expired")
        return user
    if not x_user_id:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "X-User-Id is required in phase-one offline mode"
        )
    try:
        user_id = uuid.UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid X-User-Id") from exc
    user = await session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if (
        user is None
        and settings.app_env in {"development", "test"}
        and x_user_id
        in {
            settings.dev_user_id,
            settings.dev_admin_id,
        }
    ):
        role = UserRole.ADMIN if x_user_id == settings.dev_admin_id else UserRole.USER
        user = User(
            id=user_id,
            username="phase-one-admin" if role == UserRole.ADMIN else "phase-one-user",
            password_hash="offline-disabled",
            role=role,
        )
        session.add(user)
        try:
            await session.flush()
            add_default_prompt_presets(session, user.id)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            user = await session.scalar(
                select(User).where(User.id == user_id, User.is_active.is_(True))
            )
            if user is None:
                raise
    if user is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "user is not active")
    return user


Actor = Annotated[User, Depends(get_actor)]


def require_review_write(actor: User) -> None:
    """Keep auditors read-only while preserving ordinary-owner review behavior."""

    if actor.role is UserRole.AUDITOR:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERMISSION_DENIED",
                "message": "auditor role is read-only",
            },
        )


def can_review_across_owners(actor: User) -> bool:
    return actor.role in {UserRole.OPERATOR, UserRole.ADMIN}
