"""Durable NAS handoffs. HTTP requests enqueue; a separate worker transfers media."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from libtv_agent.adapters.object_store import ObjectStore
from libtv_agent.config import Settings
from libtv_agent.domain.enums import DownloadStatus, GenerationStatus, ValidationStatus
from libtv_agent.domain.models import (
    CutflowHandoff,
    DownloadArtifact,
    GenerationAttempt,
    GenerationVariant,
    ParentTask,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

CONTRACT = "libtv-to-cutflow/1.0"
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,160}$")


class CutflowHandoffError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def configured(settings: Settings) -> bool:
    return bool(
        settings.cutflow_handoff_enabled
        and settings.cutflow_handoff_root
        and settings.cutflow_base_url
        and settings.cutflow_service_token
    )


def require_configuration(settings: Settings) -> None:
    if not configured(settings):
        raise CutflowHandoffError("CUTFLOW_UNAVAILABLE", "Cutflow 交接服务尚未配置")
    parsed = urlsplit(settings.cutflow_base_url or "")
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise CutflowHandoffError("CUTFLOW_UNAVAILABLE", "Cutflow 服务地址配置无效")


def safe_path(root: Path, relative: str) -> Path:
    if (
        not isinstance(relative, str)
        or "\\" in relative
        or ":" in relative
        or relative.startswith("/")
        or any(p in {"", ".", ".."} for p in relative.split("/"))
    ):
        raise CutflowHandoffError("UNSAFE_PATH", "交接文件路径无效")
    canonical = root.resolve()
    result = (canonical / relative).resolve()
    if not result.is_relative_to(canonical) or result == canonical:
        raise CutflowHandoffError("UNSAFE_PATH", "交接文件路径越界")
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_verified(source: Path, destination: Path, expected: str, max_bytes: int) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.name}.{uuid.uuid4()}.part")
    try:
        size = 0
        digest = hashlib.sha256()
        with source.open("rb") as src, partial.open("xb") as dst:
            while chunk := src.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise CutflowHandoffError("MEDIA_TOO_LARGE", "视频超过交接大小上限")
                digest.update(chunk)
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        if size == 0 or digest.hexdigest() != expected or sha256_file(partial) != expected:
            raise CutflowHandoffError("VIDEO_HASH_MISMATCH", "视频文件哈希校验失败")
        os.replace(partial, destination)
        return size
    finally:
        partial.unlink(missing_ok=True)


def write_json_atomic(destination: Path, payload: dict[str, Any]) -> str:
    raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.name}.{uuid.uuid4()}.part")
    try:
        with partial.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(partial, destination)
    finally:
        partial.unlink(missing_ok=True)
    return hashlib.sha256(raw).hexdigest()


async def create_cutflow_handoff(
    session: AsyncSession,
    *,
    settings: Settings,
    object_store: ObjectStore,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    variant_id: uuid.UUID,
) -> CutflowHandoff:
    require_configuration(settings)
    row = (
        await session.execute(
            select(ParentTask, GenerationVariant)
            .join(GenerationVariant, GenerationVariant.parent_task_id == ParentTask.id)
            .where(
                ParentTask.id == task_id,
                ParentTask.user_id == user_id,
                GenerationVariant.id == variant_id,
            )
        )
    ).first()
    if row is None:
        raise CutflowHandoffError("TASK_NOT_FOUND", "视频结果不存在")
    task, variant = row
    attempt = await session.scalar(
        select(GenerationAttempt)
        .where(GenerationAttempt.variant_id == variant_id)
        .order_by(GenerationAttempt.created_at.desc(), GenerationAttempt.id.desc())
        .limit(1)
    )
    artifact = (
        await session.scalar(
            select(DownloadArtifact)
            .where(DownloadArtifact.attempt_id == attempt.id)
            .order_by(DownloadArtifact.revision.desc())
            .limit(1)
        )
        if attempt
        else None
    )
    if (
        artifact is None
        or not artifact.object_key
        or artifact.status != DownloadStatus.READY
        or variant.generation_status not in {GenerationStatus.SUCCEEDED, GenerationStatus.PARTIAL}
        or variant.validation_status not in {ValidationStatus.PASSED, ValidationStatus.WARNING}
    ):
        raise CutflowHandoffError("VIDEO_NOT_READY", "视频生成、下载或技术校验尚未完成")
    if (
        artifact.source_type.lower() in {"fake", "synthetic", "offline"}
        or (artifact.object_key.startswith(("fake:", "offline:", "synthetic:")))
        or attempt.provider.lower() in {"fake", "replay", "mock"}
    ):
        raise CutflowHandoffError("SYNTHETIC_MEDIA", "离线占位素材不能进入剪辑生产")
    existing_query = select(CutflowHandoff).where(
        CutflowHandoff.user_id == user_id,
        CutflowHandoff.artifact_id == artifact.id,
    )
    existing = await session.scalar(existing_query)
    if existing:
        return existing
    handoff_id = uuid.uuid4()
    handoff = CutflowHandoff(
        id=handoff_id,
        user_id=user_id,
        parent_task_id=task_id,
        variant_id=variant_id,
        artifact_id=artifact.id,
        handoff_key=f"handoff-{handoff_id}",
        status="QUEUED",
        contract_version=CONTRACT,
        manifest_path="",
        manifest_json={
            "source": {
                "user_id": str(user_id),
                "task_id": str(task_id),
                "variant_id": str(variant_id),
                "attempt_id": str(attempt.id),
                "artifact_id": str(artifact.id),
                "title": task.title,
            },
        },
    )
    try:
        async with session.begin_nested():
            session.add(handoff)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(existing_query)
        if existing is None:
            raise
        return existing
    return handoff


async def publish_package(
    handoff: CutflowHandoff,
    artifact: DownloadArtifact,
    settings: Settings,
    object_store: ObjectStore,
) -> dict[str, str]:
    root = Path(settings.cutflow_handoff_root)
    package = safe_path(root, f"inbox/{handoff.handoff_key}")
    local = settings.artifact_root / "cutflow-cache" / f"{handoff.id}.mp4"
    local.parent.mkdir(parents=True, exist_ok=True)
    try:
        source = await object_store.localize(artifact.object_key, local)
        expected = await asyncio.to_thread(sha256_file, source)
        if artifact.sha256 and expected != artifact.sha256:
            raise CutflowHandoffError("VIDEO_HASH_MISMATCH", "视频文件哈希校验失败")
        destination = safe_path(package, "assets/generated-video.mp4")
        size = await asyncio.to_thread(
            copy_verified,
            source,
            destination,
            expected,
            settings.cutflow_max_media_bytes,
        )
        manifest = {
            "schema_version": CONTRACT,
            "handoff_id": handoff.handoff_key,
            "source": handoff.manifest_json["source"],
            "assets": [
                {
                    "asset_id": str(handoff.variant_id),
                    "relative_path": "assets/generated-video.mp4",
                    "sha256": expected,
                    "size_bytes": size,
                    "duration_seconds": artifact.duration_seconds,
                    "width": artifact.width,
                    "height": artifact.height,
                    "order": 1,
                    "role": "generated_video",
                }
            ],
            "edit_intent": {"preserve_source_audio": artifact.has_audio},
            "created_at": handoff.created_at.isoformat(),
        }
        digest = await asyncio.to_thread(write_json_atomic, package / "manifest.json", manifest)
        await asyncio.to_thread(write_json_atomic, package / "READY", {"sha256": digest})
        return {
            "handoffId": handoff.handoff_key,
            "userId": str(handoff.user_id),
            "manifestSha256": digest,
        }
    finally:
        # LocalObjectStore returns its original object; only remove our own cache.
        await asyncio.to_thread(local.unlink, missing_ok=True)


async def import_outputs(
    handoff: CutflowHandoff,
    outputs: list[dict[str, Any]],
    settings: Settings,
    object_store: ObjectStore,
) -> list[dict[str, Any]]:
    from libtv_agent.services.media import technical_validate

    if len(outputs) > 50:
        raise CutflowHandoffError("INVALID_RESULT", "回传成片数量超过上限")
    saved = list(handoff.outputs_json or [])
    known = {item["id"]: item for item in saved}
    root = safe_path(Path(settings.cutflow_handoff_root), f"outbox/{handoff.handoff_key}")
    for output in outputs:
        output_id = output.get("id", "")
        digest = output.get("sha256", "")
        if (
            not isinstance(output_id, str)
            or not SAFE_SEGMENT.fullmatch(output_id)
            or (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest))
        ):
            raise CutflowHandoffError("INVALID_RESULT", "回传版本标识或哈希无效")
        if output_id in known:
            if known[output_id]["sha256"] != digest:
                raise CutflowHandoffError("IMMUTABLE_RESULT_CHANGED", "回传版本内容发生变化")
            continue
        source = safe_path(root, output["relative_path"])
        cache = settings.artifact_root / "cutflow-cache" / f"{handoff.id}-{output_id}.mp4"
        try:
            size = await asyncio.to_thread(
                copy_verified,
                source,
                cache,
                digest,
                settings.cutflow_max_media_bytes,
            )
            if size != output.get("size_bytes"):
                raise CutflowHandoffError("INVALID_RESULT", "回传文件大小不匹配")
            await asyncio.to_thread(_decode_check, cache)
            metadata = await asyncio.wait_for(
                technical_validate(
                    cache,
                    duration_min=0.1,
                    duration_max=300,
                    target_ratio=1,
                    ratio_tolerance=100,
                    allow_audio=True,
                ),
                timeout=120,
            )
            if not metadata.passed or metadata.width <= 0 or metadata.height <= 0:
                raise CutflowHandoffError("INVALID_RESULT", "回传视频技术校验失败")
            key = await object_store.put_file(
                cache,
                f"cutflow/{handoff.user_id}/{handoff.id}/{output_id}.mp4",
                "video/mp4",
            )
            saved.append(
                {
                    "id": output_id,
                    "sha256": digest,
                    "object_key": key,
                    "size_bytes": size,
                    "duration_seconds": metadata.duration_seconds,
                    "width": metadata.width,
                    "height": metadata.height,
                    "review_status": "PENDING",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            known[output_id] = saved[-1]
        finally:
            await asyncio.to_thread(cache.unlink, missing_ok=True)
    return saved


def _decode_check(path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise CutflowHandoffError("FFMPEG_REQUIRED", "回传视频校验需要 FFmpeg")
    try:
        subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-xerror",
                "-threads",
                "1",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-f",
                "null",
                "-",
            ],
            check=True,
            timeout=180,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise CutflowHandoffError("INVALID_RESULT", "回传视频完整解码失败") from exc
