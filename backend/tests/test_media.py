import hashlib
from pathlib import Path

from libtv_agent.services.media import _hash_and_size, technical_validation_options


def test_hash_and_size_streams_complete_file(tmp_path: Path) -> None:
    payload = (b"streaming-hash-check" * 1024) + b"tail"
    path = tmp_path / "video.mp4"
    path.write_bytes(payload)

    digest, size = _hash_and_size(path, chunk_size=127)

    assert digest == hashlib.sha256(payload).hexdigest()
    assert size == len(payload)


def test_technical_validation_options_follow_generation_config() -> None:
    assert technical_validation_options(
        {
            "durationSeconds": 6,
            "aspectRatio": "9:16",
            "audio": "native",
            "sound": False,
        }
    ) == {
        "duration_min": 5.0,
        "duration_max": 7.0,
        "target_ratio": 9 / 16,
        "allow_audio": True,
    }
