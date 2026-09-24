import errno
import io
from pathlib import Path
from urllib.error import HTTPError

import pytest
from libtv_agent.adapters.bach_provider import BachApiAdapter
from libtv_agent.adapters.kling_official_api import KlingOfficialApiAdapter
from libtv_agent.adapters.kling_official_cli import KlingCliError, KlingOfficialCliAdapter
from libtv_agent.adapters.video_provider import ProviderOutput
from libtv_agent.adapters.wavespeed_video import WaveSpeedVideoAdapter
from test_kling_api_adapter import _settings


@pytest.mark.parametrize("fault", ["truncated", "disk_full", "expired"])
@pytest.mark.parametrize("provider", ["api", "cli", "wavespeed", "bach"])
async def test_download_fault_never_publishes_partial_and_can_recover(
    tmp_path, monkeypatch, fault, provider
):
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

    adapter_type, module = {
        "api": (KlingOfficialApiAdapter, "kling_official_api"),
        "cli": (KlingOfficialCliAdapter, "kling_official_cli"),
        "wavespeed": (WaveSpeedVideoAdapter, "wavespeed_video"),
        "bach": (BachApiAdapter, "bach_provider"),
    }[provider]
    monkeypatch.setattr(f"libtv_agent.adapters.{module}.urlopen", fetch)
    monkeypatch.setattr(Path, "open", open_file)
    adapter = adapter_type(_settings(tmp_path))
    output = ProviderOutput(url="https://synthetic.invalid/video.mp4", content_type="video")
    with pytest.raises(KlingCliError) as error:
        await adapter.download(output, destination)
    assert error.value.code.endswith("DOWNLOAD_FAILED")
    assert not destination.exists()
    assert not destination.with_suffix(".mp4.part").exists()
    failing = False
    result = await adapter.download(output, destination)
    assert result.path.read_bytes() == data
    assert calls == ["GET", "GET"]
