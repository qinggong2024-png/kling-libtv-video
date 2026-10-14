import asyncio
import json
import os
import shutil
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from libtv_agent.adapters.object_store import LocalObjectStore
from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.db import Database
from libtv_agent.domain.enums import (
    AttemptStatus,
    DownloadStatus,
    GenerationStatus,
    QualityDecisionStatus,
    UserRole,
    ValidationStatus,
    VariantKind,
)
from libtv_agent.domain.models import (
    Base,
    CutflowHandoff,
    DownloadArtifact,
    GenerationAttempt,
    GenerationVariant,
    ParentTask,
    User,
)
from libtv_agent.runner import cutflow_worker
from libtv_agent.services.cutflow_handoff import (
    CutflowHandoffError,
    copy_verified,
    create_cutflow_handoff,
    import_outputs,
    publish_package,
    safe_path,
    sha256_file,
)
from sqlalchemy import func, select


@pytest.fixture
async def handoff_env(tmp_path):
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'handoff.db').as_posix()}",
        artifact_root=tmp_path / "cache",
        cutflow_handoff_enabled=True,
        cutflow_handoff_root=tmp_path / "nas",
        cutflow_base_url="http://cutflow.test:3001",
        cutflow_service_token="isolated-test-token",
    )
    database = Database(settings.database_url)
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    ids = {key: uuid.uuid4() for key in ["user", "other", "task", "variant", "attempt", "artifact"]}
    store = LocalObjectStore(tmp_path / "objects")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"generated-video")
    key = await store.put_file(source, "outputs/video.mp4", "video/mp4")
    async with database.session_factory() as session:
        session.add_all(
            [
                User(id=ids["user"], username="owner", password_hash="unused"),
                User(id=ids["other"], username="other", password_hash="unused"),
                ParentTask(
                    id=ids["task"],
                    user_id=ids["user"],
                    client_task_id="test",
                    title="Handoff test",
                    asset_count=1,
                ),
                GenerationVariant(
                    id=ids["variant"],
                    parent_task_id=ids["task"],
                    variant_type=VariantKind.STABLE,
                    generation_status=GenerationStatus.SUCCEEDED,
                    download_status=DownloadStatus.READY,
                    validation_status=ValidationStatus.PASSED,
                    final_approval_status=QualityDecisionStatus.APPROVED,
                ),
                GenerationAttempt(
                    id=ids["attempt"],
                    variant_id=ids["variant"],
                    status=AttemptStatus.SUCCEEDED,
                    provider="kling",
                ),
                DownloadArtifact(
                    id=ids["artifact"],
                    attempt_id=ids["attempt"],
                    status=DownloadStatus.READY,
                    object_key=key,
                    sha256=sha256_file(source),
                    revision=1,
                ),
            ]
        )
        await session.commit()
    try:
        yield database, settings, store, ids
    finally:
        await database.dispose()


async def enqueue(env, user=None):
    database, settings, store, ids = env
    async with database.session_factory() as session:
        row = await create_cutflow_handoff(
            session,
            settings=settings,
            object_store=store,
            user_id=user or ids["user"],
            task_id=ids["task"],
            variant_id=ids["variant"],
        )
        await session.commit()
        return row


async def test_api_enqueue_does_not_copy_and_worker_publishes_verified_package(handoff_env):
    database, settings, store, ids = handoff_env
    row = await enqueue(handoff_env)
    assert row.status == "QUEUED"
    assert not settings.cutflow_handoff_root.exists()
    async with database.session_factory() as session:
        artifact = await session.get(DownloadArtifact, ids["artifact"])
        descriptor = await publish_package(row, artifact, settings, store)
        original = await store.localize(artifact.object_key, Path("unused"))
        assert original.is_file()
    package = settings.cutflow_handoff_root / "inbox" / row.handoff_key
    assert json.loads((package / "READY").read_text())["sha256"] == descriptor["manifestSha256"]
    manifest = json.loads((package / "manifest.json").read_text())
    assert manifest["source"]["user_id"] == str(ids["user"])
    assert manifest["assets"][0]["sha256"] == sha256_file(package / "assets/generated-video.mp4")


async def test_concurrent_enqueue_is_idempotent(handoff_env):
    rows = await asyncio.gather(*(enqueue(handoff_env) for _ in range(10)))
    assert len({row.id for row in rows}) == 1
    async with handoff_env[0].session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(CutflowHandoff)) == 1


async def test_cross_owner_and_unvalidated_media_rejected(handoff_env):
    with pytest.raises(CutflowHandoffError, match="不存在"):
        await enqueue(handoff_env, handoff_env[3]["other"])
    async with handoff_env[0].session_factory() as session:
        variant = await session.get(GenerationVariant, handoff_env[3]["variant"])
        variant.validation_status = ValidationStatus.FAILED
        await session.commit()
    with pytest.raises(CutflowHandoffError, match="尚未完成"):
        await enqueue(handoff_env)


async def test_source_hash_failure_never_publishes_ready(handoff_env):
    database, settings, store, ids = handoff_env
    row = await enqueue(handoff_env)
    async with database.session_factory() as session:
        artifact = await session.get(DownloadArtifact, ids["artifact"])
        artifact.sha256 = "a" * 64
        with pytest.raises(CutflowHandoffError, match="哈希"):
            await publish_package(row, artifact, settings, store)
    assert not (settings.cutflow_handoff_root / "inbox" / row.handoff_key / "READY").exists()


@pytest.mark.parametrize("path", ["../other.mp4", "/abs.mp4", "C:/x.mp4", "a\\b", "a/../b"])
def test_relative_path_containment(tmp_path, path):
    with pytest.raises(CutflowHandoffError):
        safe_path(tmp_path, path)


def test_copy_limit_and_corruption_leave_no_complete_file(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"video")
    destination = tmp_path / "result"
    for digest, limit in [("a" * 64, 100), (sha256_file(source), 1)]:
        with pytest.raises(CutflowHandoffError):
            copy_verified(source, destination, digest, limit)
        assert not destination.exists()
        assert not list(tmp_path.glob("*.part"))


async def test_worker_lost_response_retries_same_receipt_and_recovers_lease(
    handoff_env,
    monkeypatch,
):
    database, settings, store, ids = handoff_env
    row = await enqueue(handoff_env)
    calls = []

    def remote(_settings, method, suffix, payload=None):
        calls.append(payload if method == "POST" else suffix)
        if len(calls) == 1:
            raise TimeoutError("lost response")
        return {
            "handoffId": row.handoff_key,
            "status": "uploading",
            "batchId": str(uuid.uuid4()),
            "outputs": [],
        }

    monkeypatch.setattr(cutflow_worker, "control_request", remote)
    await cutflow_worker.tick(database, settings, store)
    async with database.session_factory() as session:
        saved = await session.get(CutflowHandoff, row.id)
        assert saved.manifest_path and saved.failure_count == 1
        descriptor = saved.manifest_json
        saved.next_run_at = None
        saved.lease_token = "dead-worker"
        saved.lease_until = datetime.now(UTC) - timedelta(minutes=1)
        await session.commit()
    await cutflow_worker.tick(database, settings, store)
    assert calls[0] == descriptor == calls[1]
    async with database.session_factory() as session:
        saved = await session.get(CutflowHandoff, row.id)
        assert saved.status == "AWAITING_EDIT" and saved.lease_token is None


async def test_live_lease_blocks_duplicate_worker(handoff_env):
    database, settings, store, _ids = handoff_env
    row = await enqueue(handoff_env)
    async with database.session_factory() as session:
        saved = await session.get(CutflowHandoff, row.id)
        saved.lease_token = "live"
        saved.lease_until = datetime.now(UTC) + timedelta(minutes=1)
        await session.commit()
    assert not await cutflow_worker.tick(database, settings, store)


async def test_api_ownership_auditor_and_paths_not_exposed(handoff_env):
    database, settings, store, ids = handoff_env
    app = create_app(settings)
    app.state.database = database
    app.state.object_store = store
    app.state.settings = settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = {"taskId": str(ids["task"]), "variantId": str(ids["variant"])}
        result = await client.post(
            "/api/v1/cutflow-handoffs", json=body, headers={"X-User-Id": str(ids["user"])}
        )
        assert result.status_code == 202
        assert "manifestPath" not in result.json()
        handoff_id = result.json()["id"]
        other = {"X-User-Id": str(ids["other"])}
        assert (
            await client.get(f"/api/v1/cutflow-handoffs/{handoff_id}", headers=other)
        ).status_code == 404
        assert (
            await client.get(f"/api/v1/cutflow-handoffs/{handoff_id}/outputs/x", headers=other)
        ).status_code == 404
        async with database.session_factory() as session:
            actor = await session.get(User, ids["user"])
            actor.role = UserRole.AUDITOR
            await session.commit()
        assert (
            await client.post(
                "/api/v1/cutflow-handoffs", json=body, headers={"X-User-Id": str(ids["user"])}
            )
        ).status_code == 403


async def test_real_video_return_is_separate_pending_derivative(handoff_env, tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and ffprobe required")
    database, settings, store, ids = handoff_env
    row = await enqueue(handoff_env)
    output_id = str(uuid.uuid4())
    output = settings.cutflow_handoff_root / "outbox" / row.handoff_key / "outputs" / "edited.mp4"
    output.parent.mkdir(parents=True)
    await asyncio.to_thread(
        subprocess.run,
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x288:rate=10",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ],
        check=True,
        timeout=30,
        capture_output=True,
    )
    result = {
        "id": output_id,
        "relative_path": "outputs/edited.mp4",
        "sha256": sha256_file(output),
        "size_bytes": output.stat().st_size,
    }
    saved = await import_outputs(row, [result], settings, store)
    assert saved[0]["review_status"] == "PENDING"
    assert saved[0]["width"] == 160
    row.outputs_json = saved
    assert await import_outputs(row, [result], settings, store) == saved
    with pytest.raises(CutflowHandoffError, match="变化"):
        await import_outputs(row, [{**result, "sha256": "a" * 64}], settings, store)
    async with database.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(DownloadArtifact)) == 1
        variant = await session.get(GenerationVariant, ids["variant"])
        assert variant.final_approval_status == QualityDecisionStatus.APPROVED


async def test_dual_repository_http_nas_ffmpeg_roundtrip(handoff_env, tmp_path):
    if not os.environ.get("CUTFLOW_SOURCE_ROOT") or not shutil.which("ffmpeg"):
        pytest.skip("Set CUTFLOW_SOURCE_ROOT to an isolated Cutflow checkout")
    database, settings, store, ids = handoff_env
    source = tmp_path / "real-source.mp4"
    await asyncio.to_thread(
        subprocess.run,
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x288:rate=10",
         "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)],
        check=True, timeout=30, capture_output=True,
    )
    async with database.session_factory() as session:
        artifact = await session.get(DownloadArtifact, ids["artifact"])
        artifact.object_key = await store.put_file(source, "outputs/real-source.mp4", "video/mp4")
        artifact.sha256 = sha256_file(source)
        await session.commit()
    helper = Path(__file__).parents[2] / "scripts/fixtures/cutflow-bridge-http.mjs"
    process = await asyncio.create_subprocess_exec(
        "node", str(helper), str(tmp_path / "cutflow"), str(settings.cutflow_handoff_root),
        str(ids["user"]), str(uuid.uuid4()),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        address = (await asyncio.wait_for(process.stdout.readline(), timeout=15)).decode().strip()
        assert address.startswith("http://127.0.0.1:")
        settings.cutflow_base_url = address
        row = await enqueue(handoff_env)
        await cutflow_worker.tick(database, settings, store)
        async with database.session_factory() as session:
            saved = await session.get(CutflowHandoff, row.id)
            assert saved.status == "PENDING_REVIEW", saved.error_code
            assert len(saved.outputs_json) == 1
            assert saved.outputs_json[0]["review_status"] == "PENDING"
            assert saved.outputs_json[0]["sha256"] != sha256_file(source)
            assert await session.scalar(select(func.count()).select_from(DownloadArtifact)) == 1
            variant = await session.get(GenerationVariant, ids["variant"])
            assert variant.final_approval_status == QualityDecisionStatus.APPROVED
    finally:
        process.terminate()
        await process.communicate()


def test_cutflow_migration_has_single_head_and_upgrades_existing_schema(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from libtv_agent import config as config_module
    from sqlalchemy import create_engine, inspect, text

    backend = Path(__file__).parents[1]
    configuration = Config(str(backend / "alembic.ini"))
    settings = Settings(
        _env_file=None, app_env="test",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'migration.db').as_posix()}",
    )
    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    assert ScriptDirectory.from_config(configuration).get_heads() == ["ca01b2c3d406"]
    command.upgrade(configuration, "e5f6a7b8c901")
    engine = create_engine(f"sqlite:///{(tmp_path / 'migration.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO app_user (id, username, password_hash, role, is_active, "
            "auto_confirm_prompts, video_learning_enabled, created_at) "
            "VALUES ('00000000000000000000000000000001','preserved','unused','USER',1,0,0,"
            "'2026-10-14 00:00:00')"
        ))
    command.upgrade(configuration, "head")
    with engine.connect() as connection:
        assert "cutflow_handoff" in inspect(connection).get_table_names()
        assert "ai_usage_reservation" in inspect(connection).get_table_names()
        assert "ai_usage_quota_summary" in inspect(connection).get_table_names()
        assert "ai_usage_ledger" in inspect(connection).get_table_names()
        assert connection.execute(text("SELECT username FROM app_user")).scalar() == "preserved"
        indexes = {entry["name"] for entry in inspect(connection).get_indexes("cutflow_handoff")}
        assert "ix_cutflow_handoff_status" in indexes
    engine.dispose()
