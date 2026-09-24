import asyncio
import threading

import pytest
from libtv_agent.adapters.download_worker import stage_download


@pytest.mark.parametrize("mode", ["cancel", "timeout", "repeat_cancel"])
async def test_cancelled_thread_never_publishes_and_is_drained(tmp_path, mode):
    entered, release = threading.Event(), threading.Event()
    temporary, destination = tmp_path / "video.part", tmp_path / "video.mp4"

    def worker():
        entered.set()
        assert release.wait(5)
        temporary.write_bytes(b"late data")
        return 9

    task = asyncio.create_task(
        stage_download(
            worker,
            temporary,
            destination,
            timeout=0.02 if mode == "timeout" else 5,
        )
    )
    try:
        for _ in range(500):
            if entered.is_set():
                break
            await asyncio.sleep(0.001)
        assert entered.is_set()
        if mode != "timeout":
            task.cancel()
        await asyncio.sleep(0.05)
        if mode == "repeat_cancel":
            task.cancel()
            await asyncio.sleep(0)
        assert not task.done()
        assert not destination.exists()
    finally:
        release.set()
        with pytest.raises(TimeoutError if mode == "timeout" else asyncio.CancelledError):
            await task
    assert not destination.exists()
    assert not temporary.exists()


async def test_completed_thread_publishes_once(tmp_path):
    temporary, destination = tmp_path / "video.part", tmp_path / "video.mp4"

    def worker():
        temporary.write_bytes(b"data")
        return 4

    assert await stage_download(worker, temporary, destination, timeout=5) == 4
    assert destination.read_bytes() == b"data"
    assert not temporary.exists()
