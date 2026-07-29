import hashlib
import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


@dataclass(frozen=True)
class PreprocessedImage:
    asset_id: uuid.UUID
    sha256: str
    normalized_path: Path
    thumbnail_path: Path
    width: int
    height: int
    mime_type: str
    order: int
    version: int = 1


def preprocess_image(
    data: bytes,
    filename: str,
    order: int,
    artifact_root: Path,
    *,
    asset_id: uuid.UUID | None = None,
    max_bytes: int = 20 * 1024 * 1024,
) -> PreprocessedImage:
    if not 1 <= order <= 7:
        raise ValueError("storyboard order must be between 1 and 7")
    if not data:
        raise ValueError("image is empty")
    if len(data) > max_bytes:
        raise ValueError(f"image exceeds the {max_bytes}-byte size limit")
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.verify()
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise ValueError("only JPEG, PNG and WebP storyboard images are supported")
            normalized = ImageOps.exif_transpose(source)
            if not 128 <= normalized.width <= 8192 or not 128 <= normalized.height <= 8192:
                raise ValueError("image dimensions must be between 128 and 8192 pixels")
            if normalized.mode not in {"RGB", "L"}:
                background = Image.new("RGB", normalized.size, "white")
                if "A" in normalized.getbands():
                    background.paste(normalized, mask=normalized.getchannel("A"))
                else:
                    background.paste(normalized.convert("RGB"))
                normalized = background
            else:
                normalized = normalized.convert("RGB")
            normalized_buffer = io.BytesIO()
            normalized.save(normalized_buffer, format="JPEG", quality=92, optimize=True)
            normalized_bytes = normalized_buffer.getvalue()
            width, height = normalized.size
            thumb = normalized.copy()
            thumb.thumbnail((360, 640), Image.Resampling.LANCZOS)
            thumb_buffer = io.BytesIO()
            thumb.save(thumb_buffer, format="JPEG", quality=82, optimize=True)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"invalid or incomplete image: {filename}") from exc

    resolved_id = asset_id or uuid.uuid4()
    digest = hashlib.sha256(normalized_bytes).hexdigest()
    normalized_path = artifact_root / "inputs" / str(resolved_id) / "normalized.jpg"
    thumbnail_path = artifact_root / "thumbs" / str(resolved_id) / "thumbnail.jpg"
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.write_bytes(normalized_bytes)
    thumbnail_path.write_bytes(thumb_buffer.getvalue())
    return PreprocessedImage(
        asset_id=resolved_id,
        sha256=digest,
        normalized_path=normalized_path,
        thumbnail_path=thumbnail_path,
        width=width,
        height=height,
        mime_type="image/jpeg",
        order=order,
    )
