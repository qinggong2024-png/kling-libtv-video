from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_creative_offline_readiness.py"
SPEC = importlib.util.spec_from_file_location("creative_offline_readiness", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
READINESS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = READINESS
SPEC.loader.exec_module(READINESS)

check_creative_modules = READINESS.check_creative_modules
check_frontend_artifacts = READINESS.check_frontend_artifacts
check_migrations = READINESS.check_migrations
migration_graph = READINESS.migration_graph
run_checks = READINESS.run_checks


class CreativeOfflineReadinessTests(unittest.TestCase):
    def test_current_workspace_is_offline_ready(self) -> None:
        results = run_checks(ROOT)
        self.assertTrue(all(result.passed for result in results), results)

    def test_script_prints_ready_and_does_not_read_env(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(ROOT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("OFFLINE_MVP_READY", completed.stdout)
        self.assertNotIn("DATABASE_URL", completed.stdout)
        self.assertNotIn("OPENAI_API_KEY", completed.stdout)

    def test_missing_core_module_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_checks(root)[0]
            self.assertFalse(result.passed)
            self.assertIn("missing", result.detail)

    def test_multiple_heads_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            versions = root / "backend" / "alembic" / "versions"
            versions.mkdir(parents=True)
            (versions / "a.py").write_text(
                "revision = 'a'\ndown_revision = None\n", encoding="utf-8"
            )
            (versions / "b.py").write_text(
                "revision = 'b'\ndown_revision = None\n", encoding="utf-8"
            )
            graph = migration_graph(root)
            self.assertEqual(graph["heads"], ["a", "b"])
            with self.assertRaisesRegex(ValueError, "one head"):
                check_migrations(root)

    def test_migration_graph_parses_without_importing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            versions = root / "backend" / "alembic" / "versions"
            versions.mkdir(parents=True)
            (versions / "a.py").write_text(
                "raise RuntimeError('must not import')\n"
                "revision = 'a'\n"
                "down_revision = None\n",
                encoding="utf-8",
            )
            (versions / "b.py").write_text(
                "revision = 'b'\n"
                "down_revision = 'a'\n"
                "depends_on = ('a',)\n",
                encoding="utf-8",
            )
            self.assertEqual(migration_graph(root)["heads"], ["b"])

    def test_frontend_artifact_check_requires_recognizable_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frontend = root / "frontend"
            (frontend / "dist" / "assets").mkdir(parents=True)
            (frontend / "package.json").write_text(
                '{"scripts": {"build": "vite build"}}', encoding="utf-8"
            )
            (frontend / "package-lock.json").write_text("{}", encoding="utf-8")
            index = frontend / "dist" / "index.html"
            index.write_text("<html><script src='assets/app.js'></script></html>", encoding="utf-8")
            (frontend / "dist" / "assets" / "app.js").write_text("", encoding="utf-8")
            self.assertIn("recognized", check_frontend_artifacts(root))
            index.write_text("<html></html>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "recognizable"):
                check_frontend_artifacts(root)

    def test_current_module_check_does_not_depend_on_env(self) -> None:
        original_read_text = Path.read_text

        def reject_env_read(path: Path, *args: object, **kwargs: object) -> str:
            if path.name == ".env":
                raise AssertionError("the readiness checker must not read .env")
            return original_read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", reject_env_read):
            self.assertTrue(all(result.passed for result in run_checks(ROOT)))


if __name__ == "__main__":
    unittest.main()
