import asyncio
import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from libtv_agent.api.dependencies import Actor
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.models import ParentTask
from libtv_agent.services.observability import operations_snapshot
from sqlalchemy import select

router = APIRouter(tags=["events"])


@router.get("/events")
async def events(actor: Actor, request: Request, once: bool = False) -> StreamingResponse:
    async def stream():
        while True:
            async with request.app.state.database.session_factory() as session:
                if actor.role in {UserRole.ADMIN, UserRole.OPERATOR}:
                    payload = await operations_snapshot(session, request.app.state.settings)
                    event_name = "operations.snapshot"
                    await session.commit()
                else:
                    tasks = list(
                        await session.scalars(
                            select(ParentTask)
                            .where(ParentTask.user_id == actor.id)
                            .order_by(ParentTask.updated_at.desc())
                            .limit(100)
                        )
                    )
                    payload = {
                        "userId": str(actor.id),
                        "tasks": [
                            {
                                "id": str(task.id),
                                "phase": task.phase.value,
                                "stateVersion": task.state_version,
                                "updatedAt": task.updated_at.isoformat(),
                            }
                            for task in tasks
                        ],
                    }
                    event_name = "tasks.snapshot"
            event_id = str(time.time_ns())
            serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
            yield f"id: {event_id}\nevent: {event_name}\ndata: {serialized}\n\n"
            if once or await request.is_disconnected():
                break
            await asyncio.sleep(request.app.state.settings.sse_heartbeat_seconds)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
