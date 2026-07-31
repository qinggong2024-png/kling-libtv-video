"""Seed the first editable prompt preset for every workflow.

Revision ID: b6f4d2a9c801
Revises: a4d7c2e9f610
Create Date: 2026-07-31
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from libtv_agent.services.prompt_presets import DEFAULT_PROMPT_PRESET_SPECS

revision: str = "b6f4d2a9c801"
down_revision: str | Sequence[str] | None = "a4d7c2e9f610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    users = sa.table("app_user", sa.column("id", sa.Uuid()))
    presets = sa.table(
        "prompt_preset",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("scope", sa.String()),
        sa.column("name", sa.String()),
        sa.column("content", sa.Text()),
        sa.column("sort_order", sa.Integer()),
    )

    if context.is_offline_mode():
        for scope, name, content in DEFAULT_PROMPT_PRESET_SPECS:
            deterministic_id = sa.cast(
                sa.func.md5(
                    sa.cast(users.c.id, sa.String()) + sa.literal(f":prompt-preset:{scope}:{name}")
                ),
                sa.Uuid(),
            )
            missing = ~sa.exists(
                sa.select(1)
                .select_from(presets)
                .where(
                    presets.c.user_id == users.c.id,
                    presets.c.scope == scope,
                    presets.c.name == name,
                )
            )
            op.execute(
                presets.insert().from_select(
                    ["id", "user_id", "scope", "name", "content", "sort_order"],
                    sa.select(
                        deterministic_id,
                        users.c.id,
                        sa.literal(scope),
                        sa.literal(name),
                        sa.literal(content),
                        sa.literal(0),
                    ).where(missing),
                )
            )
        return

    connection = op.get_bind()
    user_ids = list(connection.execute(sa.select(users.c.id)).scalars())
    for user_id in user_ids:
        for scope, name, content in DEFAULT_PROMPT_PRESET_SPECS:
            exists = connection.scalar(
                sa.select(presets.c.id).where(
                    presets.c.user_id == user_id,
                    presets.c.scope == scope,
                    presets.c.name == name,
                )
            )
            if exists is None:
                connection.execute(
                    presets.update()
                    .where(
                        presets.c.user_id == user_id,
                        presets.c.scope == scope,
                    )
                    .values(sort_order=presets.c.sort_order + 1)
                )
                connection.execute(
                    presets.insert().values(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        scope=scope,
                        name=name,
                        content=content,
                        sort_order=0,
                    )
                )


def downgrade() -> None:
    # These rows are user-editable after creation, so a downgrade must not
    # guess which current values are still safe to delete.
    pass
