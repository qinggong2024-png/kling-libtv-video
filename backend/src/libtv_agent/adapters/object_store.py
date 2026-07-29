import asyncio
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Protocol

from libtv_agent.config import Settings
from minio import Minio
from minio.error import S3Error


class ObjectStore(Protocol):
    async def put_file(self, source: Path, key: str, content_type: str) -> str: ...
    async def localize(self, key: str, destination: Path) -> Path: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def presign_get(self, key: str, expires_seconds: int = 300) -> str | None: ...


class PrefixedObjectStore:
    def __init__(self, inner: ObjectStore, prefix: str) -> None:
        self.inner = inner
        self.prefix = _safe_key(prefix)

    def _key(self, key: str) -> str:
        normalized = _safe_key(key)
        if normalized == self.prefix or normalized.startswith(f"{self.prefix}/"):
            return normalized
        return f"{self.prefix}/{normalized}"

    async def put_file(self, source: Path, key: str, content_type: str) -> str:
        object_key = self._key(key)
        return await self.inner.put_file(source, object_key, content_type)

    async def localize(self, key: str, destination: Path) -> Path:
        return await self.inner.localize(self._key(key), destination)

    async def delete(self, key: str) -> None:
        await self.inner.delete(self._key(key))

    async def exists(self, key: str) -> bool:
        return await self.inner.exists(self._key(key))

    async def presign_get(self, key: str, expires_seconds: int = 300) -> str | None:
        return await self.inner.presign_get(self._key(key), expires_seconds)


def _safe_key(key: str) -> str:
    normalized = key.replace("\\", "/").lstrip("/")
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("object key must be a normalized relative path")
    return normalized


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        candidate = (self.root / _safe_key(key)).resolve()
        if self.root not in candidate.parents:
            raise ValueError("object key escapes the storage root")
        return candidate

    async def put_file(self, source: Path, key: str, content_type: str) -> str:
        del content_type
        normalized = _safe_key(key)
        destination = self._path(normalized)
        await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(_copy_file, source, destination)
        return normalized

    async def localize(self, key: str, destination: Path) -> Path:
        source = self._path(key)
        if not await asyncio.to_thread(source.is_file):
            raise FileNotFoundError(key)
        return source

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, missing_ok=True)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).is_file)

    async def presign_get(self, key: str, expires_seconds: int = 300) -> str | None:
        del key, expires_seconds
        return None


class MinioObjectStore:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.minio_bucket
        self._bucket_ready = False
        self._bucket_lock = asyncio.Lock()
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    async def ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        async with self._bucket_lock:
            if self._bucket_ready:
                return
            await asyncio.to_thread(self._ensure_bucket_sync)
            self._bucket_ready = True

    def _ensure_bucket_sync(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    async def put_file(self, source: Path, key: str, content_type: str) -> str:
        normalized = _safe_key(key)
        await self.ensure_bucket()
        await asyncio.to_thread(
            self.client.fput_object,
            self.bucket,
            normalized,
            str(source),
            content_type,
        )
        return normalized

    async def localize(self, key: str, destination: Path) -> Path:
        normalized = _safe_key(key)
        await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self.client.fget_object, self.bucket, normalized, str(destination))
        return destination

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.remove_object, self.bucket, _safe_key(key))

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self.client.stat_object, self.bucket, _safe_key(key))
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return False
            raise
        return True

    async def presign_get(self, key: str, expires_seconds: int = 300) -> str | None:
        await self.ensure_bucket()
        return await asyncio.to_thread(
            self.client.presigned_get_object,
            self.bucket,
            _safe_key(key),
            expires=timedelta(seconds=expires_seconds),
        )


def _copy_file(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve():
        return
    shutil.copyfile(source, destination)


def create_object_store(settings: Settings) -> ObjectStore:
    if settings.object_store_mode == "minio":
        store: ObjectStore = MinioObjectStore(settings)
    else:
        store = LocalObjectStore(settings.artifact_root)
    return PrefixedObjectStore(store, settings.object_store_prefix)
