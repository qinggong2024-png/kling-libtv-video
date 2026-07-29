from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from libtv_agent.services.database_schema import inspect_database_schema
from sqlalchemy import text

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    try:
        async with request.app.state.database.session_factory() as session:
            await session.execute(text("SELECT 1"))
            connection = await session.connection()
            schema = await connection.run_sync(inspect_database_schema)
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "checks": {"postgresql": "unavailable"}},
        )
    if not schema.ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "degraded",
                "checks": {
                    "postgresql": "ok",
                    "databaseSchema": "outdated",
                },
                "databaseSchema": {
                    "currentRevisions": schema.current_revisions,
                    "expectedRevisions": schema.expected_revisions,
                    "missingTables": schema.missing_tables,
                },
            },
        )
    return JSONResponse(
        content={
            "status": "ok",
            "checks": {"postgresql": "ok", "databaseSchema": "ok"},
        }
    )
