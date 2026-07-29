import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from libtv_agent.app import create_app  # noqa: E402
from libtv_agent.config import Settings  # noqa: E402


def main() -> None:
    app = create_app(
        Settings(
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            _env_file=None,
        )
    )
    # JSON is valid YAML 1.2 and avoids adding a build-only YAML dependency.
    destination = ROOT / "openapi.yaml"
    destination.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
