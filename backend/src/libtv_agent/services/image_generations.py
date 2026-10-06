from __future__ import annotations

import asyncio
import hashlib
import io
import ipaddress
import socket
import urllib.request
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from libtv_agent.domain.contracts import sha256_json
from libtv_agent.domain.models import (
    ImageGenerationBatch,
    ImageGenerationItem,
    ImageGenerationOutput,
)
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

ACTIVE_ITEM_STATUSES = {"CREATED", "PROCESSING"}
TERMINAL_ITEM_STATUSES = {
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "TIMEOUT",
    "WRITE_UNCERTAIN",
    "MANUAL_REVIEW",
}
PROVIDER_MODEL_IDS = {
    ("gpt", "edit"): "openai/gpt-image-2/edit",
    ("gpt", "text-to-image"): "openai/gpt-image-2/text-to-image",
    ("nanobanana", "edit"): "google/nano-banana-2/edit",
    ("nanobanana", "text-to-image"): "google/nano-banana-2/text-to-image",
}


@dataclass(frozen=True)
class ImageItemSpec:
    client_task_id: str
    outfit_id: str
    outfit_name: str
    sku: str
    kind: str
    view: str
    label: str
    prompt: str
    reference_file_indexes: tuple[int, ...]


class ImageBatchConflictError(RuntimeError):
    pass


class ImageBatchSubmissionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        uncertain: bool = False,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.uncertain = uncertain
        self.details = details or {}


def request_fingerprint(manifest: dict[str, Any], file_hashes: Iterable[str]) -> str:
    return sha256_json({"manifest": manifest, "fileHashes": list(file_hashes)})


async def find_idempotent_batch(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    idempotency_key: str,
    request_hash: str,
) -> ImageGenerationBatch | None:
    batch = await session.scalar(
        select(ImageGenerationBatch).where(
            ImageGenerationBatch.user_id == user_id,
            ImageGenerationBatch.idempotency_key == idempotency_key,
        )
    )
    if batch is not None and batch.request_hash != request_hash:
        raise ImageBatchConflictError("idempotency key was reused with a different request")
    return batch


def build_prediction_payload(
    *,
    provider: str,
    prompt: str,
    image_urls: list[str],
    aspect_ratio: str,
    resolution: str,
    quality: str | None,
    output_format: str,
) -> tuple[str, dict[str, Any]]:
    mode = "edit" if image_urls else "text-to-image"
    model_id = PROVIDER_MODEL_IDS[(provider, mode)]
    payload: dict[str, Any] = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "output_format": output_format,
    }
    if image_urls:
        payload["images"] = image_urls
    if provider == "gpt":
        payload["quality"] = quality or "medium"
    else:
        payload["enable_web_search"] = False
        payload["enable_image_search"] = False
    return model_id, payload


def create_batch_record(
    *,
    user_id: uuid.UUID,
    idempotency_key: str,
    request_hash: str,
    manifest: dict[str, Any],
    item_specs: list[ImageItemSpec],
) -> ImageGenerationBatch:
    now = datetime.now(UTC)
    batch = ImageGenerationBatch(
        user_id=user_id,
        client_batch_id=str(manifest["clientBatchId"]),
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        name=str(manifest["name"]),
        provider=str(manifest["provider"]),
        status="CREATED",
        expected_generation_count=int(manifest["expectedGenerationCount"]),
        paid_submission_consent_at=now,
        request_json=manifest,
    )
    for order_no, spec in enumerate(item_specs, start=1):
        batch.items.append(
            ImageGenerationItem(
                order_no=order_no,
                client_task_id=spec.client_task_id,
                outfit_id=spec.outfit_id,
                outfit_name=spec.outfit_name,
                sku=spec.sku,
                kind=spec.kind,
                view=spec.view,
                label=spec.label,
                prompt=spec.prompt,
                model_id="PENDING",
                request_json={"referenceFileIndexes": list(spec.reference_file_indexes)},
                outputs=[],
            )
        )
    return batch


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def _provider_data(value: Any) -> dict[str, Any]:
    result = _mapping(value)
    data = result.get("data")
    return _mapping(data) if data is not None else result


def _provider_error(exc: Exception, *, submission: bool) -> ImageBatchSubmissionError:
    code = str(getattr(exc, "code", "WAVESPEED_REQUEST_FAILED"))[:80]
    retryable = bool(getattr(exc, "retryable", False))
    outcome_uncertain = bool(
        getattr(exc, "uncertain", False) or getattr(exc, "outcome_uncertain", False)
    )
    details = dict(getattr(exc, "details", {}) or {})
    if getattr(exc, "submitted", False):
        details["submitted"] = True
    if getattr(exc, "task_id", None):
        details["taskId"] = str(exc.task_id)
    if getattr(exc, "model_id", None):
        details["modelId"] = str(exc.model_id)
    if submission and (
        outcome_uncertain or isinstance(exc, (TimeoutError, ConnectionError, asyncio.TimeoutError))
    ):
        return ImageBatchSubmissionError(
            "WAVESPEED_SUBMISSION_UNCERTAIN",
            "WaveSpeed submission outcome is unknown; this item will not be "
            "resubmitted automatically",
            retryable=False,
            uncertain=True,
            details=details,
        )
    return ImageBatchSubmissionError(
        code,
        str(exc)[:4000],
        retryable=retryable,
        details=details,
    )


def _upload_url(value: Any) -> str:
    if isinstance(value, str):
        return value
    data = _provider_data(value)
    url = data.get("download_url") or data.get("downloadUrl") or data.get("url")
    if not isinstance(url, str) or not url:
        raise ImageBatchSubmissionError(
            "WAVESPEED_UPLOAD_INVALID_RESPONSE",
            "WaveSpeed media upload did not return a download URL",
            retryable=False,
        )
    return url


def _submission_result(value: Any) -> tuple[str, str, str | None, dict[str, Any]]:
    data = _provider_data(value)
    task_id = data.get("id") or data.get("task_id") or data.get("taskId")
    if not isinstance(task_id, str) or not task_id:
        raise ImageBatchSubmissionError(
            "WAVESPEED_SUBMIT_INVALID_RESPONSE",
            "WaveSpeed submission did not return a prediction ID",
            retryable=False,
        )
    raw_status = str(data.get("status") or "").lower()
    status_map = {"created": "CREATED", "processing": "PROCESSING"}
    status = status_map.get(raw_status)
    if status is None:
        raise ImageBatchSubmissionError(
            "WAVESPEED_SUBMIT_INVALID_RESPONSE",
            f"WaveSpeed submission returned an invalid status: {raw_status or 'missing'}",
            retryable=False,
            uncertain=True,
            details={"taskId": task_id, "providerStatus": raw_status or None},
        )
    urls = _mapping(data.get("urls"))
    result_url = data.get("result_url") or urls.get("get")
    return task_id, status, str(result_url) if result_url else None, data


async def submit_batch(
    session: AsyncSession,
    *,
    batch: ImageGenerationBatch,
    adapter: Any,
    file_paths: list[Path],
) -> None:
    """Submit every prediction once. No call in this function retries a provider POST."""

    for item in batch.items:
        if item.status == "SUBMITTING" and not item.provider_task_id:
            error = {
                "code": "WAVESPEED_SUBMISSION_UNCERTAIN",
                "message": (
                    "A previous WaveSpeed submission was interrupted before its prediction "
                    "ID was persisted; it will not be resubmitted automatically"
                ),
                "retryable": False,
                "details": {"submitted": True},
            }
            await session.execute(
                update(ImageGenerationItem)
                .where(
                    ImageGenerationItem.id == item.id,
                    ImageGenerationItem.status == "SUBMITTING",
                    ImageGenerationItem.provider_task_id.is_(None),
                )
                .values(status="WRITE_UNCERTAIN", error_json=error)
                .execution_options(synchronize_session=False)
            )
            await session.refresh(item)
        elif item.status == "SUBMITTING" and item.provider_task_id:
            await session.execute(
                update(ImageGenerationItem)
                .where(
                    ImageGenerationItem.id == item.id,
                    ImageGenerationItem.status == "SUBMITTING",
                    ImageGenerationItem.provider_task_id.is_not(None),
                )
                .values(status="CREATED")
                .execution_options(synchronize_session=False)
            )
            await session.refresh(item)
    await session.commit()

    pending_items = [item for item in batch.items if item.status == "PENDING"]
    if not pending_items:
        _update_batch_status(batch)
        await session.commit()
        return

    batch.status = "SUBMITTING"
    await session.commit()
    try:
        uploaded_urls = [_upload_url(await adapter.upload_media(path)) for path in file_paths]
    except Exception as exc:
        error = (
            exc
            if isinstance(exc, ImageBatchSubmissionError)
            else _provider_error(exc, submission=False)
        )
        batch.error_json = {
            "code": error.code,
            "message": str(error),
            "retryable": error.retryable,
            "details": error.details,
        }
        batch.status = "FAILED"
        for item in pending_items:
            item.status = "FAILED"
            item.error_json = batch.error_json
        await session.commit()
        return

    request = batch.request_json
    for item in pending_items:
        if item.provider_task_id:
            continue
        claimed = await session.execute(
            update(ImageGenerationItem)
            .where(
                ImageGenerationItem.id == item.id,
                ImageGenerationItem.status == "PENDING",
                ImageGenerationItem.provider_task_id.is_(None),
            )
            .values(status="SUBMITTING")
        )
        await session.commit()
        if claimed.rowcount != 1:
            await session.refresh(item)
            continue
        indexes = item.request_json.get("referenceFileIndexes", [])
        image_urls = [uploaded_urls[int(index)] for index in indexes]
        model_id, payload = build_prediction_payload(
            provider=batch.provider,
            prompt=item.prompt,
            image_urls=image_urls,
            aspect_ratio=str(request["aspectRatio"]),
            resolution=str(request["resolution"]),
            quality=request.get("quality"),
            output_format=str(request["outputFormat"]),
        )
        item.model_id = model_id
        item.request_json = payload
        item.status = "SUBMITTING"
        await session.commit()
        try:
            response = await adapter.submit_prediction(model_id, payload)
            task_id, provider_status, result_url, raw = _submission_result(response)
            item.provider_task_id = task_id
            item.provider_result_url = result_url
            item.raw_response_json = raw
            item.status = provider_status
            item.submitted_at = datetime.now(UTC)
        except Exception as exc:
            error = (
                exc
                if isinstance(exc, ImageBatchSubmissionError)
                else _provider_error(exc, submission=True)
            )
            item.status = "WRITE_UNCERTAIN" if error.uncertain else "FAILED"
            item.error_json = {
                "code": error.code,
                "message": str(error),
                "retryable": error.retryable,
                "details": error.details,
            }
        await session.commit()
    _update_batch_status(batch)
    await session.commit()


def _prediction_result(value: Any) -> tuple[str, list[str], dict[str, Any], dict[str, Any] | None]:
    data = _provider_data(value)
    raw_status = str(data.get("status") or "").lower()
    status_map = {
        "created": "CREATED",
        "queued": "CREATED",
        "processing": "PROCESSING",
        "running": "PROCESSING",
        "completed": "COMPLETED",
        "succeeded": "COMPLETED",
        "success": "COMPLETED",
        "failed": "FAILED",
        "cancelled": "CANCELLED",
        "canceled": "CANCELLED",
        "timeout": "TIMEOUT",
    }
    status = status_map.get(raw_status)
    outputs: list[str] = []
    for output in data.get("outputs") or []:
        if isinstance(output, str):
            outputs.append(output)
        elif isinstance(output, dict) and isinstance(output.get("url"), str):
            outputs.append(output["url"])
    error: dict[str, Any] | None = None
    if status is None:
        status = "FAILED"
        error = {
            "code": "WAVESPEED_RESPONSE_INVALID",
            "message": (
                "WaveSpeed prediction response omitted its status"
                if not raw_status
                else f"WaveSpeed returned unknown prediction status: {raw_status}"
            ),
            "retryable": False,
            "details": {"providerStatus": raw_status},
        }
    elif status == "COMPLETED" and not outputs:
        status = "FAILED"
        error = {
            "code": "WAVESPEED_RESPONSE_INVALID",
            "message": "WaveSpeed completed a prediction without any output image",
            "retryable": False,
            "details": {"providerStatus": raw_status},
        }
    elif status in {"FAILED", "CANCELLED", "TIMEOUT"}:
        provider_error = data.get("error") or data.get("message") or f"prediction {raw_status}"
        error = {
            "code": f"WAVESPEED_PREDICTION_{status}",
            "message": str(provider_error)[:4000],
            "retryable": False,
            "details": {"providerStatus": raw_status},
        }
    return status, outputs, data, error


def _update_batch_status(batch: ImageGenerationBatch) -> None:
    statuses = {item.status for item in batch.items}
    if "WRITE_UNCERTAIN" in statuses:
        batch.status = "WRITE_UNCERTAIN"
    elif statuses and statuses <= {"COMPLETED"}:
        batch.status = "COMPLETED"
    elif statuses & {"CREATED", "PROCESSING", "SUBMITTING", "PENDING"}:
        batch.status = "PROCESSING"
    elif "COMPLETED" in statuses:
        batch.status = "PARTIAL_FAILED"
    else:
        batch.status = "FAILED"


def _validate_public_https_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("WaveSpeed output URL must use public HTTPS")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("WaveSpeed output host could not be resolved") from exc
    if not addresses or any(
        not ipaddress.ip_address(address[4][0]).is_global for address in addresses
    ):
        raise ValueError("WaveSpeed output URL must resolve only to public addresses")


class _PublicHttpsRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        _validate_public_https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download_remote_image(url: str, destination: Path, limit: int) -> tuple[str, int, str]:
    _validate_public_https_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "libtv-agent/1.0"})
    opener = urllib.request.build_opener(_PublicHttpsRedirectHandler())
    with opener.open(request, timeout=60) as response:  # noqa: S310
        content_type = response.headers.get_content_type()
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValueError("WaveSpeed output is not an image")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("WaveSpeed output exceeds the download size limit")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
            image_format = image.format
    except (OSError, ValueError) as exc:
        raise ValueError("WaveSpeed output image cannot be decoded") from exc
    expected_format = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[content_type]
    if image_format != expected_format:
        raise ValueError("WaveSpeed output content type does not match its image data")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return content_type, len(data), hashlib.sha256(data).hexdigest()


async def _materialize_output(app: Any, output: ImageGenerationOutput) -> None:
    destination = app.state.settings.runner_root / "wavespeed" / "outputs" / f"{output.id}.img"
    content_type, size, digest = await asyncio.to_thread(
        _download_remote_image,
        output.remote_url,
        destination,
        100 * 1024 * 1024,
    )
    try:
        extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
        output.object_key = await app.state.object_store.put_file(
            destination,
            (
                f"users/{output.item.batch.user_id}/image-generations/"
                f"{output.item.batch_id}/{output.id}{extension}"
            ),
            content_type,
        )
        output.content_type = content_type
        output.size_bytes = size
        output.sha256 = digest
    finally:
        await asyncio.to_thread(destination.unlink, missing_ok=True)


async def _claim_image_observation(session: AsyncSession, item: ImageGenerationItem) -> bool:
    last_polled_predicate = (
        ImageGenerationItem.last_polled_at.is_(None)
        if item.last_polled_at is None
        else ImageGenerationItem.last_polled_at == item.last_polled_at
    )
    claimed = await session.execute(
        update(ImageGenerationItem)
        .where(
            ImageGenerationItem.id == item.id,
            ImageGenerationItem.status == item.status,
            last_polled_predicate,
        )
        .values(last_polled_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    await session.refresh(item, attribute_names=["outputs"])
    if claimed.rowcount != 1:
        await session.refresh(item)
        await session.commit()
        return False
    return True


async def refresh_batch(session: AsyncSession, *, app: Any, batch: ImageGenerationBatch) -> None:
    for item in batch.items:
        if item.status not in ACTIVE_ITEM_STATUSES or not item.provider_task_id:
            continue
        claimed = False
        try:
            result = await app.state.wavespeed_adapter.get_prediction(item.provider_task_id)
            claimed = await _claim_image_observation(session, item)
            if not claimed:
                continue
            provider_status, urls, raw, error = _prediction_result(result)
            item.status = provider_status
            item.raw_response_json = raw
            item.error_json = error
            item.last_polled_at = datetime.now(UTC)
            if provider_status == "COMPLETED":
                item.completed_at = datetime.now(UTC)
                known = {output.remote_url for output in item.outputs}
                for index, url in enumerate(urls, start=1):
                    if url not in known:
                        item.outputs.append(ImageGenerationOutput(order_no=index, remote_url=url))
                await session.flush()
                for output in item.outputs:
                    if output.object_key is None:
                        try:
                            await _materialize_output(app, output)
                        except Exception as exc:
                            output.content_type = None
                            item.status = "PROCESSING"
                            item.error_json = {
                                "code": "WAVESPEED_OUTPUT_DOWNLOAD_FAILED",
                                "message": str(exc)[:4000],
                                "retryable": True,
                                "details": {"remoteUrlRetained": True},
                            }
        except Exception as exc:
            if not session.is_active:
                await session.rollback()
                raise
            if not claimed and not await _claim_image_observation(session, item):
                continue
            error = _provider_error(exc, submission=False)
            if not error.retryable:
                item.status = "FAILED"
            item.error_json = {
                "code": error.code,
                "message": str(error),
                "retryable": error.retryable,
                "details": error.details,
            }
        await session.commit()
    # Serialize aggregate updates and reload items changed by other API/worker sessions.
    await session.execute(
        update(ImageGenerationBatch)
        .where(ImageGenerationBatch.id == batch.id)
        .values(status=ImageGenerationBatch.status)
        .execution_options(synchronize_session=False)
    )
    await session.refresh(batch, attribute_names=["items"])
    for item in batch.items:
        await session.refresh(item)
    _update_batch_status(batch)
    await session.commit()


async def refresh_active_batches(
    session: AsyncSession,
    *,
    app: Any,
    limit: int = 100,
) -> int:
    """Advance persisted predictions even when no browser is polling them."""

    batches = list(
        (
            await session.scalars(
                select(ImageGenerationBatch)
                .join(ImageGenerationItem)
                .where(
                    ImageGenerationItem.status.in_(ACTIVE_ITEM_STATUSES),
                    ImageGenerationItem.provider_task_id.is_not(None),
                )
                .distinct()
                .order_by(ImageGenerationBatch.created_at)
                .limit(limit)
            )
        ).all()
    )
    for batch in batches:
        await refresh_batch(session, app=app, batch=batch)
    return len(batches)


async def owned_batch(
    session: AsyncSession, *, user_id: uuid.UUID, batch_id: uuid.UUID
) -> ImageGenerationBatch | None:
    return await session.scalar(
        select(ImageGenerationBatch).where(
            ImageGenerationBatch.id == batch_id,
            ImageGenerationBatch.user_id == user_id,
        )
    )


async def owned_output(
    session: AsyncSession, *, user_id: uuid.UUID, output_id: uuid.UUID
) -> ImageGenerationOutput | None:
    return await session.scalar(
        select(ImageGenerationOutput)
        .join(ImageGenerationItem, ImageGenerationItem.id == ImageGenerationOutput.item_id)
        .join(ImageGenerationBatch, ImageGenerationBatch.id == ImageGenerationItem.batch_id)
        .where(ImageGenerationOutput.id == output_id, ImageGenerationBatch.user_id == user_id)
    )
