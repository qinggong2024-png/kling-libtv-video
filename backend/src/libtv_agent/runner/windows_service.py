import asyncio
import json
import os
import shutil
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_SRC = PROJECT_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from libtv_agent.config import Settings  # noqa: E402
from libtv_agent.logging_config import configure_file_logging  # noqa: E402

SERVICE_NAME = "LibTVProductionRunner"
SERVICE_ACCOUNT = rf"NT SERVICE\{SERVICE_NAME}"
RUNNER_LOG_NAME = "runner.log"

try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
except ImportError:
    servicemanager = win32event = win32service = win32serviceutil = None


def service_preflight() -> dict[str, object]:
    issues: list[str] = []
    try:
        import servicemanager  # noqa: F401
        import win32event  # noqa: F401
        import win32service  # noqa: F401
        import win32serviceutil  # noqa: F401
    except ImportError:
        issues.append("pywin32 is not installed; install the windows-runner extra")

    try:
        settings = Settings()
        settings.validate_shared_environment()
    except Exception as exc:
        issues.append(f"runner configuration is invalid: {exc}")
        settings = None

    libtv_executable = settings.libtv_executable if settings else "libtv"
    if shutil.which(libtv_executable) is None:
        issues.append(f"LibTV executable is unavailable: {libtv_executable}")
    if shutil.which("ffprobe") is None:
        issues.append("ffprobe is unavailable")

    return {
        "status": "PASS" if not issues else "BLOCKED",
        "serviceName": SERVICE_NAME,
        "serviceAccount": SERVICE_ACCOUNT,
        "projectRoot": str(PROJECT_ROOT),
        "python": sys.executable,
        "issues": issues,
    }


def service_data_root() -> Path:
    if win32serviceutil is None:
        raise RuntimeError("pywin32 is required")
    return Path(
        win32serviceutil.GetServiceCustomOption(SERVICE_NAME, "DataRoot")
    ).resolve()


if win32serviceutil is not None:
    class RunnerService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = "LibTV Production Runner"
        _svc_description_ = "Supervises durable LibTV command-host processes."

        def __init__(self, args: list[str]) -> None:
            super().__init__(args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            self.stopping = threading.Event()

        def SvcStop(self) -> None:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self.stopping.set()
            win32event.SetEvent(self.stop_event)

        def SvcDoRun(self) -> None:
            data_root = service_data_root()
            if not (data_root / ".env").is_file():
                raise RuntimeError(f"production configuration is missing: {data_root / '.env'}")
            os.chdir(data_root)
            servicemanager.LogInfoMsg("LibTV Production Runner started")
            # The Windows service has no console at all, so a file log is the
            # only place its failures can surface.
            configure_file_logging(
                data_root / "var" / "logs" / RUNNER_LOG_NAME,
                failure_reporter=servicemanager.LogErrorMsg,
            )
            try:
                from libtv_agent.runner.service_runtime import run_service_loop

                asyncio.run(run_service_loop(self.stopping, PROJECT_ROOT, data_root))
            finally:
                servicemanager.LogInfoMsg("LibTV Production Runner stopped")


def run_service() -> None:
    if win32serviceutil is None:
        raise RuntimeError(
            "Install the windows-runner extra to manage the Windows Service"
        )
    win32serviceutil.HandleCommandLine(RunnerService)


if __name__ == "__main__":
    if sys.argv[1:] == ["--preflight"]:
        result = service_preflight()
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0 if result["status"] == "PASS" else 1)
    run_service()
