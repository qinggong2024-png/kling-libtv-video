from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest


def _load_acceptance_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "acceptance_libtv.py"
    spec = importlib.util.spec_from_file_location("acceptance_libtv", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("execute_paid", "confirmation"),
    [
        (False, ""),
        (True, "wrong-confirmation"),
    ],
)
async def test_paid_execution_rejects_incomplete_confirmation_before_app_start(
    monkeypatch: pytest.MonkeyPatch,
    execute_paid: bool,
    confirmation: str,
) -> None:
    module = _load_acceptance_module()
    monkeypatch.setattr(
        module,
        "create_app",
        lambda _settings: pytest.fail("application must not start before paid confirmation"),
    )
    args = argparse.Namespace(set_id="1", execute_paid=execute_paid, confirmation=confirmation)

    with pytest.raises(ValueError, match="exact confirmation phrase"):
        await module.execute(args)


def test_acceptance_lock_rejects_a_second_process(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_acceptance_module()
    monkeypatch.setattr(module, "_try_lock", lambda _handle: (_ for _ in ()).throw(OSError()))

    with pytest.raises(RuntimeError, match="another LibTV acceptance process is active"):
        with module._exclusive_acceptance_lock():
            pytest.fail("locked acceptance body must not run")


def test_acceptance_lock_is_exclusive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_acceptance_module()
    monkeypatch.setattr(module, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(module, "LOCK_PATH", tmp_path / "operation.lock")

    with module._exclusive_acceptance_lock():
        with pytest.raises(RuntimeError, match="another LibTV acceptance process is active"):
            with module._exclusive_acceptance_lock():
                pytest.fail("a second acceptance process must not acquire the lock")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "message"),
    [
        ({"paidTestsUsed": 0, "sets": {}}, "has not completed prepare-only"),
        (
            {"paidTestsUsed": 1, "sets": {"1": {"paidExecutionStarted": True}}},
            "already consumed",
        ),
        (
            {"paidTestsUsed": 2, "sets": {"1": {"paidExecutionStarted": False}}},
            "budget is exhausted",
        ),
    ],
)
async def test_paid_budget_guards_fail_before_app_start(
    monkeypatch: pytest.MonkeyPatch,
    state: dict[str, object],
    message: str,
) -> None:
    module = _load_acceptance_module()

    async def read_state() -> dict[str, object]:
        return state

    monkeypatch.setattr(module, "_read_state", read_state)
    monkeypatch.setattr(
        module,
        "create_app",
        lambda _settings: pytest.fail("application must not start after a budget rejection"),
    )
    args = argparse.Namespace(
        set_id="1",
        execute_paid=True,
        confirmation=module.PAID_GENERATION_CONFIRMATION,
    )

    with pytest.raises(ValueError, match=message):
        await module.execute(args)


def test_prepare_and_live_settings_keep_paid_boundary_explicit() -> None:
    module = _load_acceptance_module()

    prepare_settings = module._settings(live=False, set_id="1")
    assert prepare_settings.libtv_execution_mode == "prepare-only"
    assert prepare_settings.paid_generation_enabled is False
    assert prepare_settings.paid_submissions_paused is True

    live_settings = module._settings(live=True, set_id="1")
    assert live_settings.libtv_execution_mode == "live"
    assert live_settings.paid_generation_enabled is True
    assert live_settings.paid_generation_confirmation == module.PAID_GENERATION_CONFIRMATION
    assert live_settings.paid_submissions_paused is False
