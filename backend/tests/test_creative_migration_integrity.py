from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

ROOT = Path(__file__).resolve().parents[2]
BEFORE = "d0c1e2f3a405"
AFTER = "d2f3a4b5c607"


def _migration_config(database: Path) -> Config:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database.as_posix()}"
    os.environ["APP_ENV"] = "test"
    from libtv_agent.config import get_settings

    get_settings.cache_clear()
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    return config


def _facts_hash(engine, table: str, columns: list[str], where: str | None = None) -> str:
    rows = engine.connect().execute(
        text(
            f"SELECT {', '.join(columns)} FROM {table}"
            f"{f' WHERE {where}' if where else ''} ORDER BY 1"
        )
    ).mappings()
    payload = [dict(row) for row in rows]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


@pytest.fixture
def migrated_database(tmp_path: Path):
    database = tmp_path / "migration.db"
    config = _migration_config(database)
    command.upgrade(config, BEFORE)
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    now = datetime.now(UTC).isoformat()
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    version_id = uuid.uuid4()
    task_id = uuid.uuid4()
    record_id = uuid.uuid4()
    command_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO app_user "
                "(id, username, password_hash, role, is_active, created_at) "
                "VALUES (:id, :username, :password_hash, 'USER', 1, :now)"
            ),
            {
                "id": str(user_id),
                "username": f"migration-{user_id}",
                "password_hash": "test-only",
                "now": now,
            },
        )
        connection.execute(
            text(
                "INSERT INTO product "
                "(id, user_id, internal_sku_id, created_at, updated_at) "
                "VALUES (:id, :user_id, :sku, :now, :now)"
            ),
            {"id": str(product_id), "user_id": str(user_id), "sku": "CW-OLD-001", "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO product_version "
                "(id, product_id, version_number, product_page_url, page_title, "
                "candidate_names, truth_fields, immutable_fields, allowed_variation, "
                "source_asset_references, license_status, status, created_at) "
                "VALUES (:id, :product_id, 1, :url, 'Old product', '[]', '{}', '{}', "
                "'[]', '[]', 'UNKNOWN', 'DRAFT', :now)"
            ),
            {
                "id": str(version_id),
                "product_id": str(product_id),
                "url": "https://example.invalid/old-product",
                "now": now,
            },
        )
        connection.execute(
            text(
                "INSERT INTO creative_task (id, user_id, product_id, status, state_version, "
                "snapshot_json) VALUES (:id, :user_id, :product_id, 'PLANNED', 1, '{}')"
            ),
            {"id": str(task_id), "user_id": str(user_id), "product_id": str(product_id)},
        )
        connection.execute(
            text(
                "INSERT INTO creative_record "
                "(id, task_id, kind, record_key, content_hash, payload_json) "
                "VALUES (:id, :task_id, 'HISTORY', 'old-1', :hash, '{}')"
            ),
            {"id": str(record_id), "task_id": str(task_id), "hash": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO creative_command "
                "(id, task_id, command_key, request_hash, result_json) "
                "VALUES (:id, :task_id, 'old-command', :hash, '{}')"
            ),
            {"id": str(command_id), "task_id": str(task_id), "hash": "b" * 64},
        )
    before = {
        table: _facts_hash(
            engine,
            table,
            columns,
            "version_number = 1" if table == "product_version" else None,
        )
        for table, columns in {
            "product_version": ["id", "product_id", "version_number", "product_page_url"],
            "creative_task": ["id", "user_id", "product_id", "status", "state_version"],
            "creative_record": ["id", "task_id", "kind", "record_key", "content_hash"],
            "creative_command": ["id", "task_id", "command_key", "request_hash"],
        }.items()
    }
    command.upgrade(config, AFTER)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO product_version "
                "(id, product_id, version_number, product_page_url, source_type, request_key, "
                "candidate_names, truth_fields, immutable_fields, allowed_variation, "
                "source_asset_references, license_status, status, created_at) "
                "VALUES (:id, (SELECT product_id FROM product_version LIMIT 1), 2, NULL, "
                "'USER_UPLOAD', 'upload-1', '[]', '{}', '{}', '[]', '[]', 'UNKNOWN', 'DRAFT', :now)"
            ),
            {"id": str(uuid.uuid4()), "now": now},
        )
    yield config, engine, before, version_id, record_id, command_id
    engine.dispose()


def test_upgrade_preserves_old_rows_and_adds_upload_support(migrated_database):
    _, engine, before, _, _, _ = migrated_database
    source_type = engine.connect().execute(
        text("SELECT source_type FROM product_version WHERE version_number = 1")
    ).scalar_one()
    assert source_type == "PRODUCT_PAGE"
    for table, expected in before.items():
        columns = {
            "product_version": ["id", "product_id", "version_number", "product_page_url"],
            "creative_task": ["id", "user_id", "product_id", "status", "state_version"],
            "creative_record": ["id", "task_id", "kind", "record_key", "content_hash"],
            "creative_command": ["id", "task_id", "command_key", "request_hash"],
        }[table]
        assert _facts_hash(
            engine,
            table,
            columns,
            "version_number = 1" if table == "product_version" else None,
        ) == expected
    with pytest.raises((IntegrityError, OperationalError)):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO product_version "
                    "(id, product_id, version_number, product_page_url, source_type, "
                    "request_key, "
                    "candidate_names, truth_fields, immutable_fields, allowed_variation, "
                    "source_asset_references, license_status, status) "
                "VALUES (:id, (SELECT product_id FROM product_version LIMIT 1), 3, NULL, "
                "'USER_UPLOAD', 'upload-1', '[]', '{}', '{}', '[]', '[]', 'UNKNOWN', 'DRAFT')"
                ),
                {"id": str(uuid.uuid4())},
            )


def test_fact_and_history_update_delete_triggers_reject_direct_sql(migrated_database):
    _, engine, _, version_id, record_id, command_id = migrated_database
    with pytest.raises((IntegrityError, OperationalError)):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE product_version SET page_title = 'tampered' WHERE id = :id"),
                {"id": str(version_id)},
            )
    with pytest.raises((IntegrityError, OperationalError)):
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM creative_record WHERE id = :id"), {"id": str(record_id)}
            )
    with pytest.raises((IntegrityError, OperationalError)):
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM product_version WHERE id = :id"), {"id": str(version_id)}
            )


def test_creative_command_delete_trigger_rejects_direct_sql(migrated_database):
    _, engine, _, _, _, command_id = migrated_database
    with pytest.raises((IntegrityError, OperationalError)):
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM creative_command WHERE id = :id"), {"id": str(command_id)}
            )


def test_downgrade_refuses_user_upload_versions(migrated_database):
    config, engine, _, _, _, _ = migrated_database
    with pytest.raises(RuntimeError, match="real URL"):
        command.downgrade(config, BEFORE)
    count = engine.connect().execute(
        text("SELECT COUNT(*) FROM product_version")
    ).scalar_one()
    assert count == 2
