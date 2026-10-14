"""Synthetic catalogs only; no provider, credentials or external prices."""

import json
from datetime import UTC, datetime

import pytest
from libtv_agent.config import Settings
from libtv_agent.services.ai_pricing import (
    AIPricingError,
    actual_cost_from_snapshot,
    estimate_price,
    estimate_text_price,
    load_price_catalog,
)


def entry(unit, **changes):
    return {
        "provider": "paid-adapter", "model": "exact-model", "unit": unit,
        "rate_microusd": 1000, "quantity": 1,
        "effective_at": "2026-01-01T00:00:00Z",
        "source": "synthetic verified upper bound; not a provider quote",
        "version": "synthetic-v1", "reference_only": False,
        "all_parameters_upper_bound": True, **changes,
    }


def settings_for(*prices, **changes):
    return Settings(
        _env_file=None, app_env="test", ai_unknown_price_policy="cap",
        ai_price_catalog_json=json.dumps({"version": "safety-test", "prices": prices}),
        **changes,
    )


def quote(settings, kind, **changes):
    return estimate_price(
        settings, provider="paid-adapter", model="exact-model", kind=kind,
        **({"image_count": 1} if kind == "image" else
           {"video_seconds": 10} if kind == "video" else
           {"input_tokens": 10, "max_output_tokens": 5}),
        **changes,
    )


@pytest.mark.parametrize("kind", ["text", "image", "video"])
def test_real_unknown_price_rejects_even_with_cap_policy(kind):
    with pytest.raises(AIPricingError, match="no effective local price"):
        quote(settings_for(), kind)


@pytest.mark.parametrize("kind,unit", [
    ("image", "image"), ("video", "video_second"),
])
@pytest.mark.parametrize("marker", ["missing", False])
def test_parameter_specific_price_cannot_authorize_any_media(kind, unit, marker):
    low_tier = entry(unit, source="synthetic low resolution / silent / standard tier only")
    if marker == "missing":
        low_tier.pop("all_parameters_upper_bound")
    else:
        low_tier["all_parameters_upper_bound"] = marker
    with pytest.raises(AIPricingError, match="all_parameters_upper_bound"):
        quote(settings_for(low_tier), kind)


@pytest.mark.parametrize("unit,kind", [("image", "image"), ("video_second", "video")])
def test_reference_price_never_authorizes_even_with_upper_bound_flag(unit, kind):
    with pytest.raises(AIPricingError, match="no effective"):
        quote(settings_for(entry(unit, reference_only=True)), kind)


def test_reference_catalog_needs_no_upper_bound_declaration():
    reference = entry("image", reference_only=True)
    reference.pop("all_parameters_upper_bound")
    assert load_price_catalog(settings_for(reference)).prices[0].reference_only


@pytest.mark.parametrize("value", ["true", 1, None])
def test_upper_bound_marker_requires_literal_boolean(value):
    with pytest.raises(AIPricingError, match="invalid local"):
        load_price_catalog(settings_for(entry("image", all_parameters_upper_bound=value)))


def test_latest_unverified_rate_does_not_fall_back_to_old_verified_rate():
    settings = settings_for(
        entry("image"),
        entry("image", effective_at="2026-10-01T00:00:00Z",
              version="new-low-tier", all_parameters_upper_bound=False),
    )
    with pytest.raises(AIPricingError, match="all_parameters_upper_bound"):
        quote(settings, "image", now=datetime(2026, 10, 14, tzinfo=UTC))


def test_verified_media_upper_bound_is_frozen_for_actual_usage():
    result = quote(settings_for(entry("video_second", rate_microusd=1234)), "video")
    price = result.snapshot["prices"]["video_second"]
    assert price["all_parameters_upper_bound"] is True
    assert result.estimated_cost_microusd == 12_340
    assert actual_cost_from_snapshot(
        result.snapshot, input_tokens=None, output_tokens=None, video_seconds=7,
    ) == 8638


@pytest.mark.parametrize("unverified", ["input_token", "output_token"])
def test_text_requires_max_tier_rates_for_both_input_and_output(unverified):
    entries = [
        entry("input_token", trusted_input_token_upper_bound=20_000),
        entry("output_token"),
    ]
    for price in entries:
        if price["unit"] == unverified:
            price.pop("all_parameters_upper_bound")
    with pytest.raises(AIPricingError, match="all_parameters_upper_bound"):
        estimate_text_price(
            settings_for(*entries), provider="paid-adapter", model="exact-model",
            input_chars=1, input_image_count=0, max_output_tokens=1,
        )


def test_text_heuristic_cannot_replace_verified_provider_context_limit():
    with pytest.raises(AIPricingError, match="trusted_input_token_upper_bound"):
        estimate_text_price(
            settings_for(entry("input_token"), entry("output_token")),
            provider="paid-adapter", model="exact-model",
            input_chars=1_000_000, input_image_count=100, max_output_tokens=1,
        )


def test_text_reserves_full_trusted_input_limit_including_images_and_schema():
    settings = settings_for(
        entry("input_token", rate_microusd=2, trusted_input_token_upper_bound=128_000),
        entry("output_token", rate_microusd=8),
    )
    results = [
        estimate_text_price(
            settings, provider="paid-adapter", model="exact-model",
            input_chars=chars, input_image_count=images, max_output_tokens=1000,
        )
        for chars, images in ((1, 0), (100_000, 20))
    ]
    for result in results:
        assert result.estimated_cost_microusd == 264_000
        assert result.snapshot["quantities"] == {
            "input_token": 128_000, "output_token": 1000,
        }
        assert result.snapshot["input_bound_source"] == "TRUSTED_MODEL_INPUT_TOKEN_UPPER_BOUND"


def test_full_trusted_context_cannot_exceed_request_cap():
    settings = settings_for(
        entry("input_token", trusted_input_token_upper_bound=128_000),
        entry("output_token"),
    )
    with pytest.raises(AIPricingError, match="request cap"):
        estimate_text_price(
            settings, provider="paid-adapter", model="exact-model",
            input_chars=1, input_image_count=0, max_output_tokens=1,
        )


@pytest.mark.parametrize("provider", ["offline:fake", "offline:replay"])
def test_explicit_offline_can_keep_synthetic_capacity(provider):
    result = estimate_text_price(
        settings_for(), provider=provider, model="synthetic",
        input_chars=1, input_image_count=0, max_output_tokens=1,
    )
    assert result.snapshot["price_status"] == "CONSERVATIVE_CAP"


def test_arbitrary_offline_prefix_does_not_authorize_unknown_price():
    with pytest.raises(AIPricingError, match="no effective"):
        estimate_price(settings_for(), provider="offline:wavespeed", model="exact-model")
