from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory


@pytest.mark.parametrize("start", ["base", "5c8f2a1d9e70"])
def test_phase_capacity_precedes_historical_approval_update(start):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    steps = script._upgrade_revs("head", start)
    steps = script.get_revision("ca01b2c3d405").module.order_upgrade_steps(steps)
    upgrades = [step.revision.revision for step in steps]
    assert script.get_heads() == ["ca01b2c3d406"]
    assert upgrades.index("ca01b2c3d405") < upgrades.index("a6c8e2f4b901")
    if start == "base":
        assert upgrades.index("5c8f2a1d9e70") < upgrades.index("ca01b2c3d405")


def test_existing_head_only_needs_capacity_and_merge():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    upgrades = list(reversed([
        step.revision for step in script.iterate_revisions(
            "head", "c9f0a1b2c3d4", implicit_base=True,
        )
    ]))
    assert upgrades == ["ca01b2c3d405", "ca01b2c3d406"]
