"""Per-user daily image-generation quota.

Images are billed per submitted prediction, and the number of images a batch will produce
is already fixed when the batch is created (``image_generation_batch.expected_generation_count``).
That lets the quota be enforced *before* any paid call happens, and — unlike the video
quota in :mod:`libtv_agent.services.points` — it needs no reservation ledger: today's usage
is simply derived from the batches that already exist.

Design notes:

* The unit is *images*, i.e. the N the image centre reports as "正在处理 N 张图片".
  ``api.image_generations`` already asserts ``len(specs) == manifest.expectedGenerationCount``
  before the batch is persisted, so the stored value is trustworthy.
* A rejected request writes no batch row, so a blocked attempt never consumes quota.
* Batches that fail later still count for the day. That is deliberate and matches the
  conservative posture of the video quota, where a released reservation has never actually
  happened in production.
* The image budget is independent of the video budget: neither consumes the other.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING

from libtv_agent.domain.models import ImageGenerationBatch
from libtv_agent.services.points import SHANGHAI, business_date
from sqlalchemy import func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ImageQuotaExceededError(RuntimeError):
    """Raised when a new image batch would push today's usage past the daily limit."""

    def __init__(self, *, limit: int, used: int, requested: int) -> None:
        super().__init__(f"daily image limit exceeded: {used} used + {requested} > {limit}")
        self.limit = limit
        self.used = used
        self.requested = requested

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


def business_day_window(day: date) -> tuple[datetime, datetime]:
    """Half-open UTC window ``[start, end)`` covering one Asia/Shanghai calendar day.

    ``created_at`` is persisted in UTC (``server_default=CURRENT_TIMESTAMP``), so the
    comparison has to happen in UTC. The window is computed in Python rather than with a
    dialect-specific date expression so the query stays portable across SQLite / PostgreSQL.
    """
    start = datetime.combine(day, time.min, tzinfo=SHANGHAI).astimezone(UTC)
    return start, start + timedelta(days=1)


async def images_submitted_on(
    session: AsyncSession, *, user_id: uuid.UUID, day: date | None = None
) -> int:
    """How many images this user has already submitted for ``day`` (defaults to today)."""
    start, end = business_day_window(day or business_date())
    total = await session.scalar(
        select(func.coalesce(func.sum(ImageGenerationBatch.expected_generation_count), 0)).where(
            ImageGenerationBatch.user_id == user_id,
            ImageGenerationBatch.created_at >= start,
            ImageGenerationBatch.created_at < end,
        )
    )
    return int(total or 0)


async def assert_image_quota_available(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    requested_images: int,
    daily_limit: int,
    now: datetime | None = None,
) -> int:
    """Raise :class:`ImageQuotaExceededError` unless the request fits in today's budget.

    Returns how many images were already submitted today, which callers may log and tests
    assert on. ``requested_images`` must be the server-derived image count, never a
    client-supplied figure.
    """
    if requested_images < 0:
        raise ValueError("requested_images must not be negative")
    used = await images_submitted_on(session, user_id=user_id, day=business_date(now))
    if used + requested_images > daily_limit:
        raise ImageQuotaExceededError(limit=daily_limit, used=used, requested=requested_images)
    return used
