"""API-only recovery entry point: login and persisted task queries, no workers."""

import re
from contextlib import asynccontextmanager

from fastapi.responses import JSONResponse

from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.db import Database


def create_maintenance_app(settings: Settings | None = None):
    app = create_app(settings)
    if not app.state.settings.shared_authentication_enabled:
        raise ValueError("Maintenance API requires shared authentication")

    @asynccontextmanager
    async def lifespan(application):
        application.state.database = Database(application.state.settings.database_url)
        try:
            yield
        finally:
            await application.state.database.dispose()

    # Replace the normal lifecycle before startup: no recovery or provider probes.
    app.router.lifespan_context = lifespan

    @app.middleware("http")
    async def maintenance_boundary(request, call_next):
        path = request.url.path
        readable = path in {
            "/api/v1/health/live", "/api/v1/health/ready",
            "/api/v1/system/status", "/api/v1/auth/me", "/api/v1/tasks",
        } or re.fullmatch(
            r"/api/v1/(tasks|image-generation-batches)/[0-9a-fA-F-]{36}", path
        ) is not None
        session_action = request.method == "POST" and path in {
            "/api/v1/auth/login", "/api/v1/auth/logout",
        }
        if not (request.method in {"GET", "HEAD"} and readable or session_action):
            return JSONResponse(status_code=503, content={"detail": {
                "code": "MAINTENANCE_QUERY_ONLY",
                "message": "当前仅支持登录和查询已保存任务，生成暂不可用。",
            }})
        response = await call_next(request)
        response.headers["X-LibTV-Maintenance"] = "query-only"
        return response

    return app
