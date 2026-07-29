import argparse
import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from libtv_agent.config import Settings
from libtv_agent.db import Database
from libtv_agent.domain.enums import UserRole
from libtv_agent.domain.models import User
from libtv_agent.services.auth import PasswordService
from sqlalchemy import select


async def create_user(username: str, role: UserRole) -> None:
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("passwords do not match")
    settings = Settings()
    settings.validate_shared_environment()
    database = Database(settings.database_url)
    try:
        async with database.session_factory() as session:
            if await session.scalar(select(User).where(User.username == username)):
                raise SystemExit("username already exists")
            session.add(
                User(
                    username=username,
                    password_hash=PasswordService().hash(password),
                    role=role,
                )
            )
            await session.commit()
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an invited shared-environment user")
    parser.add_argument("username")
    parser.add_argument("--role", choices=[item.value for item in UserRole], default="USER")
    args = parser.parse_args()
    asyncio.run(create_user(args.username, UserRole(args.role)))


if __name__ == "__main__":
    main()
