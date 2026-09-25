from pathlib import Path
import threading

from libtv_agent.api_windows_service import _stop_when_requested, service_settings


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
