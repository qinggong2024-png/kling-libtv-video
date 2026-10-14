from fastapi import APIRouter, Request
from libtv_agent.api.dependencies import Actor, Session
from libtv_agent.services.ai_pricing import load_price_catalog
from libtv_agent.services.ai_usage import read_ai_quota

router = APIRouter(prefix="/ai-usage", tags=["ai-usage"])


@router.get("/quota")
async def get_quota(actor: Actor, session: Session, request: Request) -> dict:
    return await read_ai_quota(session, request.app.state.settings, user_id=actor.id)


@router.get("/prices")
async def get_prices(actor: Actor, request: Request) -> dict:
    return load_price_catalog(request.app.state.settings).model_dump(mode="json")
