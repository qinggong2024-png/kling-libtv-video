import argparse
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


def main(data_root: Path | None = None) -> None:
    # This process is started in a hidden window with no output redirection, so
    # without a file handler its exceptions go nowhere at all. The service loop
    # wraps every cycle in logger.exception(); that traceback is the only way to
    # find out why generation stalled.
    runtime_root = data_root.resolve() if data_root else PROJECT_ROOT
    configure_file_logging(runtime_root / "logs" / "runner.log" if data_root else RUNNER_LOG_PATH)

    stopping = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_stop)
    asyncio.run(run_service_loop(stopping, PROJECT_ROOT, runtime_root))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the existing local worker loop")
    parser.add_argument("--data-root", type=Path)
    main(parser.parse_args().data_root)
