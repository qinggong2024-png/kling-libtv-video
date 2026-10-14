"""Run with python -m libtv_agent.runner.cutflow_worker [--once].

Run one instance per LibTV installation. Row leases recover crashes and fence stale writes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from libtv_agent.adapters.object_store import ObjectStore, create_object_store
from libtv_agent.config import Settings, get_settings
from libtv_agent.db import Database
from libtv_agent.domain.models import CutflowHandoff, DownloadArtifact
from libtv_agent.services.cutflow_handoff import (
    CutflowHandoffError,
    import_outputs,
    publish_package,
    require_configuration,
)
from sqlalchemy import or_, select, update


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def control_request(settings: Settings, method: str, suffix: str, payload=None) -> dict:
    require_configuration(settings)
    request = Request(
        (settings.cutflow_base_url or "").rstrip("/") + "/api/integrations/libtv" + suffix,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {settings.cutflow_service_token}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with build_opener(NoRedirect()).open(
            request,
            timeout=settings.cutflow_request_timeout_seconds,
        ) as response:
            raw = response.read(1_048_577)
    except HTTPError as exc:
        # Do not log remote response bodies, credentials, or filesystem paths.
        raise CutflowHandoffError(
            "CUTFLOW_HTTP_ERROR",
            f"Cutflow 控制接口返回 HTTP {exc.code}",
        ) from None
    if len(raw) > 1_048_576:
        raise CutflowHandoffError("INVALID_RESULT", "Cutflow 控制响应过大")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise CutflowHandoffError("INVALID_RESULT", "Cutflow 控制响应格式错误")
    return result


async def _heartbeat(database: Database, handoff_id: uuid.UUID, token: str) -> None:
    while True:
        await asyncio.sleep(20)
        async with database.session_factory() as session:
            await session.execute(
                update(CutflowHandoff)
                .where(CutflowHandoff.id == handoff_id, CutflowHandoff.lease_token == token)
                .values(lease_until=datetime.now(UTC) + timedelta(minutes=5))
            )
            await session.commit()


async def tick(database: Database, settings: Settings, object_store: ObjectStore) -> bool:
    require_configuration(settings)
    now = datetime.now(UTC)
    token = str(uuid.uuid4())
    eligible = (
        CutflowHandoff.status.not_in(["FAILED", "CANCELED"]),
        or_(CutflowHandoff.lease_until.is_(None), CutflowHandoff.lease_until < now),
        or_(CutflowHandoff.next_run_at.is_(None), CutflowHandoff.next_run_at <= now),
    )
    async with database.session_factory() as session:
        row = await session.scalar(
            select(CutflowHandoff)
            .where(*eligible)
            .order_by(CutflowHandoff.next_run_at, CutflowHandoff.created_at)
            .limit(1)
        )
        if row is None:
            return False
        claimed = await session.execute(
            update(CutflowHandoff)
            .where(CutflowHandoff.id == row.id, *eligible)
            .values(lease_token=token, lease_until=now + timedelta(minutes=5))
            .execution_options(synchronize_session=False)
        )
        await session.commit()
        if claimed.rowcount != 1:
            return False
        await session.refresh(row)
        artifact = await session.get(DownloadArtifact, row.artifact_id)
    heartbeat = asyncio.create_task(_heartbeat(database, row.id, token))
    try:
        if not row.manifest_path:
            descriptor = await publish_package(row, artifact, settings, object_store)
            # Persist the published descriptor before contacting Cutflow. A lost
            # HTTP response can safely replay the exact same immutable import.
            async with database.session_factory() as session:
                await session.execute(
                    update(CutflowHandoff)
                    .where(CutflowHandoff.id == row.id, CutflowHandoff.lease_token == token)
                    .values(
                        manifest_path=f"inbox/{row.handoff_key}/manifest.json",
                        manifest_json=descriptor,
                        status="READY",
                    )
                )
                await session.commit()
            row.manifest_json = descriptor
        if not row.cutflow_batch_id:
            await asyncio.to_thread(control_request, settings, "POST", "", row.manifest_json)
        response = await asyncio.to_thread(
            control_request,
            settings,
            "GET",
            f"/{row.handoff_key}?userId={row.user_id}",
        )
        if response.get("handoffId") != row.handoff_key:
            raise CutflowHandoffError("INVALID_RESULT", "Cutflow 交接标识不匹配")
        remote_status = response.get("status")
        if remote_status not in {
            "importing",
            "uploading",
            "reference_queued",
            "analyzing_reference",
            "creating_proxies",
            "detecting_products",
            "regroup_queued",
            "reference_ready",
            "batch_queued",
            "editing",
            "review",
            "revision_queued",
            "revising",
            "cancel_requested",
            "canceled",
            "completed",
            "failed",
        }:
            raise CutflowHandoffError("INVALID_RESULT", "Cutflow 状态未识别")
        if remote_status == "failed":
            raise CutflowHandoffError("CUTFLOW_IMPORT_FAILED", "Cutflow 处理失败，请检查剪辑端")
        outputs = response.get("outputs", [])
        if not isinstance(outputs, list):
            raise CutflowHandoffError("INVALID_RESULT", "Cutflow 成片列表无效")
        saved = await import_outputs(row, outputs, settings, object_store)
        batch_id = response.get("batchId")
        if batch_id is not None:
            uuid.UUID(batch_id)
        if row.cutflow_batch_id and batch_id != row.cutflow_batch_id:
            raise CutflowHandoffError("INVALID_RESULT", "Cutflow 批次标识发生变化")
        state = (
            "CANCELED"
            if remote_status == "canceled"
            else "PENDING_REVIEW"
            if saved
            else (
                "AWAITING_EDIT"
                if remote_status in {"uploading", "reference_ready"}
                else "CANCELED"
                if remote_status == "canceled"
                else "EDITING"
                if batch_id
                else "IMPORTING"
            )
        )
        values = {
            "status": state,
            "outputs_json": saved,
            "cutflow_batch_id": batch_id,
            "cutflow_editor_url": settings.cutflow_base_url.rstrip("/") if batch_id else None,
            "error_code": None,
            "error_message": None,
            "failure_count": 0,
            "next_run_at": datetime.now(UTC) + timedelta(seconds=settings.cutflow_poll_seconds),
        }
    except Exception as exc:
        failures = row.failure_count + 1
        values = {
            "failure_count": failures,
            "status": "FAILED" if failures >= 5 else row.status,
            "error_code": exc.code if isinstance(exc, CutflowHandoffError) else "CUTFLOW_RETRY",
            "error_message": str(exc)
            if isinstance(exc, CutflowHandoffError)
            else "交接暂时失败，系统将重试；请检查网络、NAS 和剪辑端",
            "next_run_at": datetime.now(UTC) + timedelta(seconds=min(300, 15 * 2**failures)),
        }
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat
    async with database.session_factory() as session:
        await session.execute(
            update(CutflowHandoff)
            .where(CutflowHandoff.id == row.id, CutflowHandoff.lease_token == token)
            .values(**values, lease_token=None, lease_until=None)
        )
        await session.commit()
    return True


async def run(once: bool) -> None:
    settings = get_settings()
    require_configuration(settings)
    database = Database(settings.database_url)
    try:
        store = create_object_store(settings)
        while True:
            await tick(database, settings, store)
            if once:
                break
            await asyncio.sleep(1)
    finally:
        await database.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    asyncio.run(run(parser.parse_args().once))
