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


def test_alembic_revision_identity_ignores_mergepoint_annotation() -> None:
    helper = SCRIPTS / "local-instance-identity.ps1"
    command = (
        f". '{helper}'; "
        "$current = @(Get-AlembicRevisionIds "
        "-Output @('f2b6d8a13c47 (head) (mergepoint)')); "
        "$expected = @(Get-AlembicRevisionIds "
        "-Output @('f2b6d8a13c47 (head)')); "
        "[pscustomobject]@{ "
        "current = ($current -join ','); "
        "expected = ($expected -join ',') "
        "} | ConvertTo-Json -Compress"
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

    assert json.loads(completed.stdout) == {
        "current": "f2b6d8a13c47",
        "expected": "f2b6d8a13c47",
    }


def test_local_startup_scripts_require_workspace_owned_ports() -> None:
    for name in ("start-local-api.ps1", "start-local-frontend.ps1", "start-local-stack.ps1"):
        source = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "local-instance-identity.ps1" in source
        assert "Assert-WorkspacePortOwnership" in source

    check_source = (SCRIPTS / "check-local-services.ps1").read_text(encoding="utf-8")
    assert "Get-WorkspacePortIdentity" in check_source
    assert "workspaceOwned" in check_source


def test_source_revision_is_stable_and_changes_with_backend_content(tmp_path: Path) -> None:
    helper = SCRIPTS / "local-instance-identity.ps1"
    (tmp_path / "backend/src").mkdir(parents=True)
    (tmp_path / "backend/alembic/versions").mkdir(parents=True)
    (tmp_path / "backend/src/app.py").write_text("first", encoding="utf-8")
    (tmp_path / "backend/alembic/versions/001.py").write_text("migration", encoding="utf-8")
    (tmp_path / "backend/alembic.ini").write_text("alembic", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("project", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("lock", encoding="utf-8")

    def revision() -> str:
        command = f". '{helper}'; Get-WorkspaceSourceRevision -ProjectRoot '{tmp_path}'"
        return subprocess.run(
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
            encoding="utf-8",
            errors="replace",
        ).stdout.strip()

    initial = revision()
    assert len(initial) == 64
    assert revision() == initial
    (tmp_path / "backend/src/app.py").write_text("second", encoding="utf-8")
    assert revision() != initial


def test_watchdog_requires_api_source_revision_match() -> None:
    for name in ("start-local-api.ps1", "start-local-stack.ps1", "watch-local-stack.ps1"):
        source = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "Get-WorkspaceSourceRevision" in source
        assert "sourceRevision" in source

    check_source = (SCRIPTS / "check-local-services.ps1").read_text(encoding="utf-8")
    assert "apiSourceRevision" in check_source
    assert "expectedSourceRevision" in check_source


def test_api_restart_only_cleans_runner_coupled_by_process_tree() -> None:
    source = (SCRIPTS / "start-local-api.ps1").read_text(encoding="utf-8")
    assert "Get-ProcessAncestorIds" in source
    assert "coupledRunnerIds" in source
    assert "$apiWrapperIds -contains" in source
    assert "$ancestor.CommandLine.Contains($PSCommandPath)" in source
