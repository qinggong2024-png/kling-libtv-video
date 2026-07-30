from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from libtv_agent.domain.models import SubjectElementJob
from libtv_agent.services.kling_elements import create_element
from libtv_agent.services.tasks import get_task
from sqlalchemy import select

logger = logging.getLogger(__name__)

SUBJECT_ELEMENT_MAX_ATTEMPTS = 5
SUBJECT_ELEMENT_RETRY_BASE_SECONDS = 2
_SUCCEEDED_STATUSES = {"active", "ready", "succeed", "success", "succeeded", "completed"}


def automatic_element_metadata(
    filename: str,
    *,
    task_id: uuid.UUID,
    reference_count: int,
) -> tuple[str, str]:
    """Build deterministic Kling-required metadata without an approval step."""

    stem = " ".join(Path(filename).stem.split()).strip() or "subject"
    name = f"{stem[:13]}-{task_id.hex[:6]}"
    description = (
        f"Garment subject automatically created from {reference_count} ordered references; "
        "the first image is frontal and the second is the back reference."
    )
    return name[:20], description[:100]


async def _element_image_reference(
    app: Any,
    object_key: str,
    task_id: uuid.UUID,
    index: int,
) -> str:
    # The local MinIO endpoint normally signs localhost/private URLs that Kling
    # cannot fetch. Base64 is accepted by the official Element API and keeps
    # local development plus private deployments reachable without a public
    # object-store hostname.
    local_path = await app.state.object_store.localize(
        object_key,
        app.state.settings.runner_root
        / "kling"
        / "element-inputs"
        / str(task_id)
        / f"subject-{index}.jpg",
    )
    return await asyncio.to_thread(
        lambda: base64.b64encode(local_path.read_bytes()).decode("ascii")
    )


def _retry_delay(attempt_count: int) -> int:
    return min(60, SUBJECT_ELEMENT_RETRY_BASE_SECONDS * (2 ** max(0, attempt_count - 1)))


async def _record_subject_element_failure(
    app: Any,
    *,
    job_id: uuid.UUID,
    cause: Exception,
) -> bool:
    async with app.state.database.session_factory() as session:
        job = await session.get(SubjectElementJob, job_id)
        if job is None:
            return False
        job.status = "FAILED"
        job.last_error_code = str(
            getattr(cause, "code", "KLING_SUBJECT_ELEMENT_CREATE_FAILED")
        )[:80]
        job.last_error_message = str(cause)[:2000]
        retryable = job.attempt_count < SUBJECT_ELEMENT_MAX_ATTEMPTS
        job.next_attempt_at = (
            datetime.now(UTC) + timedelta(seconds=_retry_delay(job.attempt_count))
            if retryable
            else None
        )
        await session.commit()
        return retryable


async def _run_subject_element_attempt(
    app: Any,
    *,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[uuid.UUID | None, bool]:
    async with app.state.database.session_factory() as session:
        job = await session.scalar(
            select(SubjectElementJob)
            .where(
                SubjectElementJob.parent_task_id == task_id,
                SubjectElementJob.user_id == user_id,
            )
            .with_for_update()
        )
        if job is None or job.status in {"SUBMITTED", "SUCCEEDED"}:
            return None, False
        if job.attempt_count >= SUBJECT_ELEMENT_MAX_ATTEMPTS:
            return job.id, False
        job.status = "PROCESSING"
        job.attempt_count += 1
        job.next_attempt_at = None
        job.last_error_code = None
        job.last_error_message = None
        job_id = job.id
        await session.commit()

    try:
        async with app.state.database.session_factory() as session:
            task = await get_task(session, user_id, task_id)
            subject_assets = sorted(
                (
                    asset
                    for asset in task.assets
                    if asset.source_type == "SUBJECT_REFERENCE"
                    and asset.role == "PRODUCT"
                ),
                key=lambda asset: asset.order_no,
            )
            if not 1 <= len(subject_assets) <= 4:
                raise ValueError("subject element requires 1..4 ordered reference images")
            if any(not asset.object_key for asset in subject_assets):
                raise ValueError("subject element source object is missing")
            object_keys = [str(asset.object_key) for asset in subject_assets]
            job = await session.get(SubjectElementJob, job_id)
            if job is None:
                return None, False
            name = job.name
            description = job.description
            external_task_id = job.external_task_id

        references = await asyncio.gather(
            *(
                _element_image_reference(app, object_key, task_id, index)
                for index, object_key in enumerate(object_keys, start=1)
            )
        )
        result = await create_element(
            app.state.kling_adapter,
            {
                "name": name,
                "description": description,
                "imageReferences": references,
                "externalId": external_task_id,
            },
        )
        provider_status = str(result.get("status") or "submitted").strip().lower()
        async with app.state.database.session_factory() as session:
            job = await session.get(SubjectElementJob, job_id)
            if job is None:
                return None, False
            job.provider_task_id = str(result["id"])
            if provider_status in _SUCCEEDED_STATUSES:
                job.element_id = str(result["id"])
                job.status = "SUCCEEDED"
            else:
                job.status = "SUBMITTED"
            job.next_attempt_at = None
            job.last_error_code = None
            job.last_error_message = None
            await session.commit()
        logger.info(
            "automatic subject element creation submitted",
            extra={
                "task_id": str(task_id),
                "provider_task_id": str(result["id"]),
                "provider_status": provider_status,
            },
        )
        return job_id, False
    except asyncio.CancelledError:
        async with app.state.database.session_factory() as session:
            job = await session.get(SubjectElementJob, job_id)
            if job is not None and job.status == "PROCESSING":
                job.status = "PENDING"
                job.next_attempt_at = datetime.now(UTC)
                await session.commit()
        raise
    except Exception as exc:
        retryable = await _record_subject_element_failure(app, job_id=job_id, cause=exc)
        logger.exception(
            "automatic subject element creation failed",
            extra={"task_id": str(task_id), "retryable": retryable},
        )
        return job_id, retryable


async def create_subject_element_for_task(
    app: Any,
    *,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Run a durable, bounded-retry Element creation job."""

    while True:
        async with app.state.database.session_factory() as session:
            job = await session.scalar(
                select(SubjectElementJob).where(
                    SubjectElementJob.parent_task_id == task_id,
                    SubjectElementJob.user_id == user_id,
                )
            )
            next_attempt_at = job.next_attempt_at if job is not None else None
        if next_attempt_at is not None:
            if next_attempt_at.tzinfo is None:
                next_attempt_at = next_attempt_at.replace(tzinfo=UTC)
            delay = max(0.0, (next_attempt_at - datetime.now(UTC)).total_seconds())
            await asyncio.sleep(delay)
        job_id, retryable = await _run_subject_element_attempt(
            app,
            task_id=task_id,
            user_id=user_id,
        )
        if job_id is None or not retryable:
            return
        async with app.state.database.session_factory() as session:
            job = await session.get(SubjectElementJob, job_id)
            next_attempt_at = job.next_attempt_at if job is not None else None
        if next_attempt_at is None:
            return
        if next_attempt_at.tzinfo is None:
            next_attempt_at = next_attempt_at.replace(tzinfo=UTC)
        delay = max(0.0, (next_attempt_at - datetime.now(UTC)).total_seconds())
        await asyncio.sleep(delay)


def schedule_subject_element_job(
    app: Any,
    *,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Schedule one in-process worker while the durable row prevents loss."""

    key = str(task_id)
    if key in app.state.subject_element_job_keys:
        return False
    app.state.subject_element_job_keys.add(key)
    task = asyncio.create_task(
        create_subject_element_for_task(app, task_id=task_id, user_id=user_id)
    )
    app.state.subject_element_jobs.add(task)

    def finished(completed: asyncio.Task[None]) -> None:
        app.state.subject_element_jobs.discard(completed)
        app.state.subject_element_job_keys.discard(key)

    task.add_done_callback(finished)
    return True


async def recover_subject_element_jobs(app: Any) -> int:
    """Resume jobs persisted before a process stop or transient provider failure."""

    async with app.state.database.session_factory() as session:
        jobs = list(
            await session.scalars(
                select(SubjectElementJob).where(
                    SubjectElementJob.status.in_(("PENDING", "PROCESSING", "FAILED")),
                    SubjectElementJob.attempt_count < SUBJECT_ELEMENT_MAX_ATTEMPTS,
                )
            )
        )
        for job in jobs:
            if job.status == "PROCESSING":
                job.status = "PENDING"
        await session.commit()
    return sum(
        schedule_subject_element_job(
            app,
            task_id=job.parent_task_id,
            user_id=job.user_id,
        )
        for job in jobs
    )
