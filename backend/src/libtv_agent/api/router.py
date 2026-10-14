from fastapi import APIRouter
from libtv_agent.api.admin import router as admin_router
from libtv_agent.api.auth import router as auth_router
from libtv_agent.api.confirmations import router as confirmations_router
from libtv_agent.api.controlled_image_bridge import router as controlled_image_bridge_router
from libtv_agent.api.creative_workflow import router as creative_workflow_router
from libtv_agent.api.cutflow_handoffs import router as cutflow_handoffs_router
from libtv_agent.api.downloads import router as downloads_router
from libtv_agent.api.events import router as events_router
from libtv_agent.api.health import router as health_router
from libtv_agent.api.human_reviews import router as human_reviews_router
from libtv_agent.api.image_generations import router as image_generations_router
from libtv_agent.api.kling import router as kling_router
from libtv_agent.api.motion_actions import router as motion_actions_router
from libtv_agent.api.products import router as products_router
from libtv_agent.api.prompt_presets import router as prompt_presets_router
from libtv_agent.api.site_style_profiles import router as site_style_profiles_router
from libtv_agent.api.submission_recovery import router as submission_recovery_router
from libtv_agent.api.system import router as system_router
from libtv_agent.api.tasks import router as tasks_router
from libtv_agent.api.uploads import router as uploads_router
from libtv_agent.api.users import router as users_router
from libtv_agent.api.video_tasks import router as video_tasks_router
from libtv_agent.api.video_templates import router as video_templates_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(image_generations_router)
api_router.include_router(kling_router)
api_router.include_router(auth_router)
api_router.include_router(system_router)
api_router.include_router(tasks_router)
api_router.include_router(uploads_router)
api_router.include_router(downloads_router)
api_router.include_router(events_router)
api_router.include_router(admin_router)
api_router.include_router(users_router)
api_router.include_router(confirmations_router)
api_router.include_router(cutflow_handoffs_router)
api_router.include_router(video_templates_router)
api_router.include_router(motion_actions_router)
api_router.include_router(prompt_presets_router)
api_router.include_router(site_style_profiles_router)
api_router.include_router(video_tasks_router)
api_router.include_router(submission_recovery_router)
api_router.include_router(products_router)
api_router.include_router(creative_workflow_router)
api_router.include_router(controlled_image_bridge_router)
api_router.include_router(human_reviews_router)
