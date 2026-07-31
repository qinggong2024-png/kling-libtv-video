import uuid
from pathlib import Path

import pytest
from libtv_agent.db import Database
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.models import Base, User


@pytest.mark.asyncio
async def test_sqlite_database_supports_model_now_defaults(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    user = User(
        id=uuid.uuid4(),
        username="fresh-test-user",
        password_hash="offline-disabled",
        role=UserRole.ADMIN,
    )
    async with database.session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    assert user.created_at is not None
    await database.dispose()
