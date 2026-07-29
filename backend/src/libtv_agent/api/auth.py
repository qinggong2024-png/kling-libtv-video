import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.models import AuditEvent, User, UserSession
from libtv_agent.services.auth import PasswordService
from pydantic import BaseModel, Field
from sqlalchemy import select, update

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=512)


class ChangePasswordRequest(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=512)
    newPassword: str = Field(min_length=12, max_length=512)


class PromptConfirmationPreferenceRequest(BaseModel):
    automatic: bool


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@router.post("/login")
async def login(
    payload: LoginRequest, response: Response, request: Request, session: Session
) -> dict[str, str]:
    settings = request.app.state.settings
    if not settings.shared_authentication:
        raise HTTPException(status.HTTP_409_CONFLICT, "session login is for shared environments")
    user = await session.scalar(
        select(User).where(User.username == payload.username, User.is_active.is_(True))
    )
    if user is None or not PasswordService().verify(user.password_hash, payload.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=now + timedelta(hours=settings.session_ttl_hours),
        )
    )
    session.add(
        AuditEvent(
            actor_id=user.id,
            action="LOGIN",
            entity_type="user_session",
            entity_id=str(user.id),
            reason="shared environment login",
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[],
        )
    )
    await session.commit()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=settings.session_ttl_hours * 3600,
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="strict",
        path="/",
    )
    return {"userId": str(user.id), "role": user.role.value, "csrfToken": csrf_token}


@router.get("/me")
async def me(actor: Actor) -> dict[str, str]:
    return {"userId": str(actor.id), "username": actor.username, "role": actor.role.value}


@router.get("/preferences/prompt-confirmation")
async def get_prompt_confirmation_preference(actor: Actor) -> dict[str, bool]:
    return {"automatic": actor.auto_confirm_prompts}


@router.patch("/preferences/prompt-confirmation")
async def patch_prompt_confirmation_preference(
    payload: PromptConfirmationPreferenceRequest,
    actor: Actor,
    session: Session,
) -> dict[str, bool]:
    if actor.auto_confirm_prompts != payload.automatic:
        actor.auto_confirm_prompts = payload.automatic
        session.add(
            AuditEvent(
                actor_id=actor.id,
                action="UPDATE_PROMPT_CONFIRMATION_PREFERENCE",
                entity_type="app_user",
                entity_id=str(actor.id),
                reason=(
                    "automatic prompt confirmation enabled"
                    if payload.automatic
                    else "manual prompt confirmation enabled"
                ),
                correlation_id=str(uuid.uuid4()),
                evidence_refs_json=[],
            )
        )
        await session.commit()
    return {"automatic": actor.auto_confirm_prompts}


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    actor: Actor,
    request: Request,
    session: Session,
) -> Response:
    settings = request.app.state.settings
    if not settings.shared_authentication:
        raise HTTPException(status.HTTP_409_CONFLICT, "password login is not enabled")

    password_service = PasswordService()
    if not password_service.verify(actor.password_hash, payload.currentPassword):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "CURRENT_PASSWORD_INVALID", "message": "current password is incorrect"},
        )
    if password_service.verify(actor.password_hash, payload.newPassword):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "PASSWORD_UNCHANGED", "message": "new password must be different"},
        )

    actor.password_hash = password_service.hash(payload.newPassword)
    current_token = request.cookies.get(settings.session_cookie_name)
    current_token_hash = _token_hash(current_token) if current_token else None
    revoke = update(UserSession).where(
        UserSession.user_id == actor.id,
        UserSession.revoked_at.is_(None),
    )
    if current_token_hash:
        revoke = revoke.where(UserSession.token_hash != current_token_hash)
    await session.execute(revoke.values(revoked_at=datetime.now(UTC)))
    session.add(
        AuditEvent(
            actor_id=actor.id,
            action="CHANGE_PASSWORD",
            entity_type="app_user",
            entity_id=str(actor.id),
            reason="user changed own password",
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[],
        )
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(actor: Actor, request: Request, response: Response, session: Session) -> Response:
    settings = request.app.state.settings
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        row = await session.scalar(
            select(UserSession).where(UserSession.token_hash == _token_hash(token))
        )
        if row is not None and row.user_id == actor.id:
            row.revoked_at = datetime.now(UTC)
            await session.commit()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        samesite="strict",
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        samesite="strict",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
