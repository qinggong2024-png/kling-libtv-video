from fastapi import APIRouter
from libtv_agent.api.dependencies import Actor
from libtv_agent.templates.video_templates import list_video_templates

router = APIRouter(prefix="/video-templates", tags=["video-templates"])


@router.get("")
async def get_video_templates(actor: Actor) -> list[dict[str, object]]:
    del actor
    return [template.to_public_dict() for template in list_video_templates()]
