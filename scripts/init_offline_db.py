"""Create an empty SQLite database for Fake/Replay UI validation only."""

import argparse
import asyncio
from pathlib import Path

from libtv_agent.db import Database
from libtv_agent.domain.models import Base


async def initialize(database_url: str) -> None:
    database = Database(database_url)
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.path.exists():
        raise SystemExit(f"refusing to overwrite existing database: {args.path}")
    args.path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite+aiosqlite:///{args.path.resolve().as_posix()}"
    asyncio.run(initialize(database_url))


if __name__ == "__main__":
    main()
