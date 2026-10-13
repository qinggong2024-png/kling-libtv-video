"""Read-only readiness checks for the offline Creative Workflow MVP.

This module deliberately inspects source and build artifacts without importing
the application, reading ``.env``, starting a service, calling a Provider, or
running a database migration.
"""
from __future__ import annotations

import argparse
import ast
import compileall
import json
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CREATIVE_CORE_MODULES = (
    "backend/src/libtv_agent/api/creative_workflow.py",
    "backend/src/libtv_agent/creative/handoff.py",
    "backend/src/libtv_agent/creative/media_qualification.py",
    "backend/src/libtv_agent/creative/provider_input_lease.py",
    "backend/src/libtv_agent/creative/provider_submission_persistence.py",
    "backend/src/libtv_agent/creative/reality_loop.py",
    "backend/src/libtv_agent/creative/text_contract.py",
    "backend/src/libtv_agent/creative/workflow.py",
    "backend/src/libtv_agent/services/creative_image_bridge.py",
    "backend/src/libtv_agent/services/creative_image_workflow_orchestrator.py",
    "backend/src/libtv_agent/services/creative_provider_executor.py",
    "backend/src/libtv_agent/services/creative_provider_input_lease.py",
    "backend/src/libtv_agent/services/creative_provider_preflight.py",
    "backend/src/libtv_agent/services/creative_provider_requests.py",
    "backend/src/libtv_agent/services/creative_provider_submission.py",
    "backend/src/libtv_agent/services/creative_provider_submission_persistence.py",
    "backend/src/libtv_agent/services/creative_reality_loop_gate.py",
    "backend/src/libtv_agent/services/creative_video_bridge.py",
    "backend/src/libtv_agent/services/creative_workflow.py",
    "backend/src/libtv_agent/services/creative_workflow_orchestrator.py",
)

FRONTEND_LOCKFILES = (
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "yarn.lock",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _literal_assignment(tree: ast.Module, name: str, source: Path) -> object:
    for node in tree.body:
        target: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        elif isinstance(node, ast.AnnAssign):
            target = node.target
        if isinstance(target, ast.Name) and target.id == name:
            try:
                return ast.literal_eval(node.value)
            except (SyntaxError, ValueError) as exc:
                raise ValueError(f"{source.name}: {name} is not a literal") from exc
    raise ValueError(f"{source.name}: missing {name}")


def _parents(value: object, field: str, source: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (tuple, list)):
        values = tuple(value)
        if all(isinstance(item, str) for item in values):
            return values
    raise ValueError(f"{source.name}: invalid {field}")


def migration_graph(root: Path) -> dict[str, object]:
    """Parse Alembic revision literals without importing ``env.py``."""
    versions = root / "backend" / "alembic" / "versions"
    revisions: dict[str, tuple[str, ...]] = {}
    files = sorted(versions.glob("*.py"))
    if not files:
        raise ValueError("Alembic versions directory is empty")

    for source in files:
        tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=str(source))
        revision = _literal_assignment(tree, "revision", source)
        if not isinstance(revision, str) or not revision:
            raise ValueError(f"{source.name}: invalid revision")
        if revision in revisions:
            raise ValueError(f"duplicate revision: {revision}")
        parents = _parents(
            _literal_assignment(tree, "down_revision", source),
            "down_revision",
            source,
        )
        depends_on = _parents(
            _literal_assignment(tree, "depends_on", source)
            if any(
                isinstance(node, (ast.Assign, ast.AnnAssign))
                and (
                    isinstance(
                        node.targets[0] if isinstance(node, ast.Assign) else node.target,
                        ast.Name,
                    )
                    and (
                        node.targets[0] if isinstance(node, ast.Assign) else node.target
                    ).id
                    == "depends_on"
                )
                for node in tree.body
            )
            else None,
            "depends_on",
            source,
        )
        revisions[revision] = tuple(dict.fromkeys((*parents, *depends_on)))

    referenced = {parent for parents in revisions.values() for parent in parents}
    missing = referenced - revisions.keys()
    if missing:
        raise ValueError(f"missing migration parents: {sorted(missing)}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(revision: str) -> None:
        if revision in visiting:
            raise ValueError(f"migration cycle at {revision}")
        if revision in visited:
            return
        visiting.add(revision)
        for parent in revisions[revision]:
            visit(parent)
        visiting.remove(revision)
        visited.add(revision)

    for revision in revisions:
        visit(revision)

    heads = sorted(set(revisions) - referenced)
    return {"count": len(revisions), "heads": heads, "revisions": revisions}


def check_creative_modules(root: Path) -> str:
    missing = [
        relative
        for relative in CREATIVE_CORE_MODULES
        if not (root / relative).is_file()
    ]
    if missing:
        raise ValueError("missing: " + ", ".join(missing))
    return f"{len(CREATIVE_CORE_MODULES)} core modules present"


def check_migrations(root: Path) -> str:
    graph = migration_graph(root)
    heads = graph["heads"]
    if not isinstance(heads, list) or len(heads) != 1:
        raise ValueError(f"expected one head, found {heads}")
    return f"{graph['count']} revisions, unique head {heads[0]}"


def check_python_compileall(root: Path) -> str:
    """Compile Python sources while directing bytecode into a temporary cache."""
    source_roots = (
        root / "backend" / "src",
        root / "backend" / "tests",
        root / "scripts",
    )
    missing = [str(path.relative_to(root)) for path in source_roots if not path.is_dir()]
    if missing:
        raise ValueError("missing source directories: " + ", ".join(missing))

    previous_prefix = getattr(sys, "pycache_prefix", None)
    with tempfile.TemporaryDirectory(prefix="creative-offline-pycache-") as cache:
        try:
            sys.pycache_prefix = cache
            results = [
                compileall.compile_dir(
                    str(source_root),
                    quiet=1,
                    force=True,
                    legacy=False,
                    workers=1,
                )
                for source_root in source_roots
            ]
        finally:
            sys.pycache_prefix = previous_prefix
    if not all(results):
        raise ValueError("compileall reported a syntax error")
    return "backend/src, backend/tests and scripts compiled"


def check_frontend_artifacts(root: Path) -> str:
    frontend = root / "frontend"
    package_path = frontend / "package.json"
    if not package_path.is_file():
        raise ValueError("frontend/package.json is missing")
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid frontend/package.json: {exc}") from exc
    if not isinstance(package, dict) or not isinstance(package.get("scripts"), dict):
        raise ValueError("frontend/package.json has no scripts object")
    if not isinstance(package["scripts"].get("build"), str):
        raise ValueError("frontend/package.json has no build script")

    lockfiles = [name for name in FRONTEND_LOCKFILES if (frontend / name).is_file()]
    if not lockfiles:
        raise ValueError("no recognized frontend lockfile")

    index = frontend / "dist" / "index.html"
    if not index.is_file() or not index.read_text(encoding="utf-8").strip():
        raise ValueError("frontend/dist/index.html is missing or empty")
    index_text = index.read_text(encoding="utf-8")
    assets = frontend / "dist" / "assets"
    if not assets.is_dir() or not any(path.is_file() for path in assets.rglob("*")):
        raise ValueError("frontend/dist/assets has no files")
    if "<script" not in index_text or "assets/" not in index_text:
        raise ValueError("frontend/dist/index.html is not a recognizable Vite artifact")
    return f"package/build recognized; lockfile {lockfiles[0]}"


def run_checks(root: Path) -> list[CheckResult]:
    checks: tuple[tuple[str, Callable[[Path], str]], ...] = (
        ("creative modules", check_creative_modules),
        ("alembic graph", check_migrations),
        ("python compileall", check_python_compileall),
        ("frontend package/build", check_frontend_artifacts),
    )
    results: list[CheckResult] = []
    for name, check in checks:
        try:
            results.append(CheckResult(name, True, check(root)))
        except (OSError, SyntaxError, ValueError) as exc:
            results.append(CheckResult(name, False, str(exc)))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="project root (defaults to the repository containing this script)",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        print(f"BLOCKED\nproject root does not exist: {root}")
        return 1

    results = run_checks(root)
    for result in results:
        state = "PASS" if result.passed else "FAIL"
        print(f"[{state}] {result.name}: {result.detail}")
    if all(result.passed for result in results):
        print("OFFLINE_MVP_READY")
        return 0
    print("BLOCKED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
