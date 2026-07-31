from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
        if self.engine.dialect.name == "sqlite":
            # SQLite does not provide the SQL `now()` function used by the
            # model server defaults. Register it on every pooled connection.
            @event.listens_for(self.engine.sync_engine, "connect")
            def register_sqlite_functions(dbapi_connection, _connection_record) -> None:
                dbapi_connection.create_function(
                    "now",
                    0,
                    lambda: datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                )

        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    database: Database = request.app.state.database
    async with database.session_factory() as session:
        yield session
