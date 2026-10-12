from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from libtv_agent.api.dependencies import Actor, Session, require_review_write
from libtv_agent.services.controlled_image_bridge import (
    ControlledImageBridgePreflight,
    ControlledImageBridgeRejected,
    preflight_controlled_image_bridge,
)
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/creative-production-bridge", tags=["controlled-image-bridge"])


class ControlledImageBridgePreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_version: int = Field(ge=0)


@router.post(
    "/tasks/{task_id}/preflight",
    response_model=ControlledImageBridgePreflight,
)
async def preflight(
    task_id: uuid.UUID,
    payload: ControlledImageBridgePreflightRequest,
    request: Request,
    actor: Actor,
    session: Session,
) -> ControlledImageBridgePreflight:
    require_review_write(actor)
    try:
        return await preflight_controlled_image_bridge(
            session,
            task_id=task_id,
            owner_id=actor.id,
            expected_version=payload.expected_version,
            policy=getattr(request.app.state, "controlled_image_bridge_policy", None),
            object_store=request.app.state.object_store,
            settings=request.app.state.settings,
        )
    except ControlledImageBridgeRejected as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code}) from exc
