from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from libtv_agent.domain.enums import AttemptStatus, GenerationStatus
from libtv_agent.domain.models import GenerationAttempt, GenerationVariant
from libtv_agent.services.provider_errors import clear_provider_error, record_provider_error
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_TERMINAL_ATTEMPT_STATUSES = {
    AttemptStatus.SUCCEEDED,
    AttemptStatus.FAILED_BEFORE_SUBMIT,
    AttemptStatus.FAILED_TERMINAL,
    AttemptStatus.NEEDS_MANUAL_REVIEW,
    AttemptStatus.CANCELLED_BEFORE_SUBMIT,
}
_CALLBACK_STATUS_MAP = {
    "submitted": "queued",
    "processing": "running",
    "succeeded": "succeeded",
    "failed": "failed",
}


class KlingCallbackError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class KlingCallbackObservation:
    provider_task_id: str
    status: str
    message: str | None
    outputs: tuple[dict[str, Any], ...]
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class KlingCallbackResult:
    provider_task_id: str
    status: str
    duplicate: bool
    workflow_finalized: bool = False


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _output_urls(outputs: tuple[dict[str, Any], ...]) -> set[str]:
    return {
        str(item["url"])
        for item in outputs
        if item.get("type") == "video" and isinstance(item.get("url"), str)
    }


async def process_kling_callback(
    session: AsyncSession,
    *,
    adapter: Any,
    provider_name: str,
    observation: KlingCallbackObservation,
) -> KlingCallbackResult:
    """Verify a callback through a read-only provider query, then persist it.

    The callback never directly settles billing, finalizes a command, or starts a
    download. The existing Runner remains the sole owner of those transitions.
    """

    callback_status = _CALLBACK_STATUS_MAP.get(observation.status)
    if callback_status is None:
        raise KlingCallbackError(
            "KLING_CALLBACK_STATUS_INVALID",
            "Kling callback contains an unsupported status",
            status_code=422,
        )
    attempt = await session.scalar(
        select(GenerationAttempt)
        .where(
            GenerationAttempt.provider == provider_name,
            GenerationAttempt.task_id == observation.provider_task_id,
        )
        .with_for_update()
    )
    if attempt is None:
        raise KlingCallbackError(
            "KLING_CALLBACK_TASK_NOT_FOUND",
            "Kling callback task is not associated with this deployment",
            status_code=404,
        )

    try:
        verified = await adapter.query(observation.provider_task_id)
    except Exception as exc:
        raise KlingCallbackError(
            "KLING_CALLBACK_VERIFICATION_FAILED",
            "Kling callback could not be verified with the official task query",
            status_code=503,
        ) from exc
    if verified.status != callback_status:
        raise KlingCallbackError(
            "KLING_CALLBACK_STATUS_CONFLICT",
            "Kling callback status does not match the official task query",
            status_code=409,
        )
    callback_urls = _output_urls(observation.outputs)
    verified_urls = {output.url for output in verified.outputs if output.url}
    if callback_urls and callback_urls != verified_urls:
        raise KlingCallbackError(
            "KLING_CALLBACK_OUTPUT_CONFLICT",
            "Kling callback outputs do not match the official task query",
            status_code=409,
        )

    fingerprint = _fingerprint(observation.raw_payload)
    existing = attempt.raw_response_json or {}
    duplicate = existing.get("_callbackFingerprint") == fingerprint
    if duplicate:
        return KlingCallbackResult(
            provider_task_id=observation.provider_task_id,
            status=verified.status,
            duplicate=True,
        )

    if attempt.status in _TERMINAL_ATTEMPT_STATUSES:
        raise KlingCallbackError(
            "KLING_CALLBACK_ATTEMPT_TERMINAL",
            "Kling callback cannot change a terminal generation attempt",
            status_code=409,
        )

    now = datetime.now(UTC)
    attempt.provider_status = verified.status
    attempt.provider_raw_status = verified.raw_status
    attempt.last_polled_at = now
    attempt.raw_response_json = {
        **verified.raw_response,
        "_callbackFingerprint": fingerprint,
        "_callbackReceivedAt": now.isoformat(),
    }
    if verified.credits_consumed is not None:
        attempt.credits_consumed = verified.credits_consumed
    if verified.outputs:
        attempt.output_url = verified.outputs[0].url
    if verified.status == "failed":
        record_provider_error(
            attempt,
            code="KLING_REMOTE_TASK_FAILED",
            message=observation.message or "Kling remote generation failed",
            details={
                "providerTaskId": observation.provider_task_id,
                "providerStatus": observation.status,
                "source": "verified_callback",
            },
            retryable=False,
        )
    elif verified.status == "succeeded":
        clear_provider_error(attempt)

    variant = await session.get(GenerationVariant, attempt.variant_id)
    if variant is not None:
        variant.generation_status = {
            "queued": GenerationStatus.RUNNING,
            "running": GenerationStatus.RUNNING,
            "succeeded": GenerationStatus.SUCCEEDED,
            "failed": GenerationStatus.FAILED,
        }[verified.status]
    attempt.state_version += 1
    await session.commit()
    return KlingCallbackResult(
        provider_task_id=observation.provider_task_id,
        status=verified.status,
        duplicate=False,
    )
