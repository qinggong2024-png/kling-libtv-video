from fastapi import APIRouter
from libtv_agent.api.dependencies import Actor
from libtv_agent.templates.motion_actions import list_motion_actions

router = APIRouter(prefix="/motion-actions", tags=["motion-actions"])


@router.get("")
async def get_motion_actions(actor: Actor) -> list[dict[str, object]]:
    del actor
    return [action.to_public_dict() for action in list_motion_actions()]
