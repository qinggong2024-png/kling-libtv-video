from pathlib import Path
import threading

from libtv_agent.api_windows_service import _stop_when_requested, service_settings
from libtv_agent.api_windows_service import configure_service_account, SERVICE_ACCOUNT
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


async def test_stop_requests_graceful_uvicorn_shutdown():
    from types import SimpleNamespace
    stopping = threading.Event()
    stopping.set()
    server = SimpleNamespace(should_exit=False)
    await _stop_when_requested(server, stopping)
    assert server.should_exit is True


def test_settings_force_shared_authentication(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr("libtv_agent.api_windows_service.Settings", lambda **values: SimpleNamespace(**values))
    settings = service_settings(tmp_path)
    assert settings.shared_authentication_enabled is True
    assert settings.app_public_origins == ["http://192.168.30.126:5173"]
