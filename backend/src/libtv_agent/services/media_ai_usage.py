"""USD media guards; identities live in the shared ledger, not video points."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from libtv_agent.adapters.libtv import FakeLibTVAdapter, ReplayLibTVAdapter
from libtv_agent.config import Settings
from libtv_agent.domain.contracts import sha256_json
from libtv_agent.domain.enums import AIUsageReservationStatus
from libtv_agent.domain.models import (
    AIUsageReservation,
    GenerationAttempt,
    GenerationVariant,
    ImageGenerationBatch,
    ParentTask,
)
from libtv_agent.services.ai_pricing import (
    ACCOUNTING_VERSION,
    AIPricingError,
    PriceQuote,
    actual_cost_from_snapshot,
    estimate_price,
)
from libtv_agent.services.ai_usage import (
    AIUsageLimitExceededError,
    AIUsageRequestConflictError,
    get_ai_usage_reservation,
    reserve_ai_usage_batch,
    settle_ai_usage,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

IMAGE_OPERATION = "AI_IMAGE_SUBMIT"
VIDEO_OPERATION = "AI_VIDEO_SUBMIT"
OFFLINE_PROVIDERS = frozenset({"offline:fake", "offline:replay"})


class MediaAIUsageBlockedError(RuntimeError):
    def __init__(self, code: str, message: str, *, uncertain: bool = False):
        self.code = code
        self.uncertain = uncertain
        super().__init__(message)


@dataclass(frozen=True)
class MediaUsageRequest:
    user_id: uuid.UUID
    operation: str
    key: str
    provider: str
    model: str
    kind: Literal["image", "video"]
    quantity: int
    request_hash: str
    offline: bool = False


def media_quote(settings: Settings, request: MediaUsageRequest) -> PriceQuote:
    if request.offline != (request.provider in OFFLINE_PROVIDERS) or (
        request.provider.startswith("offline:") and not request.offline
    ):
        raise AIPricingError("offline media requires a verified synthetic execution backend")
    quote = estimate_price(
        settings.model_copy(update={
            "ai_unknown_price_cap_units": request.quantity,
            "ai_unknown_price_policy": "cap",
            "ai_price_catalog_json": '{"version":"offline-capacity-v1","prices":[]}',
        }) if request.offline else settings,
        provider=request.provider, model=request.model, kind=request.kind,
        image_count=request.quantity if request.kind == "image" else 0,
        video_seconds=request.quantity if request.kind == "video" else 0,
    )
    if request.offline:
        return PriceQuote(
            quote.provider, quote.model, quote.kind, 0, quote.risk_units,
            {
                **quote.snapshot, "price_status": "OFFLINE", "prices": {},
                "synthetic_capacity_only": True,
                "synthetic_capacity_units": quote.risk_units,
            },
        )
    if quote.snapshot.get("price_status") != "CONFIGURED_PRICE":
        raise AIPricingError("media requires an effective non-reference exact model price")
    return quote


async def find_media_usage(
    session: AsyncSession, *, user_id: uuid.UUID, operation: str, key: str,
) -> AIUsageReservation | None:
    return await get_ai_usage_reservation(
        session, user_id=user_id, operation_type=operation, idempotency_key=key,
    )


async def reserve_media_batch(
    session: AsyncSession, settings: Settings, requests: list[MediaUsageRequest],
) -> list[AIUsageReservation]:
    """Only call at explicit creation; never backfill during reads or recovery."""
    prepared = []
    for request in requests:
        existing = await find_media_usage(
            session, user_id=request.user_id, operation=request.operation, key=request.key,
        )
        if existing is not None:
            if existing.request_hash != request.request_hash:
                raise AIUsageRequestConflictError("media request changed under its budget key")
            quote = PriceQuote(
                existing.provider, existing.model, request.kind,
                existing.estimated_cost_microusd, existing.risk_units,
                existing.pricing_snapshot_json,
            )
        else:
            quote = media_quote(settings, request)
        prepared.append({
            "quote": quote, "user_id": request.user_id, "task_id": None,
            "operation_type": request.operation, "idempotency_key": request.key,
            "request_hash": request.request_hash, "input_chars": 0,
            "input_image_count": 0, "max_output_tokens": 0,
        })
    results = await reserve_ai_usage_batch(session, settings, requests=prepared)
    return [result.reservation for result in results]


async def claim_media_submission(
    session: AsyncSession, request: MediaUsageRequest,
) -> AIUsageReservation:
    reservation = await find_media_usage(
        session, user_id=request.user_id, operation=request.operation, key=request.key,
    )
    if reservation is None:
        raise MediaAIUsageBlockedError(
            "MEDIA_PRICE_RESERVATION_MISSING",
            "historical media without a price reservation is query-only",
        )
    if reservation.status != AIUsageReservationStatus.RESERVED or (
        reservation.actual_cost_status != "PENDING"
    ):
        raise MediaAIUsageBlockedError(
            "MEDIA_SUBMISSION_ALREADY_CLAIMED",
            "media submission already started; query or reconcile instead of submitting again",
            uncertain=reservation.status not in {
                AIUsageReservationStatus.SETTLED, AIUsageReservationStatus.RELEASED,
            },
        )
    if (
        reservation.request_hash != request.request_hash
        or reservation.provider != request.provider or reservation.model != request.model
    ):
        raise MediaAIUsageBlockedError(
            "MEDIA_BUDGET_REQUEST_CHANGED", "media request no longer matches its reserved price",
        )
    snapshot = reservation.pricing_snapshot_json or {}
    if snapshot.get("price_status") != (
        "OFFLINE" if request.offline else "CONFIGURED_PRICE"
    ):
        raise MediaAIUsageBlockedError(
            "MEDIA_PRICE_RESERVATION_INVALID", "media reservation has no exact price snapshot",
        )
    claimed = await session.execute(
        update(AIUsageReservation).where(
            AIUsageReservation.id == reservation.id,
            AIUsageReservation.accounting_version == ACCOUNTING_VERSION,
            AIUsageReservation.status == AIUsageReservationStatus.RESERVED,
            AIUsageReservation.actual_cost_status == "PENDING",
        ).values(actual_cost_status="SUBMISSION_STARTED")
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        await session.refresh(reservation)
        raise MediaAIUsageBlockedError(
            "MEDIA_SUBMISSION_ALREADY_CLAIMED",
            "media submission already started; query or reconcile instead of submitting again",
            uncertain=reservation.status not in {
                AIUsageReservationStatus.SETTLED, AIUsageReservationStatus.RELEASED,
            },
        )
    await session.refresh(reservation)
    # The durable budget claim is the last fence before any paid POST/process.
    await session.commit()
    return reservation


def billing_quantity(raw: Any, kind: Literal["image", "video"]) -> int | None:
    """Accept usage receipts only, never requested duration or output URLs."""
    if not isinstance(raw, dict):
        return None
    for nested in ("raw_response", "data"):
        if isinstance(raw.get(nested), dict):
            result = billing_quantity(raw[nested], kind)
            if result is not None:
                return result
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        return None
    keys = ("image_count", "output_images") if kind == "image" else (
        "video_seconds", "billed_seconds",
    )
    for key in keys:
        value = usage.get(key)
        if type(value) is int and value >= 0:
            return value
    return None


async def finish_media_usage(
    session: AsyncSession, reservation: AIUsageReservation | None, *,
    quantity: int | None = None, provider_response_id: str | None = None,
    not_submitted: bool = False,
    unclaimed_only: bool = False,
    inflight: bool = False,
) -> None:
    if reservation is None:
        return
    if not_submitted:
        if unclaimed_only:
            released = await session.execute(
                update(AIUsageReservation).where(
                    AIUsageReservation.id == reservation.id,
                    AIUsageReservation.status == AIUsageReservationStatus.RESERVED,
                    AIUsageReservation.actual_cost_status == "PENDING",
                ).values(actual_cost_status="NOT_SUBMITTED")
                .execution_options(synchronize_session=False)
            )
            if released.rowcount != 1:
                return
            await session.refresh(reservation)
        await settle_ai_usage(
            session, reservation.id, status=AIUsageReservationStatus.RELEASED,
            actual_cost_status="NOT_SUBMITTED",
        )
        return
    snapshot = reservation.pricing_snapshot_json or {}
    offline = (
        reservation.provider in OFFLINE_PROVIDERS
        and snapshot.get("price_status") == "OFFLINE"
        and snapshot.get("synthetic_capacity_only") is True
    )
    kind = snapshot.get("kind")
    try:
        cost = 0 if offline else actual_cost_from_snapshot(
            snapshot, input_tokens=None, output_tokens=None,
            image_count=quantity if kind == "image" else None,
            video_seconds=quantity if kind == "video" else None,
        )
    except (KeyError, TypeError, ValueError):
        cost = None
    if inflight and cost is None:
        if provider_response_id:
            await session.execute(update(AIUsageReservation).where(
                AIUsageReservation.id == reservation.id,
            ).values(provider_response_id=provider_response_id)
            .execution_options(synchronize_session=False))
        return
    await settle_ai_usage(
        session, reservation.id,
        status=AIUsageReservationStatus.SETTLED if cost is not None
        else AIUsageReservationStatus.UNKNOWN,
        actual_cost_microusd=cost, provider_response_id=provider_response_id,
        actual_cost_status="OFFLINE" if offline else
        "LOCAL_PRICE_USAGE" if cost is not None else "UNKNOWN_COST",
    )


def image_usage_request(batch: ImageGenerationBatch, item: Any) -> MediaUsageRequest:
    # One expanded item is exactly one prediction/image, not manifest.resultCount.
    mode = "edit" if item.request_json.get("referenceFileIndexes") else "text-to-image"
    from libtv_agent.services.image_generations import PROVIDER_MODEL_IDS

    model = item.model_id if item.model_id != "PENDING" else PROVIDER_MODEL_IDS[
        (batch.provider, mode)
    ]
    return MediaUsageRequest(
        batch.user_id, IMAGE_OPERATION, f"image:{batch.id}:{item.id}",
        "wavespeed", model, "image", 1,
        sha256_json({
            "batch": batch.request_hash, "item": str(item.id),
            "prompt": item.prompt, "model": model, "imageCount": 1,
        }),
    )


async def reserve_image_batch(
    session: AsyncSession, settings: Settings, batch: ImageGenerationBatch,
) -> None:
    if len(batch.items) != batch.expected_generation_count:
        raise AIPricingError("image batch count does not match expanded predictions")
    await reserve_media_batch(
        session, settings, [image_usage_request(batch, item) for item in batch.items],
    )


def video_usage_request(
    settings: Settings, task: ParentTask, variant: GenerationVariant, attempt: GenerationAttempt,
    *, adapter: Any = None,
) -> MediaUsageRequest:
    offline = attempt.provider == "libtv" and settings.libtv_adapter_mode in {"fake", "replay"}
    if offline and not (
        isinstance(adapter, ReplayLibTVAdapter) if settings.libtv_adapter_mode == "replay"
        else isinstance(adapter, FakeLibTVAdapter) and not isinstance(adapter, ReplayLibTVAdapter)
    ):
        raise AIPricingError("offline LibTV accounting requires the actual fake/replay adapter")
    if attempt.provider.startswith("offline:"):
        raise AIPricingError("a persisted provider name cannot authorize offline video")
    provider = f"offline:{settings.libtv_adapter_mode}" if offline else attempt.provider
    config = variant.generation_config_json or {}
    model = attempt.provider_model or (
        config.get("modelKey") if attempt.provider == "libtv" else settings.active_kling_model
    )
    if not model and offline:
        model = settings.libtv_adapter_mode
    duration = config.get("duration", config.get("durationSeconds"))
    if duration is None and attempt.provider != "libtv":
        duration = settings.active_kling_duration
    if duration is None and offline:
        duration = 10
    if not isinstance(model, str) or not model or type(duration) is not int or duration < 1:
        raise AIPricingError("video requires an exact model and integer output duration")
    if config.get("quantity", config.get("count", 1)) != 1:
        raise AIPricingError("video budget requires one output per attempt")
    return MediaUsageRequest(
        task.user_id, VIDEO_OPERATION, f"video:{attempt.id}", provider, model, "video", duration,
        sha256_json({
            "task": str(task.id), "attempt": str(attempt.id), "intent": attempt.intent_hash,
            "prompt": variant.prompt_text, "config": config, "provider": provider,
            "model": model, "videoSeconds": duration,
        }), offline=offline,
    )


async def reserve_video_attempts(
    session: AsyncSession, settings: Settings, task: ParentTask,
    attempts: list[GenerationAttempt],
    *, adapter: Any = None,
) -> None:
    requests = []
    for attempt in attempts:
        variant = await session.get(GenerationVariant, attempt.variant_id)
        if variant is None:
            raise AIPricingError("video variant missing before budget reservation")
        requests.append(video_usage_request(settings, task, variant, attempt, adapter=adapter))
    await reserve_media_batch(session, settings, requests)


async def finish_video_usage(
    session: AsyncSession, attempt: GenerationAttempt, *, raw: Any = None,
    not_submitted: bool = False,
    unclaimed_only: bool = False,
    inflight: bool = False,
) -> None:
    # Lookup by operation/key also works when a historical parent/variant is absent.
    reservation = await session.scalar(select(AIUsageReservation).where(
        AIUsageReservation.operation_type == VIDEO_OPERATION,
        AIUsageReservation.idempotency_key == f"video:{attempt.id}",
        AIUsageReservation.accounting_version == ACCOUNTING_VERSION,
    ))
    await finish_media_usage(
        session, reservation, quantity=billing_quantity(raw, "video"),
        provider_response_id=attempt.task_id, not_submitted=not_submitted,
        unclaimed_only=unclaimed_only,
        inflight=inflight,
    )


MEDIA_BUDGET_ERRORS = (
    AIPricingError, AIUsageLimitExceededError, AIUsageRequestConflictError,
    MediaAIUsageBlockedError,
)
