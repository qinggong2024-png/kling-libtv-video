"""Parse the two standard Retry-After representations without accepting NaN/inf."""

import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def parse_retry_after(value: str, *, now: datetime | None = None) -> float | None:
    try:
        seconds = float(value)
    except ValueError:
        try:
            deadline = parsedate_to_datetime(value)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            seconds = (deadline - (now or datetime.now(UTC))).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None
