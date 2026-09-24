from datetime import UTC, datetime

import pytest
from libtv_agent.adapters.kling_official_api import _retry_after
from libtv_agent.adapters.retry_after import parse_retry_after
from libtv_agent.adapters.wavespeed import WaveSpeedAdapter, WaveSpeedError, WaveSpeedHttpResponse
from test_wavespeed_adapter import _settings


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2", 2),
        ("0", 0),
        ("-5", 0),
        ("NaN", None),
        ("inf", None),
        ("-inf", None),
        ("garbage", None),
        ("", None),
        ("Thu, 24 Sep 2026 00:00:05 GMT", 5),
        ("Wed, 23 Sep 2026 23:59:59 GMT", 0),
    ],
)
def test_retry_after_contract(value, expected):
    assert parse_retry_after(value, now=datetime(2026, 9, 24, tzinfo=UTC)) == expected


def test_kling_header_is_case_insensitive_and_nonfinite_is_rejected():
    assert _retry_after({"rEtRy-AfTeR": "3"}) == 3
    assert _retry_after({"Retry-After": "inf"}) is None
    assert _retry_after({}) is None


def test_http_date_is_used_by_both_adapters(tmp_path):
    from datetime import timedelta
    from email.utils import format_datetime

    value = format_datetime(datetime.now(UTC) + timedelta(seconds=20), usegmt=True)
    assert 18 <= _retry_after({"Retry-After": value}) <= 20
    adapter = WaveSpeedAdapter(_settings(tmp_path, wavespeed_get_retry_max_seconds=30))
    assert 18 <= adapter._retry_delay(0, {"Retry-After": value}) <= 20


@pytest.mark.parametrize("failure", [429, 503, "network"])
async def test_get_retries_are_bounded_and_keep_task_identity(tmp_path, monkeypatch, failure):
    calls, sleeps = [], []

    async def transport(method, url, headers, body, request_timeout):
        calls.append((method, url))
        if failure == "network":
            raise OSError("synthetic disconnect")
        return WaveSpeedHttpResponse(failure, {"Retry-After": "999999"}, b"{}")

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("libtv_agent.adapters.wavespeed.asyncio.sleep", sleep)
    adapter = WaveSpeedAdapter(
        _settings(tmp_path, wavespeed_get_max_retries=3), http_request=transport
    )
    with pytest.raises(WaveSpeedError):
        await adapter.get_prediction("original-task")
    assert len(calls) == 3
    assert len(set(calls)) == 1
    assert calls[0][0] == "GET" and "original-task" in calls[0][1]
    assert len(sleeps) == 2
    assert all(0 <= delay <= adapter.settings.wavespeed_get_retry_max_seconds for delay in sleeps)
