from datetime import UTC, datetime, timedelta

from libtv_agent.adapters.object_store import ObjectStore
from libtv_agent.domain.models import DownloadArtifact
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def expire_download_artifacts(
    session: AsyncSession,
    object_store: ObjectStore,
    *,
    retention_days: int,
    now: datetime | None = None,
) -> int:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    artifacts = list(
        await session.scalars(
            select(DownloadArtifact)
            .where(
                DownloadArtifact.object_key.is_not(None),
                DownloadArtifact.created_at <= cutoff,
            )
            .with_for_update(skip_locked=True)
        )
    )
    for artifact in artifacts:
        artifact.deletion_pending_at = now or datetime.now(UTC)
    await session.commit()
    for artifact in artifacts:
        if artifact.object_key:
            await object_store.delete(artifact.object_key)
            artifact.object_key = None
            artifact.deleted_at = now or datetime.now(UTC)
    await session.commit()
    return len(artifacts)
