"""Local, versioned prices. All arithmetic is integer USD microdollars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from libtv_agent.config import Settings
from pydantic import BaseModel, ConfigDict, Field, model_validator

ACCOUNTING_VERSION = "USD_MILLIDOLLAR_V1"
LEGACY_VERSION = "LEGACY_RISK_V0"
MICROUSD_PER_UNIT = 1000
PriceUnit = Literal["input_token", "output_token", "image", "video_second"]


class AIPricingError(ValueError):
    pass


def ceil_div(value: int, denominator: int) -> int:
    return (value + denominator - 1) // denominator


def microusd_to_units(value: int) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("cost must be a nonnegative integer in microUSD")
    return ceil_div(value, MICROUSD_PER_UNIT)


def units_to_usd(value: int) -> str:
    if type(value) is not int:
        raise ValueError("units must be integers")
    sign = "-" if value < 0 else ""
    whole, fraction = divmod(abs(value), 1000)
    return f"{sign}{whole}.{fraction:03d}"


class PriceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=160)
    unit: PriceUnit
    rate_microusd: int = Field(strict=True, ge=0)
    quantity: int = Field(strict=True, ge=1)
    effective_at: datetime
    expires_at: datetime | None = None
    source: str = Field(min_length=1)
    version: str = Field(min_length=1)
    reference_only: bool = True

    @model_validator(mode="after")
    def validate_dates(self) -> PriceEntry:
        if self.effective_at.tzinfo is None or (
            self.expires_at is not None and self.expires_at.tzinfo is None
        ):
            raise ValueError("price effective dates require a timezone")
        if self.expires_at is not None and self.expires_at <= self.effective_at:
            raise ValueError("price expiry must follow its effective date")
        return self


class PriceCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1)
    prices: list[PriceEntry]

    @model_validator(mode="after")
    def validate_versions(self) -> PriceCatalog:
        identities = [
            (price.provider, price.model, price.unit, price.effective_at)
            for price in self.prices
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("ambiguous prices for the same model/unit/effective date")
        return self


def load_price_catalog(settings: Settings) -> PriceCatalog:
    try:
        return PriceCatalog.model_validate_json(settings.ai_price_catalog_json)
    except ValueError as exc:
        raise AIPricingError("invalid local AI price catalog") from exc


@dataclass(frozen=True)
class PriceQuote:
    provider: str
    model: str
    kind: Literal["text", "image", "video"]
    estimated_cost_microusd: int
    risk_units: int
    snapshot: dict


def estimate_price(
    settings: Settings,
    *,
    provider: str,
    model: str,
    kind: Literal["text", "image", "video"] = "text",
    input_tokens: int = 0,
    max_output_tokens: int = 0,
    image_count: int = 0,
    video_seconds: int = 0,
    retry_attempts: int = 0,
    fallback_reserve_microusd: int = 0,
    now: datetime | None = None,
) -> PriceQuote:
    counts = (input_tokens, max_output_tokens, image_count, video_seconds,
              retry_attempts, fallback_reserve_microusd)
    if any(type(value) is not int or value < 0 for value in counts):
        raise AIPricingError("usage dimensions must be nonnegative integers")
    if kind not in {"text", "image", "video"}:
        raise AIPricingError("unsupported AI price kind")
    if kind == "image" and image_count < 1 or kind == "video" and video_seconds < 1:
        raise AIPricingError("media estimates require output count or duration")
    quantities = (
        {"input_token": input_tokens, "output_token": max_output_tokens}
        if kind == "text"
        else {"image": image_count} if kind == "image" else {"video_second": video_seconds}
    )
    catalog = load_price_catalog(settings)
    when = now or datetime.now(UTC)
    selected: dict[str, dict] = {}
    total = 0
    for unit, count in quantities.items():
        candidates = [
            price for price in catalog.prices
            if price.provider == provider and price.model == model and price.unit == unit
            and not price.reference_only and price.effective_at <= when
            and (price.expires_at is None or when < price.expires_at)
        ]
        if not candidates:
            break
        price = max(candidates, key=lambda item: item.effective_at)
        selected[unit] = price.model_dump(mode="json")
        total += ceil_div(count * price.rate_microusd, price.quantity)
    priced = len(selected) == len(quantities)
    if not priced:
        if settings.ai_unknown_price_policy == "reject" and not provider.startswith("offline:"):
            raise AIPricingError(f"no effective local price for {provider}/{model}/{kind}")
        total = settings.ai_unknown_price_cap_units * MICROUSD_PER_UNIT
        selected = {}
    # Offline traffic still reserves capacity before dispatch but settles to zero.
    total = total * (1 + retry_attempts) + fallback_reserve_microusd
    units = max(1, microusd_to_units(total))
    if units > settings.ai_request_max_units:
        raise AIPricingError("AI request exceeds the configured USD request cap")
    return PriceQuote(
        provider, model, kind, total, units,
        {
            "accounting_version": ACCOUNTING_VERSION,
            "catalog_version": catalog.version,
            "price_status": "CONFIGURED_PRICE" if priced else "CONSERVATIVE_CAP",
            "kind": kind,
            "provider": provider,
            "model": model,
            "estimated_at": when.isoformat(),
            "quantities": quantities,
            "prices": selected,
            "retry_attempts": retry_attempts,
            "fallback_reserve_microusd": fallback_reserve_microusd,
        },
    )


def estimate_text_price(
    settings: Settings, *, provider: str, model: str, input_chars: int,
    input_image_count: int, max_output_tokens: int,
) -> PriceQuote:
    if input_chars < 0 or input_image_count < 0:
        raise AIPricingError("input sizes cannot be negative")
    return estimate_price(
        settings, provider=provider, model=model,
        input_tokens=(
            input_chars * 4 + input_image_count * settings.ai_input_image_token_reserve
            + settings.ai_input_schema_token_reserve
        ),
        max_output_tokens=max_output_tokens,
    )


def actual_cost_from_snapshot(
    snapshot: dict, *, input_tokens: int | None, output_tokens: int | None,
    image_count: int | None = None, video_seconds: int | None = None,
) -> int | None:
    if snapshot.get("price_status") != "CONFIGURED_PRICE":
        return None
    kind = snapshot.get("kind")
    quantities = (
        {"input_token": input_tokens, "output_token": output_tokens}
        if kind == "text"
        else {"image": image_count} if kind == "image" else {"video_second": video_seconds}
    )
    if any(type(value) is not int or value < 0 for value in quantities.values()):
        return None
    prices = snapshot.get("prices", {})
    if any(unit not in prices for unit in quantities):
        return None
    # Aggregate input includes cache/image tokens; using the regular rate is
    # conservative. This is a local price calculation, not a provider invoice.
    return sum(
        ceil_div(count * prices[unit]["rate_microusd"], prices[unit]["quantity"])
        for unit, count in quantities.items()
    )
