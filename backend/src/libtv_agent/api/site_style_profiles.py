from fastapi import APIRouter
from libtv_agent.api.dependencies import Actor
from libtv_agent.templates.site_style_profiles import list_site_style_profiles

router = APIRouter(prefix="/site-style-profiles", tags=["site-style-profiles"])


@router.get("")
async def get_site_style_profiles(actor: Actor) -> list[dict[str, object]]:
    del actor
    return [profile.to_public_dict() for profile in list_site_style_profiles()]
