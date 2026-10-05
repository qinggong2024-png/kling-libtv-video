import asyncio
import json
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
from libtv_agent.runner.service_runtime import run_service_loop  # noqa: E402

SERVICE_NAME = "LibTVProductionRunner"
SERVICE_ACCOUNT = rf"NT SERVICE\{SERVICE_NAME}"
RUNNER_LOG_PATH = PROJECT_ROOT / "var" / "logs" / "runner.log"


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


def run_service() -> None:
    try:
        import servicemanager
        import win32event
        import win32service
        import win32serviceutil
    except ImportError as exc:
        raise RuntimeError(
            "Install the windows-runner extra to manage the Windows Service"
        ) from exc

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
            servicemanager.LogInfoMsg("LibTV Production Runner started")
            # The Windows service has no console at all, so a file log is the
            # only place its failures can surface.
            configure_file_logging(
                RUNNER_LOG_PATH,
                failure_reporter=servicemanager.LogErrorMsg,
            )
            try:
                asyncio.run(run_service_loop(self.stopping, PROJECT_ROOT))
            finally:
                servicemanager.LogInfoMsg("LibTV Production Runner stopped")

    win32serviceutil.HandleCommandLine(RunnerService)


if __name__ == "__main__":
    if sys.argv[1:] == ["--preflight"]:
        result = service_preflight()
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0 if result["status"] == "PASS" else 1)
    run_service()
