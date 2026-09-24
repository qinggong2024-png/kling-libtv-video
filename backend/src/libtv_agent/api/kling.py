from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.models import SubjectElementJob
from libtv_agent.services.kling_callbacks import (
    KlingCallbackError,
)
from libtv_agent.services.kling_elements import (
    KlingElementError,
    create_element,
    delete_element,
    get_element,
    list_elements,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

router = APIRouter(tags=["kling"])


class KlingOperationErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class KlingOperationErrorResponse(BaseModel):
    detail: str | KlingOperationErrorDetail


ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {"model": KlingOperationErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": KlingOperationErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": KlingOperationErrorResponse},
    status.HTTP_409_CONFLICT: {"model": KlingOperationErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": KlingOperationErrorResponse},
    status.HTTP_501_NOT_IMPLEMENTED: {"model": KlingOperationErrorResponse},
    status.HTTP_502_BAD_GATEWAY: {"model": KlingOperationErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": KlingOperationErrorResponse},
}


class KlingCallbackOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str
    url: str | None = Field(default=None, max_length=4096)


class KlingCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=160)
    status: Literal["submitted", "processing", "succeeded", "failed"]
    message: str | None = Field(default=None, max_length=4000)
    create_time: int | str | None = None
    update_time: int | str | None = None
    external_id: str | None = Field(default=None, max_length=160)
    outputs: list[KlingCallbackOutput] = Field(default_factory=list, max_length=20)
    billing: list[dict[str, Any]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_envelope(cls, value: Any) -> Any:
        if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
            return value
        data = dict(value["data"])
        if "message" not in data and value.get("message") is not None:
            data["message"] = value["message"]
        return data


class KlingCallbackResponse(BaseModel):
    accepted: bool = True
    providerTaskId: str
    status: str
    duplicate: bool
    workflowFinalized: bool


class KlingElementCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    description: str = Field(min_length=1, max_length=100)
    imageReferences: list[str] = Field(default_factory=list, max_length=4)
    videoReferences: list[str] = Field(default_factory=list, max_length=1)
    voiceId: str | None = Field(default=None, max_length=160)
    tagIds: list[str] = Field(default_factory=list, max_length=20)
    callbackUrl: str | None = Field(default=None, max_length=2048)
    externalId: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validate_source(self) -> KlingElementCreateRequest:
        if bool(self.imageReferences) == bool(self.videoReferences):
            raise ValueError("exactly one of imageReferences or videoReferences is required")
        total_reference_characters = sum(
            len(reference) for reference in [*self.imageReferences, *self.videoReferences]
        )
        if total_reference_characters > 70 * 1024 * 1024:
            raise ValueError("element reference payload exceeds 70 MiB")
        return self


class KlingElementRead(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    status: str
    imageUrls: list[str] = Field(default_factory=list)
    videoUrl: str | None = None
    voiceId: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("createdAt", "updatedAt", mode="before")
    @classmethod
    def _normalize_timestamp(cls, value: Any) -> Any:
        """把可灵返回的时间戳归一化。

        可灵对没有时间戳的元素返回 ``0``（int），而字段声明为 ``str | None``；
        pydantic v2 不做 int→str 隐式转换，直接校验会让整个列表接口 500。
        """
        if isinstance(value, (int, float)):
            return None if not value else str(value)
        if value is None or value == "":
            return None
        return value


class KlingElementListResponse(BaseModel):
    items: list[KlingElementRead]
    pageNum: int
    pageSize: int
    total: int
    official: bool


def _require_admin(actor: Actor) -> None:
    if actor.role not in {UserRole.ADMIN, UserRole.OPERATOR}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "administrator role is required")


def _operation_error(exc: KlingCallbackError | KlingElementError) -> HTTPException:
    return HTTPException(
        exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.post(
    "/kling/callback",
    response_model=KlingCallbackResponse,
    responses=ERROR_RESPONSES,
)
async def receive_kling_callback() -> KlingCallbackResponse:
    # Fail closed until a verified source-authentication contract is implemented.
    # Runner polling remains responsible for download and financial settlement.
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail={
            "code": "KLING_CALLBACK_DISABLED",
            "message": (
                "Callbacks are disabled pending source authentication; task polling remains active"
            ),
            "retryable": False,
        },
    )


@router.post(
    "/admin/kling/elements",
    response_model=KlingElementRead,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
async def create_kling_element(
    payload: KlingElementCreateRequest,
    actor: Actor,
    request: Request,
) -> KlingElementRead:
    _require_admin(actor)
    try:
        result = await create_element(
            request.app.state.kling_adapter,
            payload.model_dump(exclude_none=True),
        )
    except KlingElementError as exc:
        raise _operation_error(exc) from exc
    return KlingElementRead.model_validate(result)


@router.get(
    "/admin/kling/elements",
    response_model=KlingElementListResponse,
    responses=ERROR_RESPONSES,
)
async def list_kling_elements(
    actor: Actor,
    session: Session,
    request: Request,
    page_num: Annotated[int, Query(alias="pageNum", ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=500)] = 30,
    official: bool = False,
) -> KlingElementListResponse:
    try:
        result = await list_elements(
            request.app.state.kling_adapter,
            page_num=page_num,
            page_size=page_size,
            official=official,
        )
    except KlingElementError as exc:
        raise _operation_error(exc) from exc
    if not official:
        local_jobs = list(
            await session.scalars(
                select(SubjectElementJob)
                .where(
                    SubjectElementJob.user_id == actor.id,
                    SubjectElementJob.status.in_(("PENDING", "PROCESSING", "FAILED")),
                )
                .order_by(SubjectElementJob.created_at.desc())
            )
        )
        local_items = [
            {
                "id": f"local-job:{job.id}",
                "name": job.name,
                "description": job.description,
                "status": job.status.lower(),
                "imageUrls": [],
                "createdAt": job.created_at.isoformat() if job.created_at else None,
                "updatedAt": job.updated_at.isoformat() if job.updated_at else None,
                "raw": {
                    "localJob": True,
                    "taskId": str(job.parent_task_id),
                    "attemptCount": job.attempt_count,
                    "errorCode": job.last_error_code,
                    "errorMessage": job.last_error_message,
                },
            }
            for job in local_jobs
        ]
        result["items"] = [*local_items, *result["items"]]
        result["total"] = int(result["total"]) + len(local_items)
    return KlingElementListResponse.model_validate(result)


@router.get(
    "/admin/kling/elements/{element_id}",
    response_model=KlingElementRead,
    responses=ERROR_RESPONSES,
)
async def read_kling_element(
    element_id: str,
    actor: Actor,
    request: Request,
) -> KlingElementRead:
    del actor
    try:
        result = await get_element(request.app.state.kling_adapter, element_id)
    except KlingElementError as exc:
        raise _operation_error(exc) from exc
    return KlingElementRead.model_validate(result)


@router.delete(
    "/admin/kling/elements/{element_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ERROR_RESPONSES,
)
async def delete_kling_element(
    element_id: str,
    actor: Actor,
    request: Request,
) -> Response:
    _require_admin(actor)
    try:
        await delete_element(request.app.state.kling_adapter, element_id)
    except KlingElementError as exc:
        raise _operation_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
