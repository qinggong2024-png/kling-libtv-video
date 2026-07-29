import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from libtv_agent.config import Settings  # noqa: E402
from libtv_agent.db import Database  # noqa: E402
from minio import Minio  # noqa: E402
from sqlalchemy import text  # noqa: E402


def _object_hash(client: Minio, bucket: str, key: str) -> str:
    response = client.get_object(bucket, key)
    try:
        digest = hashlib.sha256()
        for chunk in response.stream(1024 * 1024):
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        response.close()
        response.release_conn()


def _url_hash(url: str) -> str:
    digest = hashlib.sha256()
    with urlopen(url, timeout=15) as response:  # noqa: S310 - URL is MinIO-generated locally
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def verify(expected_object_count: int, settings: Settings) -> dict[str, object]:
    database = Database(settings.database_url)
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    try:
        async with database.session_factory() as session:
            table_count = int(
                await session.scalar(
                    text(
                        "select count(*) from information_schema.tables where table_schema='public'"
                    )
                )
                or 0
            )
            points_rows = int(await session.scalar(text("select count(*) from points_ledger")) or 0)
            audit_rows = int(await session.scalar(text("select count(*) from audit_event")) or 0)
            restore_rows = int(
                await session.scalar(
                    text(
                        "select count(*) from download_artifact where source_type='REMOTE_RESTORE'"
                    )
                )
                or 0
            )
            artifacts = (
                await session.execute(
                    text(
                        "select object_key, sha256 from download_artifact "
                        "where object_key is not null and sha256 is not null"
                    )
                )
            ).all()
        objects = await asyncio.to_thread(
            lambda: list(client.list_objects(settings.minio_bucket, recursive=True))
        )
        hash_mismatches: list[str] = []
        object_names = {item.object_name for item in objects}
        for object_key, expected_hash in artifacts:
            if object_key not in object_names:
                hash_mismatches.append(hashlib.sha256(object_key.encode()).hexdigest()[:12])
                continue
            actual_hash = await asyncio.to_thread(
                _object_hash, client, settings.minio_bucket, object_key
            )
            if actual_hash != expected_hash:
                hash_mismatches.append(hashlib.sha256(object_key.encode()).hexdigest()[:12])
        signed_url_verified = False
        if objects:
            signed = await asyncio.to_thread(
                client.presigned_get_object,
                settings.minio_bucket,
                objects[0].object_name,
                expires=timedelta(minutes=5),
            )
            direct_hash = await asyncio.to_thread(
                _object_hash, client, settings.minio_bucket, objects[0].object_name
            )
            signed_hash = await asyncio.to_thread(_url_hash, signed)
            signed_url_verified = "X-Amz-Signature=" in signed and signed_hash == direct_hash
        passed = (
            table_count > 0
            and len(objects) == expected_object_count
            and not hash_mismatches
            and (signed_url_verified or not objects)
        )
        return {
            "status": "PASS" if passed else "FAIL",
            "checkedAt": datetime.now(UTC).isoformat(),
            "publicTableCount": table_count,
            "pointsLedgerRows": points_rows,
            "auditRows": audit_rows,
            "remoteRestoreRows": restore_rows,
            "objectCount": len(objects),
            "expectedObjectCount": expected_object_count,
            "artifactHashMismatchKeyHashes": hash_mismatches,
            "presignedUrl": {
                "status": "PASS"
                if signed_url_verified
                else "NOT_APPLICABLE"
                if not objects
                else "FAIL",
                "expiresSeconds": 300,
                "urlRetained": False,
            },
        }
    finally:
        await database.engine.dispose()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-object-count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = Settings()
    report = await verify(args.expected_object_count, settings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
