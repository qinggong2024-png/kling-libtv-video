from pathlib import Path
import contextlib
import threading

from libtv_agent.api_windows_service import (
    _stop_when_requested,
    configure_service_event_loop_policy,
    create_service_uvicorn_server,
    service_settings,
)
from libtv_agent.api_windows_service import configure_service_account, SERVICE_ACCOUNT
from types import SimpleNamespace
from unittest.mock import Mock
import pytest


@pytest.mark.parametrize("running", [False, True])
def test_account_configuration_uses_null_password_and_closes_handles(running):
    api = Mock()
    api.SC_MANAGER_CONNECT = 1
    api.SERVICE_CHANGE_CONFIG = 2
    api.SERVICE_QUERY_STATUS = 4
    api.SERVICE_NO_CHANGE = 0xffffffff
    api.SERVICE_STOPPED = 1
    api.OpenSCManager.return_value = "manager"
    api.OpenService.return_value = "service"
    api.QueryServiceStatus.return_value = (0, 4 if running else 1)
    if running:
        with pytest.raises(RuntimeError, match="Stop"):
            configure_service_account(api)
        api.ChangeServiceConfig.assert_not_called()
    else:
        configure_service_account(api)
        args = api.ChangeServiceConfig.call_args.args
        assert args[8] == SERVICE_ACCOUNT
        assert args[9] is None
    assert [call.args[0] for call in api.CloseServiceHandle.call_args_list] == ["service", "manager"]


def test_api_windows_service_entrypoint_compiles() -> None:
    path = Path(__file__).parents[1] / "src" / "libtv_agent" / "api_windows_service.py"
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_service_contract_declares_query_only_mode() -> None:
    path = Path(__file__).parents[1] / "src" / "libtv_agent" / "api_windows_service.py"
    text = path.read_text(encoding="utf-8")
    assert 'SERVICE_NAME = "LibTVProductionApi"' in text
    assert 'mode": "query-only"' in text


def test_service_configures_thread_safe_windows_event_loop_policy(monkeypatch):
    class FakePolicy:
        pass

    import libtv_agent.api_windows_service as service

    monkeypatch.setattr(service.asyncio, "WindowsSelectorEventLoopPolicy", FakePolicy, raising=False)
    set_policy = Mock()
    monkeypatch.setattr(service.asyncio, "set_event_loop_policy", set_policy)
    configure_service_event_loop_policy()
    set_policy.assert_called_once()
    assert isinstance(set_policy.call_args.args[0], FakePolicy)


async def test_stop_requests_graceful_uvicorn_shutdown():
    from types import SimpleNamespace
    stopping = threading.Event()
    stopping.set()
    server = SimpleNamespace(should_exit=False)
    await _stop_when_requested(server, stopping)
    assert server.should_exit is True


def test_service_server_replaces_uvicorn_signal_capture():
    """The service thread cannot use ``signal.signal``; uvicorn must not try."""

    class SignalHostileServer:
        def __init__(self, config):
            self.config = config

        @contextlib.contextmanager
        def capture_signals(self):
            raise ValueError("signal only works in main thread of the main interpreter")

    uvicorn = SimpleNamespace(Server=SignalHostileServer)
    server = create_service_uvicorn_server(uvicorn, "config")
    assert server.config == "config"
    with server.capture_signals():
        pass


def test_uvicorn_still_exposes_capture_signals():
    """Guard the override against an uvicorn upgrade renaming the hook."""
    import uvicorn

    assert callable(getattr(uvicorn.Server, "capture_signals", None))


def test_settings_force_shared_authentication(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr("libtv_agent.api_windows_service.Settings", lambda **values: SimpleNamespace(**values))
    settings = service_settings(tmp_path)
    assert settings.shared_authentication_enabled is True
    assert settings.app_public_origins == ["http://192.168.30.126:5173"]
