import uuid
from copy import deepcopy
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from libtv_agent.adapters.kling_official_cli import KlingCliError
from libtv_agent.adapters.kling_provider import create_kling_adapter
from libtv_agent.adapters.libtv import LibTVError, create_libtv_adapter
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.enums import AttemptStatus, UserRole
from libtv_agent.domain.models import (
    AuditEvent,
    GenerationAttempt,
    ParentTask,
    RuntimeConfigVersion,
)
from libtv_agent.domain.schemas import ReconcileRequest
from libtv_agent.runner.supervisor import RunnerSupervisor
from libtv_agent.services.confirmation import confirm_task
from libtv_agent.services.credentials import credential_status, update_admin_credentials
from libtv_agent.services.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    load_idempotent_response,
    release_idempotency_claim,
    store_idempotent_response,
)
from libtv_agent.services.kling_config import (
    kling_admin_config_signature,
    kling_admin_config_status,
    load_kling_admin_config,
    update_kling_admin_config,
)
from libtv_agent.services.libtv_login import LibTVLoginStartError
from libtv_agent.services.model_registry import ModelRegistryError, refresh_model_registry
from libtv_agent.services.observability import operations_snapshot
from libtv_agent.services.runtime_control import (
    get_runtime_config,
    rollback_runtime_config,
    set_libtv_auth_required,
    update_runtime_config,
)
from pydantic import BaseModel, Field
from sqlalchemy import select

router = APIRouter(prefix="/admin", tags=["admin"])


class RuntimeConfigUpdateRequest(BaseModel):
    expectedVersion: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=255)
    config: dict[str, Any]


class RuntimeConfigRollbackRequest(BaseModel):
    expectedVersion: int = Field(ge=1)
    targetVersion: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=255)


class PauseRequest(BaseModel):
    expectedVersion: int = Field(ge=1)
    scope: str = Field(pattern="^(GLOBAL|PAID_SUBMISSIONS)$")
    paused: bool
    reason: str = Field(min_length=3, max_length=255)


class PromptConfirmationRequest(BaseModel):
    expectedVersion: int = Field(ge=1)
    automatic: bool


class CredentialUpdateRequest(BaseModel):
    libtvAccessKey: str | None = Field(default=None, min_length=8, max_length=4096)
    modelApiKey: str | None = Field(default=None, min_length=8, max_length=4096)
    modelBaseUrl: str | None = Field(default=None, min_length=8, max_length=2048)
    clearLibtvAccessKey: bool = False
    clearModelApiKey: bool = False
    clearModelBaseUrl: bool = False


class LibTVAccountUseRequest(BaseModel):
    account: str = Field(min_length=1, max_length=255)


class KlingConfigUpdateRequest(BaseModel):
    backend: str | None = Field(default=None, pattern="^(cli|api)$")
    apiKey: str | None = None
    clearApiKey: bool = False
    baseUrl: str | None = Field(default=None, max_length=2048)
    callbackUrl: str | None = Field(default=None, max_length=2048)
    clearCallbackUrl: bool = False
    model: str | None = Field(default=None, pattern="^kling-3\\.0-omni$")
    duration: int | None = Field(default=None, ge=3, le=15)
    aspectRatio: str | None = Field(default=None, pattern="^(16:9|9:16|1:1)$")
    resolution: str | None = Field(default=None, pattern="^(720p|1080p|4k)$")
    audio: str | None = Field(default=None, pattern="^(native|original|off)$")
    multiShot: bool | None = None
    maxSubmitConcurrency: int | None = Field(default=None, ge=1, le=20)
    maxPollConcurrency: int | None = Field(default=None, ge=1, le=50)
    enabled: bool | None = None


class KlingErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class KlingErrorResponse(BaseModel):
    detail: str | KlingErrorDetail


class KlingConfigResponse(BaseModel):
    backend: str
    apiKeyConfigured: bool
    baseUrl: str
    callbackUrl: str | None
    model: str
    duration: int
    aspectRatio: str
    resolution: str
    audio: str
    multiShot: bool
    maxSubmitConcurrency: int
    maxPollConcurrency: int
    enabled: bool
    provider: str
    updatedAt: str | None


class KlingStatusResponse(BaseModel):
    enabled: bool
    backend: str
    provider: str
    status: str
    available: bool
    authenticated: bool
    reason: str | None
    cliVersion: str | None
    checkedAt: str | None
    supportedModels: list[str]
    supportedTools: list[str]
    videoDurations: list[str]
    aspectRatios: list[str]
    imageInputLimit: int
    supportsTailImage: bool
    supportsMultipleImages: bool
    supportsWatermarkFreeOutput: bool
    verificationMode: str
    verificationMayGenerateOrCharge: bool


KLING_ADMIN_ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {"model": KlingErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": KlingErrorResponse},
    status.HTTP_409_CONFLICT: {"model": KlingErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": KlingErrorResponse},
}


def _refresh_kling_config_from_disk(request: Request) -> None:
    signature = kling_admin_config_signature(request.app.state.settings)
    if signature == request.app.state.kling_config_signature:
        return
    load_kling_admin_config(request.app.state.settings)
    request.app.state.kling_adapter = create_kling_adapter(request.app.state.settings)
    request.app.state.kling_config_signature = kling_admin_config_signature(
        request.app.state.settings
    )


@router.get(
    "/kling/config",
    response_model=KlingConfigResponse,
    responses=KLING_ADMIN_ERROR_RESPONSES,
)
async def read_kling_config(actor: Actor, request: Request) -> KlingConfigResponse:
    require_admin(actor.role)
    _refresh_kling_config_from_disk(request)
    return KlingConfigResponse.model_validate(kling_admin_config_status(request.app.state.settings))


@router.patch(
    "/kling/config",
    response_model=KlingConfigResponse,
    responses=KLING_ADMIN_ERROR_RESPONSES,
)
async def patch_kling_config(
    payload: KlingConfigUpdateRequest,
    actor: Actor,
    session: Session,
    request: Request,
) -> KlingConfigResponse:
    require_credential_admin(actor.role)
    _refresh_kling_config_from_disk(request)
    if payload.apiKey is not None and payload.clearApiKey:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INPUT_INVALID",
                "message": "apiKey and clearApiKey cannot be used together",
            },
        )
    if payload.callbackUrl is not None and payload.clearCallbackUrl:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INPUT_INVALID",
                "message": "callbackUrl and clearCallbackUrl cannot be used together",
            },
        )
    updates = {
        name: value
        for name, value in payload.model_dump(
            exclude={"clearApiKey", "clearCallbackUrl"},
            exclude_unset=True,
        ).items()
        if value is not None
    }
    if payload.clearApiKey:
        updates["apiKey"] = None
    if payload.clearCallbackUrl:
        updates["callbackUrl"] = None
    if not updates:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INPUT_INVALID",
                "message": "at least one Kling configuration change is required",
            },
        )
    try:
        result = update_kling_admin_config(request.app.state.settings, updates)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INPUT_INVALID", "message": str(exc)},
        ) from exc
    request.app.state.kling_adapter = create_kling_adapter(request.app.state.settings)
    request.app.state.kling_config_signature = kling_admin_config_signature(
        request.app.state.settings
    )
    session.add(
        AuditEvent(
            actor_id=actor.id,
            action="KLING_CONFIG_UPDATED",
            entity_type="provider_configuration",
            entity_id=str(result["provider"]),
            reason="administrator updated Kling provider configuration",
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[],
        )
    )
    await session.commit()
    return KlingConfigResponse.model_validate(result)


def _kling_status_payload(request: Request) -> dict[str, object]:
    availability = request.app.state.kling_adapter.availability_snapshot()
    capabilities = request.app.state.kling_adapter.capabilities_snapshot()
    settings = request.app.state.settings
    return {
        "enabled": settings.kling_enabled,
        "backend": "api",
        "provider": request.app.state.kling_adapter.get_provider_name(),
        "status": availability.status,
        "available": availability.available,
        "authenticated": availability.authenticated,
        "reason": availability.reason,
        "cliVersion": availability.cli_version,
        "checkedAt": capabilities.checked_at.isoformat() if capabilities else None,
        "supportedModels": list(capabilities.supported_models) if capabilities else [],
        "supportedTools": list(capabilities.supported_tools) if capabilities else [],
        "videoDurations": list(capabilities.video_durations) if capabilities else [],
        "aspectRatios": list(capabilities.aspect_ratios) if capabilities else [],
        "imageInputLimit": capabilities.image_input_limit if capabilities else 0,
        "supportsTailImage": capabilities.supports_tail_image if capabilities else False,
        "supportsMultipleImages": (
            capabilities.supports_multiple_images if capabilities else False
        ),
        "supportsWatermarkFreeOutput": (
            capabilities.supports_watermark_free_output if capabilities else False
        ),
        "verificationMode": "official_read_only_task_query",
        "verificationMayGenerateOrCharge": False,
    }


@router.get(
    "/kling/status",
    response_model=KlingStatusResponse,
    responses=KLING_ADMIN_ERROR_RESPONSES,
)
async def read_kling_status(actor: Actor, request: Request) -> KlingStatusResponse:
    require_admin(actor.role)
    _refresh_kling_config_from_disk(request)
    availability = await request.app.state.kling_adapter.check_availability()
    if availability.available:
        try:
            await request.app.state.kling_adapter.refresh_capabilities()
        except KlingCliError:
            pass
    return KlingStatusResponse.model_validate(_kling_status_payload(request))


@router.post(
    "/kling/capabilities/refresh",
    response_model=KlingStatusResponse,
    responses=KLING_ADMIN_ERROR_RESPONSES,
)
async def refresh_kling_capabilities(
    actor: Actor, session: Session, request: Request
) -> KlingStatusResponse:
    require_admin(actor.role)
    try:
        await request.app.state.kling_adapter.refresh_capabilities(force=True)
    except KlingCliError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    session.add(
        AuditEvent(
            actor_id=actor.id,
            action="KLING_CAPABILITIES_REFRESHED",
            entity_type="provider",
            entity_id=request.app.state.kling_adapter.get_provider_name(),
            reason="manual administrator refresh",
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[],
        )
    )
    await session.commit()
    return KlingStatusResponse.model_validate(_kling_status_payload(request))


async def _record_kling_auth_event(
    *,
    actor: Actor,
    session: Session,
    request: Request,
    action: str,
    reason: str,
) -> None:
    session.add(
        AuditEvent(
            actor_id=actor.id,
            action=action,
            entity_type="provider",
            entity_id=request.app.state.kling_adapter.get_provider_name(),
            reason=reason,
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[],
        )
    )
    await session.commit()


@router.post(
    "/kling/login",
    response_model=KlingStatusResponse,
    responses=KLING_ADMIN_ERROR_RESPONSES,
)
async def login_kling_account(
    actor: Actor, session: Session, request: Request
) -> KlingStatusResponse:
    require_admin(actor.role)
    try:
        await request.app.state.kling_adapter.login()
    except KlingCliError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    await _record_kling_auth_event(
        actor=actor,
        session=session,
        request=request,
        action="KLING_ACCOUNT_LOGGED_IN",
        reason="administrator completed Kling Provider authentication",
    )
    return KlingStatusResponse.model_validate(_kling_status_payload(request))


@router.post(
    "/kling/logout",
    response_model=KlingStatusResponse,
    responses=KLING_ADMIN_ERROR_RESPONSES,
)
async def logout_kling_account(
    actor: Actor, session: Session, request: Request
) -> KlingStatusResponse:
    require_admin(actor.role)
    try:
        await request.app.state.kling_adapter.logout()
    except KlingCliError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    await _record_kling_auth_event(
        actor=actor,
        session=session,
        request=request,
        action="KLING_ACCOUNT_LOGGED_OUT",
        reason="administrator logged out the Kling Provider account",
    )
    return KlingStatusResponse.model_validate(_kling_status_payload(request))


@router.get("/credentials")
async def read_credentials(actor: Actor, request: Request) -> dict[str, object]:
    require_credential_admin(actor.role)
    return credential_status(request.app.state.settings)


@router.patch("/credentials")
async def patch_credentials(
    payload: CredentialUpdateRequest,
    actor: Actor,
    session: Session,
    request: Request,
) -> dict[str, object]:
    require_credential_admin(actor.role)
    updates: dict[str, str | None] = {}
    if payload.libtvAccessKey is not None or payload.clearLibtvAccessKey:
        updates["libtvAccessKey"] = None if payload.clearLibtvAccessKey else payload.libtvAccessKey
    if payload.modelApiKey is not None or payload.clearModelApiKey:
        updates["modelApiKey"] = None if payload.clearModelApiKey else payload.modelApiKey
    if payload.modelBaseUrl is not None or payload.clearModelBaseUrl:
        updates["modelBaseUrl"] = None if payload.clearModelBaseUrl else payload.modelBaseUrl
    if not updates:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INPUT_INVALID",
                "message": "at least one credential change is required",
            },
        )
    try:
        result = update_admin_credentials(request.app.state.settings, updates)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INPUT_INVALID", "message": str(exc)},
        ) from exc
    request.app.state.libtv_adapter = create_libtv_adapter(request.app.state.settings)
    session.add(
        AuditEvent(
            actor_id=actor.id,
            action="UPDATE_PROVIDER_CREDENTIALS",
            entity_type="administrator_credentials",
            entity_id="runtime",
            reason="administrator updated provider credential configuration",
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[],
        )
    )
    await session.commit()
    return result


def require_admin(role: UserRole) -> None:
    if role not in {UserRole.ADMIN, UserRole.OPERATOR}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "administrator role is required")


def require_credential_admin(role: UserRole) -> None:
    if role is not UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "administrator role is required")


def _runtime_response(version: RuntimeConfigVersion) -> dict[str, Any]:
    return {
        "version": version.version,
        "config": version.config_json,
        "reason": version.change_reason,
        "createdAt": version.created_at.isoformat() if version.created_at else None,
        "rolledBackFrom": version.rolled_back_from,
    }


@router.get("/operations")
async def get_operations(actor: Actor, session: Session, request: Request) -> dict[str, Any]:
    require_admin(actor.role)
    snapshot = await operations_snapshot(session, request.app.state.settings)
    await session.commit()
    return snapshot


@router.get("/runtime-config")
async def read_runtime_config(actor: Actor, session: Session, request: Request) -> dict[str, Any]:
    require_admin(actor.role)
    current = await get_runtime_config(session, request.app.state.settings)
    if current is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "runtime config unavailable")
    await session.commit()
    return _runtime_response(current)


@router.patch("/runtime-config")
async def patch_runtime_config(
    payload: RuntimeConfigUpdateRequest,
    actor: Actor,
    session: Session,
    request: Request,
) -> dict[str, Any]:
    require_admin(actor.role)
    try:
        updated = await update_runtime_config(
            session,
            request.app.state.settings,
            config=payload.config,
            actor_id=actor.id,
            reason=payload.reason,
            expected_version=payload.expectedVersion,
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "RUNTIME_CONFIG_REJECTED", "message": str(exc)},
        ) from exc
    await session.commit()
    return _runtime_response(updated)


@router.post("/runtime-config/rollback")
async def post_runtime_config_rollback(
    payload: RuntimeConfigRollbackRequest,
    actor: Actor,
    session: Session,
    request: Request,
) -> dict[str, Any]:
    require_admin(actor.role)
    try:
        updated = await rollback_runtime_config(
            session,
            request.app.state.settings,
            target_version=payload.targetVersion,
            actor_id=actor.id,
            reason=payload.reason,
            expected_version=payload.expectedVersion,
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "RUNTIME_CONFIG_ROLLBACK_REJECTED", "message": str(exc)},
        ) from exc
    await session.commit()
    return _runtime_response(updated)


@router.post("/pause")
async def post_pause(
    payload: PauseRequest,
    actor: Actor,
    session: Session,
    request: Request,
) -> dict[str, Any]:
    require_admin(actor.role)
    current = await get_runtime_config(session, request.app.state.settings)
    if current is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "runtime config unavailable")
    config = deepcopy(current.config_json)
    key = "globalPaused" if payload.scope == "GLOBAL" else "paidSubmissionsPaused"
    config[key] = payload.paused
    try:
        updated = await update_runtime_config(
            session,
            request.app.state.settings,
            config=config,
            actor_id=actor.id,
            reason=payload.reason,
            expected_version=payload.expectedVersion,
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "PAUSE_STATE_CONFLICT", "message": str(exc)},
        ) from exc
    await session.commit()
    return _runtime_response(updated)


@router.post("/prompt-confirmation")
async def post_prompt_confirmation(
    payload: PromptConfirmationRequest,
    actor: Actor,
    session: Session,
    request: Request,
) -> dict[str, Any]:
    require_admin(actor.role)
    current = await get_runtime_config(session, request.app.state.settings)
    if current is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "runtime config unavailable")
    config = deepcopy(current.config_json)
    config["promptConfirmationRequired"] = not payload.automatic
    try:
        updated = await update_runtime_config(
            session,
            request.app.state.settings,
            config=config,
            actor_id=actor.id,
            reason=(
                "automatic prompt confirmation enabled"
                if payload.automatic
                else "manual prompt confirmation enabled"
            ),
            expected_version=payload.expectedVersion,
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "PROMPT_CONFIRMATION_STATE_CONFLICT", "message": str(exc)},
        ) from exc
    await session.commit()
    return _runtime_response(updated)


@router.get("/audit")
async def list_audit_events(
    actor: Actor, session: Session, limit: int = 100
) -> list[dict[str, Any]]:
    require_admin(actor.role)
    safe_limit = min(max(limit, 1), 200)
    events = list(
        await session.scalars(
            select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(safe_limit)
        )
    )
    return [
        {
            "id": str(event.id),
            "actorId": str(event.actor_id) if event.actor_id else None,
            "action": event.action,
            "entityType": event.entity_type,
            "entityId": event.entity_id,
            "fromState": event.from_state,
            "toState": event.to_state,
            "reason": event.reason,
            "correlationId": event.correlation_id,
            "evidenceCount": len(event.evidence_refs_json),
            "createdAt": event.created_at.isoformat(),
        }
        for event in events
    ]


@router.post("/model-registry/refresh")
async def refresh_registry(
    actor: Actor,
    session: Session,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, str]:
    require_admin(actor.role)
    operation = "REFRESH_MODEL_REGISTRY"
    if cached := await _claim_admin_action(session, actor.id, operation, idempotency_key, {}):
        return cached
    try:
        snapshot = await refresh_model_registry(session, request.app.state.settings, force=True)
    except ModelRegistryError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "MODEL_SCHEMA_INCOMPATIBLE", "message": str(exc)},
        ) from exc
    session.add(
        AuditEvent(
            actor_id=actor.id,
            action="REFRESH_MODEL_SCHEMA",
            entity_type="model_schema_snapshot",
            entity_id=str(snapshot.id),
            reason="administrator forced read-only refresh",
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[],
        )
    )
    response = {
        "modelKey": snapshot.model_key,
        "compatibilityFingerprint": snapshot.compatibility_fingerprint,
        "expiresAt": snapshot.expires_at.isoformat(),
    }
    await _complete_admin_action(session, actor.id, operation, idempotency_key, {}, response)
    return response


async def _claim_admin_action(
    session: Session,
    actor_id: uuid.UUID,
    operation: str,
    key: str,
    payload: dict[str, object],
) -> dict[str, Any] | None:
    try:
        cached = await load_idempotent_response(
            session,
            tenant_id=str(actor_id),
            operation_type=operation,
            key=key,
            payload=payload,
        )
    except (IdempotencyConflictError, IdempotencyInProgressError) as exc:
        code = (
            "IDEMPOTENCY_REQUEST_IN_PROGRESS"
            if isinstance(exc, IdempotencyInProgressError)
            else "IDEMPOTENCY_KEY_REUSED"
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": code, "message": str(exc)}
        ) from exc
    return cached[1] if cached else None


async def _complete_admin_action(
    session: Session,
    actor_id: uuid.UUID,
    operation: str,
    key: str,
    payload: dict[str, object],
    response: dict[str, Any],
) -> None:
    await store_idempotent_response(
        session,
        tenant_id=str(actor_id),
        operation_type=operation,
        key=key,
        payload=payload,
        response_status=200,
        response_body=response,
    )
    await session.commit()


async def _release_admin_action(
    session: Session,
    actor_id: uuid.UUID,
    operation: str,
    key: str,
    payload: dict[str, object],
) -> None:
    await release_idempotency_claim(
        session,
        tenant_id=str(actor_id),
        operation_type=operation,
        key=key,
        payload=payload,
    )


def _normalized_libtv_accounts(payload: dict[str, Any]) -> list[dict[str, object]]:
    container = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    raw_accounts = container.get("accounts") if isinstance(container, dict) else None
    if not isinstance(raw_accounts, list):
        return []
    accounts: list[dict[str, object]] = []
    for raw in raw_accounts:
        if not isinstance(raw, dict):
            continue
        account_id = raw.get("accountId")
        account_name = raw.get("accountName")
        if account_id is None or not isinstance(account_name, str) or not account_name:
            continue
        accounts.append(
            {
                "accountId": str(account_id),
                "accountName": account_name,
                "accountType": str(raw.get("accountType") or "UNKNOWN"),
                "isActive": bool(raw.get("isActive")),
                "teamId": raw.get("teamId"),
            }
        )
    return accounts


async def _libtv_account_status(
    actor: Actor,
    session: Session,
    request: Request,
) -> dict[str, object]:
    require_credential_admin(actor.role)
    settings = request.app.state.settings
    login_in_progress = await request.app.state.libtv_login_manager.in_progress()
    if settings.libtv_adapter_mode != "real":
        return {
            "available": False,
            "authenticated": False,
            "loginInProgress": login_in_progress,
            "activeAccount": None,
            "accounts": [],
        }
    try:
        payload = await request.app.state.libtv_adapter.list_accounts()
    except LibTVError as exc:
        if exc.code != "LIBTV_AUTH_REQUIRED":
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        await set_libtv_auth_required(
            session,
            settings,
            required=True,
            reason="administrator settings detected an expired LibTV login",
        )
        return {
            "available": True,
            "authenticated": False,
            "loginInProgress": login_in_progress,
            "activeAccount": None,
            "accounts": [],
        }

    await set_libtv_auth_required(
        session,
        settings,
        required=False,
        reason="administrator settings verified the LibTV login",
    )
    accounts = _normalized_libtv_accounts(payload)
    active_account = next((item for item in accounts if item["isActive"]), None)
    return {
        "available": True,
        "authenticated": True,
        "loginInProgress": login_in_progress,
        "activeAccount": active_account,
        "accounts": accounts,
    }


@router.get("/libtv-account")
async def read_libtv_account(
    actor: Actor,
    session: Session,
    request: Request,
) -> dict[str, object]:
    response = await _libtv_account_status(actor, session, request)
    await session.commit()
    return response


@router.post("/libtv-login/start")
async def start_libtv_login(
    actor: Actor,
    session: Session,
    request: Request,
) -> dict[str, Any]:
    require_credential_admin(actor.role)
    settings = request.app.state.settings
    if settings.libtv_adapter_mode != "real":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "LIBTV_LOGIN_UNAVAILABLE",
                "message": "LibTV browser login is available only in real adapter mode",
            },
        )
    try:
        started = await request.app.state.libtv_login_manager.start(
            settings.libtv_executable,
            settings.libtv_config_dir,
        )
    except LibTVLoginStartError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    response = started.as_response()
    session.add(
        AuditEvent(
            actor_id=actor.id,
            action="START_LIBTV_BROWSER_LOGIN",
            entity_type="libtv_login_session",
            entity_id=started.session_id,
            reason="administrator started the official LibTV browser login flow",
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[],
        )
    )
    await session.commit()
    return response


@router.post("/libtv-account/use")
async def use_libtv_account(
    payload: LibTVAccountUseRequest,
    actor: Actor,
    session: Session,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, Any]:
    require_credential_admin(actor.role)
    settings = request.app.state.settings
    if settings.libtv_adapter_mode != "real":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "LIBTV_ACCOUNT_SWITCH_UNAVAILABLE",
                "message": "LibTV account switching is available only in real adapter mode",
            },
        )
    account = payload.account.strip()
    payload_json = {"account": account}
    operation = f"USE_LIBTV_ACCOUNT:{account}"
    if cached := await _claim_admin_action(
        session,
        actor.id,
        operation,
        idempotency_key,
        payload_json,
    ):
        return cached
    try:
        result = await request.app.state.libtv_adapter.use_account(account)
    except LibTVError as exc:
        await _release_admin_action(
            session,
            actor.id,
            operation,
            idempotency_key,
            payload_json,
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    await set_libtv_auth_required(
        session,
        settings,
        required=False,
        reason="administrator switched the active LibTV account",
    )
    response = {
        "ok": bool(result.get("ok", True)),
        "accountId": str(result.get("accountId") or account),
        "accountName": str(result.get("accountName") or account),
        "accountType": str(result.get("accountType") or "UNKNOWN"),
        "teamId": result.get("teamId"),
        "alreadyActive": bool(result.get("alreadyActive", False)),
    }
    session.add(
        AuditEvent(
            actor_id=actor.id,
            action="USE_LIBTV_ACCOUNT",
            entity_type="libtv_account",
            entity_id=response["accountId"],
            reason="administrator switched the active LibTV account scope",
            correlation_id=str(uuid.uuid4()),
            evidence_refs_json=[],
        )
    )
    await _complete_admin_action(
        session,
        actor.id,
        operation,
        idempotency_key,
        payload_json,
        response,
    )
    return response


@router.get("/reconciliations")
async def list_reconciliations(actor: Actor, session: Session) -> list[dict[str, object]]:
    require_admin(actor.role)
    attempts = list(
        await session.scalars(
            select(GenerationAttempt)
            .where(GenerationAttempt.status == AttemptStatus.UNKNOWN_AFTER_SUBMIT)
            .order_by(GenerationAttempt.updated_at)
        )
    )
    return [
        {
            "attemptId": str(attempt.id),
            "projectUuid": attempt.project_uuid,
            "nodeKey": attempt.video_node_key,
            "taskId": attempt.task_id,
            "status": attempt.status.value,
            "chargeStatus": attempt.charge_status.value,
            "errorCode": attempt.last_error_code,
            "updatedAt": attempt.updated_at.isoformat(),
        }
        for attempt in attempts
    ]


@router.post("/reconciliations/{attempt_id}/classify")
async def classify_reconciliation(
    attempt_id: uuid.UUID,
    payload: ReconcileRequest,
    actor: Actor,
    session: Session,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, str]:
    require_admin(actor.role)
    actor_id = actor.id
    operation = f"RECONCILE_ATTEMPT:{attempt_id}"
    payload_json = payload.model_dump(mode="json", by_alias=True)
    if cached := await _claim_admin_action(
        session, actor_id, operation, idempotency_key, payload_json
    ):
        return cached
    attempt = await session.get(GenerationAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "attempt was not found")
    if payload.action == "MARK_MANUAL_REVIEW":
        if attempt.status != AttemptStatus.UNKNOWN_AFTER_SUBMIT:
            raise HTTPException(status.HTTP_409_CONFLICT, "attempt is not unknown")
        attempt.status = AttemptStatus.NEEDS_MANUAL_REVIEW
        attempt.state_version += 1
        response = {"status": attempt.status.value}
        await _complete_admin_action(
            session, actor_id, operation, idempotency_key, payload_json, response
        )
        return response
    result = await RunnerSupervisor(
        request.app.state.libtv_adapter,
        request.app.state.object_store,
        request.app.state.settings,
        kling_adapter=request.app.state.kling_adapter,
    ).reconcile_attempt(session, attempt_id)
    settings = request.app.state.settings
    if settings.auto_run_fake_commands and settings.libtv_adapter_mode in {"fake", "replay"}:
        await RunnerSupervisor(
            request.app.state.libtv_adapter,
            request.app.state.object_store,
            settings,
            kling_adapter=request.app.state.kling_adapter,
        ).run_ready(session)
    response = {"status": result}
    await _complete_admin_action(
        session, actor_id, operation, idempotency_key, payload_json, response
    )
    return response


@router.post("/tasks/{task_id}/retry-materialization")
async def retry_materialization(
    task_id: uuid.UUID,
    actor: Actor,
    session: Session,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, str]:
    require_admin(actor.role)
    operation = f"RETRY_MATERIALIZATION:{task_id}"
    if cached := await _claim_admin_action(session, actor.id, operation, idempotency_key, {}):
        return cached
    task = await session.get(ParentTask, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task was not found")
    try:
        await confirm_task(
            session,
            request.app.state.libtv_adapter,
            request.app.state.object_store,
            task,
            actor.id,
            request.app.state.settings,
            kling_adapter=request.app.state.kling_adapter,
            accept_risk=True,
            expected_state_version=task.state_version,
            allow_materialization_recovery=True,
        )
    except (ValueError, LibTVError) as exc:
        code = exc.code if isinstance(exc, LibTVError) else "MATERIALIZATION_RECOVERY_REJECTED"
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": code, "message": str(exc)}
        ) from exc
    settings = request.app.state.settings
    if settings.auto_run_fake_commands and settings.libtv_adapter_mode in {"fake", "replay"}:
        await RunnerSupervisor(
            request.app.state.libtv_adapter,
            request.app.state.object_store,
            settings,
            kling_adapter=request.app.state.kling_adapter,
        ).run_ready(session)
    response = {"status": task.phase.value}
    await _complete_admin_action(session, actor.id, operation, idempotency_key, {}, response)
    return response
