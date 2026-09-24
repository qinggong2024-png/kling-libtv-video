import errno
import io
from pathlib import Path
from urllib.error import HTTPError

import pytest
from libtv_agent.adapters.kling_official_api import KlingApiError, KlingOfficialApiAdapter
from libtv_agent.adapters.video_provider import ProviderOutput
from test_kling_api_adapter import _settings


@pytest.mark.parametrize("fault", ["truncated", "disk_full", "expired"])
async def test_download_fault_never_publishes_partial_and_can_recover(tmp_path, monkeypatch, fault):
    data = b"\x00\x00\x00\x18ftypmp42synthetic-video"
    destination = tmp_path / "output.mp4"
    calls = []
    failing = True

    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Type": "video/mp4", "Content-Length": str(len(data))}

    def fetch(request, **kwargs):
        calls.append(request.get_method())
        if failing and fault == "expired":
            raise HTTPError(request.full_url, 403, "expired", {}, None)
        return Response(data[:6] if failing and fault == "truncated" else data)

    original_open = Path.open

    def open_file(path, *args, **kwargs):
        if failing and fault == "disk_full" and path.suffix == ".part":
            raise OSError(errno.ENOSPC, "synthetic disk full")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr("libtv_agent.adapters.kling_official_api.urlopen", fetch)
    monkeypatch.setattr(Path, "open", open_file)
    adapter = KlingOfficialApiAdapter(_settings(tmp_path))
    output = ProviderOutput(url="https://synthetic.invalid/video.mp4", content_type="video")
    with pytest.raises(KlingApiError) as error:
        await adapter.download(output, destination)
    assert error.value.code == "KLING_DOWNLOAD_FAILED"
    assert not destination.exists()
    assert not destination.with_suffix(".mp4.part").exists()
    failing = False
    result = await adapter.download(output, destination)
    assert result.path.read_bytes() == data
    assert calls == ["GET", "GET"]
