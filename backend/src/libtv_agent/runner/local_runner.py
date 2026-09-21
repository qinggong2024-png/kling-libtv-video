import asyncio
import signal
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_SRC = PROJECT_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from libtv_agent.logging_config import configure_file_logging  # noqa: E402
from libtv_agent.runner.service_runtime import run_service_loop  # noqa: E402

RUNNER_LOG_PATH = PROJECT_ROOT / "var" / "logs" / "runner.log"


def main() -> None:
    # This process is started in a hidden window with no output redirection, so
    # without a file handler its exceptions go nowhere at all. The service loop
    # wraps every cycle in logger.exception(); that traceback is the only way to
    # find out why generation stalled.
    configure_file_logging(RUNNER_LOG_PATH)

    stopping = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_stop)
    asyncio.run(run_service_loop(stopping, PROJECT_ROOT))


if __name__ == "__main__":
    main()
