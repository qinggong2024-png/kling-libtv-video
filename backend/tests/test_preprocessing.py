import io
from pathlib import Path

import pytest
from libtv_agent.services.preprocessing import preprocess_image
from PIL import Image


def image_bytes(size: tuple[int, int] = (320, 640)) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", size, "#2c8b65").save(stream, format="PNG")
    return stream.getvalue()


def test_preprocess_normalizes_and_builds_thumbnail(tmp_path: Path) -> None:
    result = preprocess_image(image_bytes(), "storyboard.png", 1, tmp_path)
    assert result.mime_type == "image/jpeg"
    assert (result.width, result.height) == (320, 640)
    assert result.normalized_path.read_bytes().startswith(b"\xff\xd8")
    assert result.thumbnail_path.exists()
    assert len(result.sha256) == 64


def test_preprocess_rejects_invalid_magic_and_dimensions(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid or incomplete"):
        preprocess_image(b"not-an-image", "fake.jpg", 1, tmp_path)
    with pytest.raises(ValueError, match="dimensions"):
        preprocess_image(image_bytes((32, 32)), "small.png", 1, tmp_path)


def test_preprocessing_rejects_oversized_input_before_decode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="size limit"):
        preprocess_image(b"x" * 11, "large.png", 1, tmp_path, max_bytes=10)
