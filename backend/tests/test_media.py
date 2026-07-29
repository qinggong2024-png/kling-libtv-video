import hashlib
from pathlib import Path

from libtv_agent.services.media import _hash_and_size


def test_hash_and_size_streams_complete_file(tmp_path: Path) -> None:
    payload = (b"streaming-hash-check" * 1024) + b"tail"
    path = tmp_path / "video.mp4"
    path.write_bytes(payload)

    digest, size = _hash_and_size(path, chunk_size=127)

    assert digest == hashlib.sha256(payload).hexdigest()
    assert size == len(payload)
