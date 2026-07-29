import asyncio

from libtv_agent.config import get_settings
from libtv_agent.domain.models import Base
from sqlalchemy.ext.asyncio import create_async_engine


async def initialize() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(initialize())
