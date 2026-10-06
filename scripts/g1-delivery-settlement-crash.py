"""Fresh-process crash drill for delivery and settlement recovery.

The drill uses only a temporary SQLite database and synthetic download/object-store
implementations.  It intentionally exits a worker between durable checkpoints, then
lets a fresh worker resume the same attempt.
"""

import asyncio
import json
import os
import pathlib
import sys
from types import SimpleNamespace

SOURCE = pathlib.Path(__file__).resolve().parents[1]
ROOT = pathlib.Path(sys.argv[1]).resolve()
MODE = sys.argv[2]
if MODE not in {"seed-download", "recover-download", "seed-settlement", "recover-settlement"}:
    raise SystemExit("invalid mode")
ROOT.mkdir(parents=True, exist_ok=True)
os.environ["APP_ENV"] = "test"
os.environ["USERPROFILE"] = str(ROOT)
os.environ["TEMP"] = str(ROOT)
os.environ["TMP"] = str(ROOT)
os.chdir(ROOT)
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE / "backend/src"))


def _settings(root):
    from libtv_agent.config import Settings

    return Settings(
        _env_file=None,
        app_env="test",
        object_store_mode="local",
        runner_root=root / "runner",
        artifact_root=root / "artifacts",
        paid_submissions_paused=False,
        kling_api_enabled=False,
        generation_estimated_points=240,
        daily_user_points_limit=5000,
    )


async def _seed(factory, settings, engine):
    from libtv_agent.domain.enums import (
        AttemptStatus,
        CommandStatus,
        DownloadStatus,
        GenerationStatus,
        ParentTaskPhase,
        VariantKind,
    )
    from libtv_agent.domain.models import (
        Base,
        GenerationAttempt,
        GenerationCommand,
        GenerationVariant,
        ParentTask,
        User,
    )
    from libtv_agent.services.points import reserve_points

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        user = User(username="g1-delivery-crash", password_hash="disabled")
        session.add(user)
        await session.flush()
        task = ParentTask(
            user_id=user.id,
            client_task_id="g1-delivery-crash",
            title="g1 delivery crash",
            asset_count=1,
            phase=ParentTaskPhase.DOWNLOADING,
        )
        session.add(task)
        await session.flush()
        variant = GenerationVariant(
            parent_task_id=task.id,
            variant_type=VariantKind.STABLE,
            prompt_text="synthetic delivery crash",
            generation_config_json={"model": "synthetic"},
            generation_status=GenerationStatus.SUCCEEDED,
        )
        session.add(variant)
        await session.flush()
        attempt = GenerationAttempt(
            variant_id=variant.id,
            provider="kling_official_api",
            provider_model="synthetic",
            intent_hash="a" * 64,
            status=AttemptStatus.SUCCEEDED,
            task_id="saved-remote-handle",
            output_url="https://synthetic.invalid/video.mp4",
            raw_response_json={"videoUrl": "https://synthetic.invalid/video.mp4"},
            credits_consumed=240,
        )
        session.add(attempt)
        await session.flush()
        command = GenerationCommand(
            attempt_id=attempt.id,
            status=CommandStatus.TERMINAL,
            command_manifest_json={"provider": "kling_official_api"},
        )
        session.add(command)
        await session.flush()
        await reserve_points(
            session,
            user_id=user.id,
            attempt_id=attempt.id,
            estimated_points=240,
            daily_limit=5000,
        )
        # Both scenarios enter recovery through the same durable state.
        variant.download_status = DownloadStatus.DOWNLOADING
        await session.commit()
        (ROOT / "attempt.json").write_text(json.dumps({"attempt_id": str(attempt.id)}))


async def _run(mode):
    from libtv_agent.domain.enums import DownloadStatus, LedgerEntryType, ReservationStatus
    from libtv_agent.domain.models import (
        DownloadArtifact,
        GenerationVariant,
        PointsLedger,
        PointsReservation,
    )
    from libtv_agent.runner.supervisor import RunnerSupervisor
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    database = ROOT / "delivery-settlement-crash.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _settings(ROOT)

    if mode.startswith("seed-"):
        await _seed(factory, settings, engine)

    async def fake_download(_adapter, *, url, destination, **_kwargs):
        assert url == "https://synthetic.invalid/video.mp4"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"synthetic-video")
        if mode == "seed-download":
            (ROOT / "download-entered").write_text("1")
            await asyncio.Event().wait()

    async def fake_validate(*_args, **_kwargs):
        return SimpleNamespace(
            sha256="b" * 64,
            size_bytes=15,
            duration_seconds=5.0,
            width=1080,
            height=1920,
            has_audio=True,
            passed=True,
            issue_codes=(),
        )

    async def put_file(_path, object_key, _content_type):
        (ROOT / "object-store-put").write_text(object_key)
        return object_key

    import libtv_agent.runner.supervisor as supervisor_module

    supervisor_module.download_with_retries = fake_download
    supervisor_module.technical_validate = fake_validate
    supervisor = RunnerSupervisor(object(), SimpleNamespace(put_file=put_file), settings)
    supervisor._kling_adapters["kling_official_api"] = object()

    async with factory() as session:
        if mode == "seed-settlement":
            original_commit = session.commit
            commits = 0

            async def interrupted_commit():
                nonlocal commits
                commits += 1
                await original_commit()
                if commits == 2:
                    (ROOT / "settlement-committed").write_text("1")
                    await asyncio.Event().wait()

            session.commit = interrupted_commit
        resumed = await supervisor.resume_incomplete_downloads(session)
        await session.commit()

    async with factory() as session:
        artifacts = list(await session.scalars(select(DownloadArtifact)))
        entries = list(await session.scalars(select(PointsLedger)))
        reservation = await session.scalar(select(PointsReservation))
        variant = await session.scalar(select(GenerationVariant))
        result = {
            "mode": mode,
            "resumed": resumed,
            "artifacts": len(artifacts),
            "ready_artifacts": sum(a.status == DownloadStatus.READY for a in artifacts),
            "consume_entries": sum(e.entry_type == LedgerEntryType.CONSUME for e in entries),
            "ledger_entries": [e.entry_type.value for e in entries],
            "reservation": reservation.status.value if reservation else None,
            "download_status": variant.download_status.value if variant else None,
        }
        if mode.startswith("recover-"):
            assert resumed == 1
            assert result["artifacts"] == 1
            assert result["ready_artifacts"] == 1
            assert result["consume_entries"] == 1
            assert result["reservation"] == ReservationStatus.SETTLED.value
            await session.close()
            async with factory() as replay:
                assert await supervisor.resume_incomplete_downloads(replay) == 0
        (ROOT / f"{mode}.json").write_text(json.dumps(result, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run(MODE))
