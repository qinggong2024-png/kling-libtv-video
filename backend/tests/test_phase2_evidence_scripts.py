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
    assert "alembicFreshSqlite" in script
    assert "skippedTests" in script


def test_test_stack_forces_offline_provider_modes() -> None:
    script = (ROOT / "scripts" / "start-test-stack.ps1").read_text(encoding="utf-8")

    required_assignments = {
        "$env:AI_ADAPTER_MODE = 'fake'",
        "$env:LIBTV_ADAPTER_MODE = 'fake'",
        "$env:LIBTV_EXECUTION_MODE = 'dry-run'",
        "$env:PAID_GENERATION_ENABLED = 'false'",
        "$env:PAID_SUBMISSIONS_PAUSED = 'true'",
        "$env:KLING_CLI_ENABLED = 'false'",
        "$env:KLING_API_ENABLED = 'false'",
        "$env:KLING_ADMIN_CONFIG_FILE = Join-Path $runtimeRoot 'kling-config.json'",
        "$env:KLING_API_ENABLE_PAID_INTEGRATION_TEST = 'false'",
        "$env:WAVESPEED_ENABLED = 'false'",
    }
    assert required_assignments <= set(script.splitlines())
    # The launcher hands Start-Process a single command-line string with the redirects
    # embedded, because `-RedirectStandardOutput`/`-RedirectStandardError` trip a
    # duplicate-environment-variable bug on this machine. The app directory is therefore
    # interpolated with -f instead of being passed as a positional '-ArgumentList' pair.
    # The invariant being guarded — uvicorn is pointed at $appDir — is unchanged.
    assert '--app-dir "{1}"' in script
    assert "-f $python, $appDir," in script


def test_local_frontend_is_loopback_by_default_and_lan_is_explicit() -> None:
    vite_config = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    lan_script = (ROOT / "scripts" / "start-lan-stack.ps1").read_text(encoding="utf-8")

    assert "env.VITE_HOST || '127.0.0.1'" in vite_config
    assert "$env:VITE_HOST = '0.0.0.0'" in lan_script
