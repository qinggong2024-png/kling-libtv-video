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
BASELINE = "d1e2f3a4b506"
REPAIR = "d2f3a4b5c607"


def _config(database: Path) -> Config:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database.as_posix()}"
    os.environ["APP_ENV"] = "test"
    from libtv_agent.config import get_settings

    get_settings.cache_clear()
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    return config


def _hash(engine, table: str, columns: list[str], where: str | None = None) -> str:
    suffix = f" WHERE {where}" if where else ""
    rows = engine.connect().execute(
        text(f"SELECT {', '.join(columns)} FROM {table}{suffix} ORDER BY 1")
    ).mappings()
    payload = [dict(row) for row in rows]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _seed(config: Config, database: Path, *, upload: bool = True):
    command.upgrade(config, BASELINE)
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    now = datetime.now(UTC).isoformat()
    ids = {name: uuid.uuid4() for name in (
        "user", "product", "version", "task", "record", "command", "prompt", "creation"
    )}
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO app_user "
                "(id, username, password_hash, role, is_active, created_at) "
                "VALUES (:id, :username, 'test-only', 'USER', 1, :now)"
            ),
            {"id": str(ids["user"]), "username": f"repair-{ids['user']}", "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO product "
                "(id, user_id, internal_sku_id, created_at, updated_at) "
                "VALUES (:id, :user_id, 'CW-REPAIR', :now, :now)"
            ),
            {"id": str(ids["product"]), "user_id": str(ids["user"]), "now": now},
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
                "id": str(ids["version"]),
                "product_id": str(ids["product"]),
                "url": "https://example.invalid/old-product",
                "now": now,
            },
        )
        connection.execute(
            text(
                "INSERT INTO creative_task "
                "(id, user_id, product_id, status, state_version, snapshot_json) "
                "VALUES (:id, :user_id, :product_id, 'PLANNED', 1, '{}')"
            ),
            {
                "id": str(ids["task"]),
                "user_id": str(ids["user"]),
                "product_id": str(ids["product"]),
            },
        )
        connection.execute(
            text(
                "INSERT INTO creative_record "
                "(id, task_id, kind, record_key, content_hash, payload_json) "
                "VALUES (:id, :task_id, 'HISTORY', 'old-1', :hash, '{}')"
            ),
            {"id": str(ids["record"]), "task_id": str(ids["task"]), "hash": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO creative_command "
                "(id, task_id, command_key, request_hash, result_json) "
                "VALUES (:id, :task_id, 'old-command', :hash, '{}')"
            ),
            {"id": str(ids["command"]), "task_id": str(ids["task"]), "hash": "b" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO creative_prompt_registry "
                "(id, prompt_key, version, content_hash, payload_json) "
                "VALUES (:id, 'old-prompt', 1, :hash, '{}')"
            ),
            {"id": str(ids["prompt"]), "hash": "c" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO creative_creation "
                "(id, user_id, client_key, task_id, request_hash, result_json) "
                "VALUES (:id, :user_id, 'old-creation', :task_id, :hash, '{}')"
            ),
            {
                "id": str(ids["creation"]),
                "user_id": str(ids["user"]),
                "task_id": str(ids["task"]),
                "hash": "d" * 64,
            },
        )
        if upload:
            connection.execute(
                text(
                    "INSERT INTO product_version "
                    "(id, product_id, version_number, product_page_url, source_type, "
                    "request_key, candidate_names, truth_fields, immutable_fields, "
                    "allowed_variation, source_asset_references, license_status, status, "
                    "created_at) VALUES (:id, :product_id, 2, NULL, 'USER_UPLOAD', "
                    "'upload-1', '[]', '{}', '{}', '[]', '[]', 'UNKNOWN', 'DRAFT', :now)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "product_id": str(ids["product"]),
                    "now": now,
                },
            )
    before = {
        "product_version": _hash(
            engine,
            "product_version",
            ["id", "product_id", "version_number", "product_page_url"],
            "version_number = 1",
        ),
        "creative_record": _hash(
            engine, "creative_record", ["id", "task_id", "record_key", "content_hash"]
        ),
        "creative_command": _hash(
            engine, "creative_command", ["id", "task_id", "command_key", "request_hash"]
        ),
    }
    return engine, ids, before


@pytest.fixture
def repaired_database(tmp_path: Path):
    database = tmp_path / "repair.db"
    config = _config(database)
    engine, ids, before = _seed(config, database)
    command.upgrade(config, REPAIR)
    yield config, engine, ids, before
    engine.dispose()


def _assert_rejected(engine, statement: str, params: dict[str, str]) -> None:
    with pytest.raises((IntegrityError, OperationalError)):
        with engine.begin() as connection:
            connection.execute(text(statement), params)


def test_d2_rejects_fact_delete_and_command_update_delete_without_regression(
    repaired_database,
):
    _, engine, ids, before = repaired_database
    _assert_rejected(
        engine,
        "UPDATE product_version SET page_title = 'tampered' WHERE id = :id",
        {"id": str(ids["version"])},
    )
    _assert_rejected(
        engine,
        "DELETE FROM product_version WHERE id = :id",
        {"id": str(ids["version"])},
    )
    _assert_rejected(
        engine,
        "UPDATE creative_command SET request_hash = :hash WHERE id = :id",
        {"id": str(ids["command"]), "hash": "e" * 64},
    )
    _assert_rejected(
        engine,
        "DELETE FROM creative_command WHERE id = :id",
        {"id": str(ids["command"])},
    )
    for table, expected in before.items():
        columns = {
            "product_version": ["id", "product_id", "version_number", "product_page_url"],
            "creative_record": ["id", "task_id", "record_key", "content_hash"],
            "creative_command": ["id", "task_id", "command_key", "request_hash"],
        }[table]
        where = "version_number = 1" if table == "product_version" else None
        assert _hash(engine, table, columns, where) == expected
    for _table, statement, params in (
        (
            "creative_record",
            "UPDATE creative_record SET content_hash = :hash WHERE id = :id",
            {"id": str(ids["record"]), "hash": "f" * 64},
        ),
        (
            "creative_record",
            "DELETE FROM creative_record WHERE id = :id",
            {"id": str(ids["record"])},
        ),
        (
            "creative_prompt_registry",
            "UPDATE creative_prompt_registry SET content_hash = :hash WHERE id = :id",
            {"id": str(ids["prompt"]), "hash": "f" * 64},
        ),
        (
            "creative_prompt_registry",
            "DELETE FROM creative_prompt_registry WHERE id = :id",
            {"id": str(ids["prompt"])},
        ),
        (
            "creative_creation",
            "UPDATE creative_creation SET request_hash = :hash WHERE id = :id",
            {"id": str(ids["creation"]), "hash": "f" * 64},
        ),
        (
            "creative_creation",
            "DELETE FROM creative_creation WHERE id = :id",
            {"id": str(ids["creation"])},
        ),
    ):
        _assert_rejected(engine, statement, params)


def test_user_upload_null_url_and_request_key_remain_supported(repaired_database):
    _, engine, _, _ = repaired_database
    assert engine.connect().execute(
        text(
            "SELECT COUNT(*) FROM product_version "
            "WHERE source_type = 'USER_UPLOAD' AND product_page_url IS NULL"
        )
    ).scalar_one() == 1
    with pytest.raises((IntegrityError, OperationalError)):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO product_version "
                    "(id, product_id, version_number, product_page_url, source_type, "
                    "request_key, candidate_names, truth_fields, immutable_fields, "
                    "allowed_variation, source_asset_references, license_status, status) "
                    "VALUES (:id, (SELECT product_id FROM product_version LIMIT 1), 3, "
                    "NULL, 'USER_UPLOAD', 'upload-1', '[]', '{}', '{}', '[]', '[]', "
                    "'UNKNOWN', 'DRAFT')"
                ),
                {"id": str(uuid.uuid4())},
            )


def test_downgrade_removes_only_d2_triggers_and_keeps_d1_protection(tmp_path: Path):
    database = tmp_path / "downgrade.db"
    config = _config(database)
    engine, ids, _ = _seed(config, database, upload=False)
    command.upgrade(config, REPAIR)
    command.downgrade(config, BASELINE)
    _assert_rejected(
        engine,
        "UPDATE product_version SET page_title = 'tampered' WHERE id = :id",
        {"id": str(ids["version"])},
    )
    for statement, params in (
        (
            "UPDATE creative_record SET content_hash = :hash WHERE id = :id",
            {"id": str(ids["record"]), "hash": "f" * 64},
        ),
        (
            "DELETE FROM creative_record WHERE id = :id",
            {"id": str(ids["record"])},
        ),
        (
            "UPDATE creative_prompt_registry SET content_hash = :hash WHERE id = :id",
            {"id": str(ids["prompt"]), "hash": "f" * 64},
        ),
        (
            "DELETE FROM creative_prompt_registry WHERE id = :id",
            {"id": str(ids["prompt"])},
        ),
        (
            "UPDATE creative_creation SET request_hash = :hash WHERE id = :id",
            {"id": str(ids["creation"]), "hash": "f" * 64},
        ),
        (
            "DELETE FROM creative_creation WHERE id = :id",
            {"id": str(ids["creation"])},
        ),
    ):
        _assert_rejected(engine, statement, params)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE creative_command SET request_hash = :hash WHERE id = :id"),
            {"id": str(ids["command"]), "hash": "f" * 64},
        )
        connection.execute(
            text("DELETE FROM creative_command WHERE id = :id"),
            {"id": str(ids["command"])},
        )
        connection.execute(
            text("DELETE FROM product_version WHERE id = :id"),
            {"id": str(ids["version"])},
        )
    engine.dispose()
