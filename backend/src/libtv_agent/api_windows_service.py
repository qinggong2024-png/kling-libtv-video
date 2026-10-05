"""Windows Service host for the query-only LibTV API.

The service intentionally uses the maintenance app. It does not run the normal
API launcher, Alembic, or the local Runner, so starting the service cannot
silently resume paid work.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = PROJECT_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from libtv_agent.config import Settings  # noqa: E402
from libtv_agent.maintenance import create_maintenance_app  # noqa: E402
from libtv_agent.logging_config import configure_file_logging  # noqa: E402

SERVICE_NAME = "LibTVProductionApi"
SERVICE_ACCOUNT = rf"NT SERVICE\{SERVICE_NAME}"
API_LOG_PATH = PROJECT_ROOT / "var" / "logs" / "api-service.log"

try:
    import servicemanager
    import win32service
    import win32serviceutil
except ImportError:
    servicemanager = win32service = win32serviceutil = None


def service_settings(data_root: Path) -> Settings:
    return Settings(
        _env_file=data_root / ".env",
        shared_authentication_enabled=True,
        session_cookie_secure=False,
        app_public_origins=["http://192.168.30.126:5173"],
    )


def configure_service_account(api=None) -> None:
    api = api or win32service
    if api is None:
        raise RuntimeError("pywin32 is required")
    manager = api.OpenSCManager(None, None, api.SC_MANAGER_CONNECT)
    try:
        service = api.OpenService(
            manager, SERVICE_NAME, api.SERVICE_CHANGE_CONFIG | api.SERVICE_QUERY_STATUS
        )
        try:
            if api.QueryServiceStatus(service)[1] != api.SERVICE_STOPPED:
                raise RuntimeError("Stop the API service before configuring its account")
            # Virtual service accounts require a NULL password, not an empty string.
            api.ChangeServiceConfig(
                service, api.SERVICE_NO_CHANGE, api.SERVICE_NO_CHANGE,
                api.SERVICE_NO_CHANGE, None, None, 0, None,
                SERVICE_ACCOUNT, None, None,
            )
        finally:
            api.CloseServiceHandle(service)
    finally:
        api.CloseServiceHandle(manager)


def service_preflight() -> dict[str, object]:
    issues: list[str] = []
    if os.name != "nt":
        issues.append("the API service is only supported on Windows")
    try:
        import servicemanager  # noqa: F401
        import win32event  # noqa: F401
        import win32service  # noqa: F401
        import win32serviceutil  # noqa: F401
    except ImportError:
        issues.append("pywin32 is not installed; install the windows-runner extra")
    try:
        data_root = Path(os.environ.get("LIBTV_API_DATA_ROOT", str(PROJECT_ROOT))).resolve()
        if not (data_root / ".env").is_file():
            raise ValueError("explicit production configuration is missing")
        os.chdir(data_root)
        settings = service_settings(data_root)
        settings.validate_shared_environment()
        if not settings.shared_authentication_enabled:
            issues.append("SHARED_AUTHENTICATION_ENABLED must be true")
    except Exception:
        issues.append("API configuration is invalid; inspect configuration locally without sharing secrets")
    return {
        "status": "PASS" if not issues else "BLOCKED",
        "serviceName": SERVICE_NAME,
        "serviceAccount": SERVICE_ACCOUNT,
        "projectRoot": str(PROJECT_ROOT),
        "python": sys.executable,
        "mode": "query-only",
        "issues": issues,
    }


def configure_service_event_loop_policy() -> None:
    """Use a thread-safe Windows loop policy for the pywin32 service thread.

    ``ServiceFramework.SvcDoRun`` is invoked from a worker thread.  Python's
    default Windows Proactor policy attempts to install a signal wakeup fd and
    raises ``ValueError`` outside the main interpreter thread.  The selector
    policy does not use that signal machinery and is sufficient for uvicorn's
    local HTTP listener.
    """
    policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy is not None:
        asyncio.set_event_loop_policy(policy())


if win32serviceutil is not None:
    class ApiService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = "LibTV Production API (Query Only)"
        _svc_description_ = "Hosts the authenticated query-only LibTV API without workers."

        def __init__(self, args: list[str]) -> None:
            super().__init__(args)
            self.stopping = threading.Event()

        def SvcStop(self) -> None:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self.stopping.set()

        def SvcDoRun(self) -> None:
            data_root = Path(win32serviceutil.GetServiceCustomOption(SERVICE_NAME, "DataRoot")).resolve()
            os.chdir(data_root)
            configure_file_logging(
                data_root / "var" / "logs" / "api-service.log",
                failure_reporter=servicemanager.LogErrorMsg,
            )
            servicemanager.LogInfoMsg("LibTV Production API query-only service started")
            try:
                configure_service_event_loop_policy()
                asyncio.run(_serve(self.stopping, service_settings(data_root)))
            finally:
                servicemanager.LogInfoMsg("LibTV Production API query-only service stopped")

def create_service_uvicorn_server(uvicorn, config):
    """Build a uvicorn server that never installs process signal handlers.

    pywin32 imports the service module from the SCM callback thread.  Because
    ``threading`` is first imported there, ``threading.main_thread()`` reports
    that callback thread as the main thread while CPython's own check still
    refuses ``signal.signal``.  uvicorn's ``capture_signals`` trusts
    ``threading`` and therefore dies with ``ValueError: signal only works in
    main thread of the main interpreter``.  A Windows service is stopped
    through the SCM (see ``SvcStop``), so it has no use for process signals.
    """

    class ServiceUvicornServer(uvicorn.Server):
        @contextlib.contextmanager
        def capture_signals(self):
            yield

    return ServiceUvicornServer(config)


async def _serve(stopping: threading.Event, settings: Settings) -> None:
    import uvicorn

    app = create_maintenance_app(settings)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=8000,
        log_config=None,
        access_log=False,
    )
    server = create_service_uvicorn_server(uvicorn, config)
    watcher = asyncio.create_task(_stop_when_requested(server, stopping))
    try:
        await server.serve()
    finally:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher


async def _stop_when_requested(server, stopping: threading.Event) -> None:
    while not stopping.is_set():
        await asyncio.sleep(0.25)
    server.should_exit = True


if __name__ == "__main__":
    if sys.argv[1:] == ["--configure-account"]:
        configure_service_account()
        print("Service account configured: " + SERVICE_ACCOUNT)
        raise SystemExit(0)
    if sys.argv[1:] == ["--preflight"]:
        result = service_preflight()
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0 if result["status"] == "PASS" else 1)
    if win32serviceutil is None:
        raise SystemExit("Install the windows-runner extra before managing the service")
    # pywin32 records the absolute module path when invoked as a script.
    win32serviceutil.HandleCommandLine(ApiService)
