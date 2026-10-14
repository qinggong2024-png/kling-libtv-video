from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from libtv_agent.config import Settings

PAID_GENERATION_CONFIRMATION = "I_ACCEPT_LIBTV_POINT_CHARGES"


class PaidGenerationBlockedError(RuntimeError):
    code = "PAID_GENERATION_BLOCKED"


def paid_generation_authorized(settings: Settings) -> bool:
    return (
        settings.app_env != "test"
        and settings.libtv_execution_mode == "live"
        and settings.paid_generation_enabled
        and settings.paid_generation_confirmation == PAID_GENERATION_CONFIRMATION
    )


def real_provider_submission_authorized(settings: Settings) -> bool:
    """Real providers never inherit the unrelated LibTV synthetic adapter exemption."""
    return paid_generation_authorized(settings)


def require_paid_generation_authorized(settings: Settings) -> None:
    if paid_generation_authorized(settings):
        return
    raise PaidGenerationBlockedError(
        "paid LibTV generation is blocked; live mode, the explicit enable switch, "
        "and the exact confirmation phrase are all required"
    )


def build_generation_command(executable: str, project_uuid: str, node_key: str) -> list[str]:
    return [executable, "node", node_key, "--project", project_uuid, "--run"]


def build_generation_preview(
    *,
    executable: str,
    project_uuid: str,
    node_key: str,
    params: dict[str, Any] | None = None,
    prompt_hash: str | None = None,
    execution_mode: str,
    authorized: bool,
) -> dict[str, Any]:
    command = build_generation_command(executable, project_uuid, node_key)
    summary_keys = (
        "model",
        "modelKey",
        "modeType",
        "duration",
        "aspectRatio",
        "ratio",
        "quality",
        "sound",
        "enableSound",
        "smartStoryboard",
        "quantity",
        "count",
    )
    source = params or {}
    return {
        "paidBoundary": "libtv node <nodeKey> --project <projectUuid> --run",
        "argv": command,
        "windowsCommandLine": subprocess.list2cmdline(command),
        "projectUuid": project_uuid,
        "nodeKey": node_key,
        "parameterSummary": {key: source[key] for key in summary_keys if key in source},
        "promptHash": prompt_hash,
        "estimatedGenerationCount": 1,
        "executionMode": execution_mode,
        "authorized": authorized,
        "costRisk": "Executing this command may consume LibTV points.",
    }


def write_preview_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary.replace(path)
