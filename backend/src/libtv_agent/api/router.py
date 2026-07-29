from fastapi import APIRouter
from libtv_agent.api.admin import router as admin_router
from libtv_agent.api.auth import router as auth_router
from libtv_agent.api.confirmations import router as confirmations_router
from libtv_agent.api.downloads import router as downloads_router
from libtv_agent.api.events import router as events_router
from libtv_agent.api.health import router as health_router
from libtv_agent.api.system import router as system_router
from libtv_agent.api.tasks import router as tasks_router
from libtv_agent.api.uploads import router as uploads_router
from libtv_agent.api.users import router as users_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(system_router)
api_router.include_router(tasks_router)
api_router.include_router(uploads_router)
api_router.include_router(downloads_router)
api_router.include_router(events_router)
api_router.include_router(admin_router)
api_router.include_router(users_router)
api_router.include_router(confirmations_router)
