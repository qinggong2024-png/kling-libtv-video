import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def test_workspace_process_identity_distinguishes_sibling_repository() -> None:
    helper = SCRIPTS / "local-instance-identity.ps1"
    command = (
        f". '{helper}'; "
        f"$root = '{ROOT}'; "
        "$same = Test-WorkspaceProcessIdentity "
        f"-CommandLine ('node ' + '{ROOT}' + '\\frontend\\node_modules\\vite\\bin\\vite.js') "
        "-ExecutablePath 'C:\\Program Files\\nodejs\\node.exe' -ProjectRoot $root; "
        "$sibling = Test-WorkspaceProcessIdentity "
        "-CommandLine 'node C:\\other\\repo\\frontend\\node_modules\\vite\\bin\\vite.js' "
        "-ExecutablePath 'C:\\Program Files\\nodejs\\node.exe' -ProjectRoot $root; "
        "[pscustomobject]@{ same = $same; sibling = $sibling } | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {"same": True, "sibling": False}


def test_local_startup_scripts_require_workspace_owned_ports() -> None:
    for name in ("start-local-api.ps1", "start-local-frontend.ps1", "start-local-stack.ps1"):
        source = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "local-instance-identity.ps1" in source
        assert "Assert-WorkspacePortOwnership" in source

    check_source = (SCRIPTS / "check-local-services.ps1").read_text(encoding="utf-8")
    assert "Get-WorkspacePortIdentity" in check_source
    assert "workspaceOwned" in check_source
