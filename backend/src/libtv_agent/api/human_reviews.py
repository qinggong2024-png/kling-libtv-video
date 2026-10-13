"""Human production feedback routes; registration is owned by the integration PM."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.creative.human_review import (
    HumanReviewExport,
    HumanReviewExportQuery,
    HumanReviewList,
    HumanReviewQuery,
    HumanReviewRecord,
    HumanReviewRequest,
)
from libtv_agent.services.human_reviews import (
    HumanReviewError,
    create_review,
    export_reviews,
    list_reviews,
)

router = APIRouter(prefix="/human-reviews", tags=["human-production-reviews"])


def _http_error(exc: HumanReviewError) -> HTTPException:
    return HTTPException(exc.status_code, detail={"code": exc.code, "message": exc.code})


@router.get("/export", response_model=HumanReviewExport)
async def export(
    query: Annotated[HumanReviewExportQuery, Query()],
    request: Request, actor: Actor, session: Session,
) -> HumanReviewExport:
    try:
        return await export_reviews(
            session, actor.id, query, mode=request.app.state.settings.ai_adapter_mode,
            include_synthetic=query.include_synthetic,
        )
    except HumanReviewError as exc:
        raise _http_error(exc) from exc


@router.get("", response_model=HumanReviewList)
async def read(
    query: Annotated[HumanReviewQuery, Query()],
    request: Request, actor: Actor, session: Session,
) -> HumanReviewList:
    try:
        return await list_reviews(
            session, actor.id, query, mode=request.app.state.settings.ai_adapter_mode,
        )
    except HumanReviewError as exc:
        raise _http_error(exc) from exc


@router.post("", response_model=HumanReviewRecord, status_code=201)
async def create(
    payload: HumanReviewRequest, request: Request, actor: Actor, session: Session,
) -> HumanReviewRecord:
    try:
        return await create_review(
            session, actor, payload, mode=request.app.state.settings.ai_adapter_mode,
        )
    except HumanReviewError as exc:
        raise _http_error(exc) from exc
