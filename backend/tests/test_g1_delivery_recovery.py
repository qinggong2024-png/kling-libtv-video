from types import SimpleNamespace

from libtv_agent.domain.enums import AttemptStatus, DownloadStatus, LedgerEntryType
from libtv_agent.domain.models import DownloadArtifact, GenerationAttempt, PointsLedger
from libtv_agent.runner.supervisor import RunnerSupervisor
from sqlalchemy import select
from test_image_quota_concurrency import world  # noqa: F401
from test_launch_started_recovery import _stranded_command


async def test_download_resume_preserves_handle_provider_and_single_settlement(
    world,  # noqa: F811
    monkeypatch,
):
    app, factory, _, _ = world
    async with factory() as setup:
        _, variant, attempt, _, _ = await _stranded_command(
            setup, provider="kling_official_api", lease_expires_at=None
        )
        attempt.credits_consumed = 240
        attempt.status = AttemptStatus.SUCCEEDED
        attempt.task_id = "saved-remote-handle"
        attempt.output_url = "https://synthetic.invalid/video.mp4"
        attempt.raw_response_json = {"videoUrl": attempt.output_url}
        variant.download_status = DownloadStatus.DOWNLOADING
        await setup.commit()
        attempt_id = attempt.id

    original = object()
    downloads = []

    async def download(adapter, **kwargs):
        assert adapter is original
        downloads.append(kwargs["url"])

    async def validate(*args, **kwargs):
        return SimpleNamespace(
            sha256="a" * 64,
            size_bytes=1024,
            duration_seconds=5.0,
            width=1080,
            height=1920,
            has_audio=True,
            passed=True,
            issue_codes=(),
        )

    async def put_file(*args):
        return "synthetic/output.mp4"

    monkeypatch.setattr("libtv_agent.runner.supervisor.download_with_retries", download)
    monkeypatch.setattr("libtv_agent.runner.supervisor.technical_validate", validate)
    supervisor = RunnerSupervisor(object(), SimpleNamespace(put_file=put_file), app.state.settings)
    supervisor._kling_adapters["kling_official_api"] = original
    async with factory() as recovery:
        assert await supervisor.resume_incomplete_downloads(recovery) == 1
    async with factory() as replay:
        assert await supervisor.resume_incomplete_downloads(replay) == 0
    async with factory() as verify:
        attempt = await verify.get(GenerationAttempt, attempt_id)
        assert attempt.task_id == "saved-remote-handle"
        assert attempt.status == AttemptStatus.SUCCEEDED
        artifacts = list(await verify.scalars(select(DownloadArtifact)))
        assert len(artifacts) == 1 and artifacts[0].status == DownloadStatus.READY
        entries = list(await verify.scalars(select(PointsLedger)))
        assert sorted(entry.entry_type for entry in entries) == sorted(
            [
                LedgerEntryType.RESERVE,
                LedgerEntryType.CONSUME,
            ]
        )
    assert downloads == ["https://synthetic.invalid/video.mp4"]
