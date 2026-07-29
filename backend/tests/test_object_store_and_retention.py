import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from libtv_agent.adapters import object_store as object_store_module
from libtv_agent.adapters.object_store import (
    LocalObjectStore,
    MinioObjectStore,
    PrefixedObjectStore,
)
from libtv_agent.config import Settings
from libtv_agent.domain.enums import DownloadStatus
from libtv_agent.domain.models import Base, DownloadArtifact
from libtv_agent.services.retention import expire_download_artifacts
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_local_object_store_uses_relative_keys_and_rejects_traversal(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"phase-one")
    store = LocalObjectStore(tmp_path / "objects")

    key = await store.put_file(source, "users/user-1/inputs/source.bin", "application/octet-stream")

    assert key == "users/user-1/inputs/source.bin"
    assert await store.exists(key)
    localized = await store.localize(key, tmp_path / "unused" / "copy.bin")
    assert localized.read_bytes() == b"phase-one"
    with pytest.raises(ValueError, match="normalized relative"):
        await store.exists("../outside.bin")
    await store.delete(key)
    assert not await store.exists(key)


@pytest.mark.asyncio
async def test_environment_prefix_is_applied_once(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"isolated")
    store = PrefixedObjectStore(LocalObjectStore(tmp_path / "objects"), "staging")

    key = await store.put_file(source, "users/user-1/input.bin", "application/octet-stream")

    assert key == "staging/users/user-1/input.bin"
    assert await store.exists(key)


@pytest.mark.asyncio
async def test_minio_bucket_initialization_is_shared_by_concurrent_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubMinio:
        def __init__(self) -> None:
            self.bucket_checks = 0

        def bucket_exists(self, bucket: str) -> bool:
            del bucket
            self.bucket_checks += 1
            return True

    client = StubMinio()
    monkeypatch.setattr(object_store_module, "Minio", lambda *args, **kwargs: client)
    store = MinioObjectStore(Settings(object_store_mode="minio", _env_file=None))

    await asyncio.gather(*(store.ensure_bucket() for _ in range(8)))

    assert client.bucket_checks == 1


@pytest.mark.asyncio
async def test_output_retention_deletes_object_but_keeps_artifact_record(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'retention.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalObjectStore(tmp_path / "objects")
    source = tmp_path / "video.mp4"
    source.write_bytes(b"offline-video")
    key = await store.put_file(source, "users/u/outputs/task/video.mp4", "video/mp4")
    artifact_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            DownloadArtifact(
                id=artifact_id,
                attempt_id=uuid.uuid4(),
                status=DownloadStatus.READY,
                object_key=key,
                created_at=datetime.now(UTC) - timedelta(days=8),
            )
        )
        await session.commit()
        assert await expire_download_artifacts(session, store, retention_days=7) == 1
        artifact = await session.get(DownloadArtifact, artifact_id)
        assert artifact is not None
        assert artifact.object_key is None
        assert artifact.deletion_pending_at is not None
        assert artifact.deleted_at is not None
        assert artifact.status == DownloadStatus.READY
        assert not await store.exists(key)
    await engine.dispose()
