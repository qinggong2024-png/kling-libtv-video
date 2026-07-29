from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_readiness_uses_machine_reports_without_manual_test_count_parameters() -> None:
    script = (ROOT / "scripts" / "write-phase2-readiness-report.ps1").read_text(encoding="utf-8")

    assert "BackendPassed" not in script
    assert "BackendSkipped" not in script
    assert "phase2-machine-evidence.json" in script
    assert "git config --get user.name" in script
    assert "git diff --cached --name-only" in script
    assert "continuousRunHours" in script
    assert "machineEvidencePassed" in script
    assert "onlyResolvedOnlineSkips" in script
    assert "requiredAuthorizationFields" in script


def test_backup_and_restore_drill_enforce_isolation_and_no_paid_adapter() -> None:
    backup = (ROOT / "scripts" / "backup.ps1").read_text(encoding="utf-8")
    restore = (ROOT / "scripts" / "restore-drill.ps1").read_text(encoding="utf-8")

    assert "pg_dump --format=custom" in backup
    assert "mc mirror" in backup
    assert "Get-FileHash -Algorithm SHA256" in backup
    assert "libtv-restore-drill-" in restore
    assert "$env:LIBTV_ADAPTER_MODE = 'fake'" in restore
    assert "$env:AI_ADAPTER_MODE = 'fake'" in restore
    assert "$env:PAID_SUBMISSIONS_PAUSED = 'true'" in restore
    assert "paidOperationsExecuted = $false" in restore


def test_check_report_is_junit_driven_and_runs_all_steps() -> None:
    script = (ROOT / "scripts" / "check.ps1").read_text(encoding="utf-8")

    assert "--junitxml" in script
    assert "PASS_WITH_SKIPS" in script
    assert "backendRuffLint" in script
    assert "backendRuffFormat" in script
    assert "frontendLint" in script
    assert "frontendBuild" in script
    assert "alembicOfflineSql" in script
    assert "skippedTests" in script
