import json
from pathlib import Path

from libtv_agent.app import create_app
from libtv_agent.config import Settings
from libtv_agent.domain.enums import AttemptStatus, ParentTaskPhase
from libtv_agent.services.state_machine import load_state_machines

ROOT = Path(__file__).parents[2]


def test_machine_contract_matches_enums() -> None:
    machines = load_state_machines()
    assert set(machines["parentTask"]["transitions"]) == {value.value for value in ParentTaskPhase}
    assert set(machines["generationAttempt"]["transitions"]) == {
        value.value for value in AttemptStatus
    }


def test_openapi_artifact_matches_application_routes() -> None:
    committed = json.loads((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
    current = create_app(
        Settings(
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            _env_file=None,
        )
    ).openapi()
    assert committed == current
    required_paths = {
        "/api/v1/uploads",
        "/api/v1/tasks",
        "/api/v1/tasks/{task_id}/analyze",
        "/api/v1/tasks/{task_id}/confirm",
        "/api/v1/tasks/{task_id}/restore-remote-output",
        "/api/v1/tasks/{task_id}/variants/{variant_id}/feedback",
        "/api/v1/confirmations/execute",
        "/api/v1/downloads/{artifact_id}",
        "/api/v1/admin/reconciliations",
    }
    assert required_paths <= committed["paths"].keys()
