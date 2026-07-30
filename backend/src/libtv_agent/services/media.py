import asyncio
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from libtv_agent.adapters.libtv import LibTVAdapter, LibTVError


def _hidden_process_creation_flags() -> int:
    return 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


@dataclass(frozen=True)
class TechnicalValidation:
    passed: bool
    issue_codes: tuple[str, ...]
    duration_seconds: float
    width: int
    height: int
    has_audio: bool
    sha256: str
    size_bytes: int


async def download_with_retries(
    adapter: LibTVAdapter, *, url: str, destination: Path, attempts: int = 5
) -> Path:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return await adapter.download_media(url=url, destination=destination)
        except LibTVError as exc:
            last_error = exc
            if exc.code != "DOWNLOAD_RETRYABLE":
                raise
        except Exception as exc:
            last_error = exc
            if not bool(getattr(exc, "retryable", False)):
                raise
    raise LibTVError(
        "DOWNLOAD_RETRYABLE", f"download failed after {attempts} attempts: {last_error}"
    )


async def technical_validate(
    path: Path,
    *,
    duration_min: float = 9.0,
    duration_max: float = 11.0,
    target_ratio: float = 9 / 16,
    ratio_tolerance: float = 0.01,
    allow_audio: bool = False,
) -> TechnicalValidation:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe is required for technical validation")
    process = await asyncio.create_subprocess_exec(
        ffprobe,
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=_hidden_process_creation_flags(),
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise ValueError(f"video is not decodable: {stderr.decode('utf-8', errors='replace')}")
    metadata = json.loads(stdout)
    video_streams = [
        stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "video"
    ]
    if not video_streams:
        raise ValueError("video stream is missing")
    video = video_streams[0]
    duration = float(metadata.get("format", {}).get("duration") or video.get("duration") or 0)
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    has_audio = any(stream.get("codec_type") == "audio" for stream in metadata.get("streams", []))
    issues: list[str] = []
    if not duration_min <= duration <= duration_max:
        issues.append("DURATION_OUT_OF_RANGE")
    if height <= 0 or abs((width / height) - target_ratio) > ratio_tolerance:
        issues.append("ASPECT_RATIO_INVALID")
    if has_audio and not allow_audio:
        issues.append("UNEXPECTED_AUDIO")
    digest, size = await asyncio.to_thread(_hash_and_size, path)
    return TechnicalValidation(
        not issues, tuple(issues), duration, width, height, has_audio, digest, size
    )


def _hash_and_size(path: Path, chunk_size: int = 4 * 1024 * 1024) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size
