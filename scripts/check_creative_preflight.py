"""Offline design checks and a Fake ledger, not a production authorization service."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path

CONTRACT_PATH = "docs/contracts/creative-workflow-preflight.v1.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
UNCERTAIN = {"UNKNOWN", "WRITE_UNCERTAIN"}


def load_contract(root: Path) -> dict:
    return json.loads((root / CONTRACT_PATH).read_text(encoding="utf-8"))


def migration_graph(root: Path) -> dict:
    """Parse literals only: importing env.py could load secrets or connect to a DB."""
    revisions: dict[str, tuple[str, ...]] = {}
    hashes = {}
    for file in sorted((root / "backend/alembic/versions").glob("*.py")):
        values = {}
        for node in ast.parse(file.read_text(encoding="utf-8-sig")).body:
            target = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
            elif isinstance(node, ast.AnnAssign):
                target = node.target
            if isinstance(target, ast.Name) and target.id in {
                "revision", "down_revision", "depends_on",
            }:
                values[target.id] = ast.literal_eval(node.value)
        if "revision" not in values:
            raise ValueError(f"migration without revision: {file.name}")
        revision = values["revision"]
        if not isinstance(revision, str) or revision in revisions:
            raise ValueError(f"duplicate or invalid revision: {revision}")
        parent = values.get("down_revision")
        parents = () if parent is None else (parent,) if isinstance(parent, str) else tuple(parent)
        if any(not isinstance(value, str) for value in parents):
            raise ValueError(f"invalid parents: {revision}")
        if values.get("depends_on") is not None:
            raise ValueError("dependency edges require explicit graph support")
        revisions[revision] = parents
        hashes[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
    if not revisions:
        raise ValueError("migration graph is empty")
    referenced = {parent for parents in revisions.values() for parent in parents}
    if referenced - revisions.keys():
        raise ValueError(f"missing migration parents: {referenced - revisions.keys()}")
    visiting, visited = set(), set()

    def visit(revision: str) -> None:
        if revision in visiting:
            raise ValueError("migration cycle")
        if revision in visited:
            return
        visiting.add(revision)
        for parent in revisions[revision]:
            visit(parent)
        visiting.remove(revision)
        visited.add(revision)

    for revision in revisions:
        visit(revision)
    return {
        "count": len(revisions), "heads": sorted(revisions.keys() - referenced),
        "parents": revisions, "file_hashes": hashes,
    }


def validate_asset(asset: dict, owner_id: str, required: list[str]) -> str:
    if any(key not in asset for key in required):
        return "ASSET_INCOMPLETE"
    if asset["owner_id"] != owner_id:
        return "OWNER_MISMATCH"
    key = asset["object_key"]
    if (not isinstance(key, str) or not key or key.startswith("/")
            or "\\" in key or ":" in key or ".." in key.split("/")):
        return "OBJECT_KEY_INVALID"
    if not SHA256.fullmatch(asset["sha256"]):
        return "HASH_INVALID"
    if (type(asset["width"]) is not int or type(asset["height"]) is not int
            or min(asset["width"], asset["height"]) <= 0):
        return "DIMENSIONS_INVALID"
    if asset["revoked"] or asset["expired"] or asset["access_status"] != "AVAILABLE":
        return "ASSET_UNAVAILABLE"
    if not asset["materialized"]:
        return "ASSET_NOT_MATERIALIZED"
    if asset["license_status"] != "VERIFIED" or not asset["license_evidence_id"]:
        return "LICENSE_UNVERIFIED"
    if asset["canonical"] and (
        asset["role"] != "PRODUCT" or asset["source_type"] != "USER_UPLOAD"
        or asset["evidence_status"] != "OBSERVED_REFERENCE"
    ):
        return "CANONICAL_SOURCE_INVALID"
    if asset["role"] in {"FIRST_FRAME", "STORYBOARD"}:
        if asset["qualification_status"] != "QUALIFIED":
            return "HUMAN_REVIEW_REQUIRED"
    return "VALID"


class FakeLedger:
    """Sequential CAS simulator; it does not prove DB atomicity or worker safety."""

    def __init__(self) -> None:
        self.version = 0
        self.entries: dict[str, dict] = {}

    def charged_or_held(self, stage: str | None = None) -> int:
        return sum(
            entry["cost"] for entry in self.entries.values()
            if stage is None or entry["stage"] == stage
        )

    def reserve(self, request: dict, authorization: dict, expected_version: int) -> str:
        key = request["command_id"]
        if key in self.entries:
            return (
                "REPLAY" if self.entries[key]["hash"] == request["request_hash"]
                else "IDEMPOTENCY_CONFLICT"
            )
        if self.version != expected_version:
            return "STALE_LEDGER"
        amount = request["reserved_cost_micros"]
        if type(amount) is not int or amount < 0:
            return "INVALID_COST"
        if self.charged_or_held() + amount > authorization["max_total_cost_micros"]:
            return "BUDGET_EXHAUSTED"
        stage = request["stage"]
        stage_cap = authorization["stage_caps_micros"].get(stage)
        if stage_cap is None or self.charged_or_held(stage) + amount > stage_cap:
            return "STAGE_BUDGET_EXHAUSTED"
        model = request["model"]
        model_cap = authorization["model_call_caps"].get(model)
        calls = sum(entry["model"] == model for entry in self.entries.values())
        if model_cap is None or calls >= model_cap:
            return "MODEL_CALL_LIMIT"
        self.entries[key] = {
            "hash": request["request_hash"], "cost": amount, "model": model,
            "stage": stage, "status": "RESERVED",
        }
        self.version += 1
        return "RESERVED"

    def settle(self, command_id: str, status: str, actual_cost: int | None = None) -> str:
        entry = self.entries[command_id]
        if entry["status"] == "SETTLED":
            return (
                "SETTLED" if status not in UNCERTAIN and actual_cost == entry["cost"]
                else "SETTLEMENT_CONFLICT"
            )
        if status in UNCERTAIN:
            entry["status"] = status
            return "HOLD"
        if type(actual_cost) is not int or actual_cost < 0:
            return "RECONCILIATION_REQUIRED"
        if actual_cost > entry["cost"]:
            return "QUOTE_EXCEEDED"
        entry.update(status="SETTLED", cost=actual_cost)
        self.version += 1
        return "SETTLED"


def decide_call(contract: dict, fixture: dict, ledger: FakeLedger) -> str:
    """Evaluate synthetic input; no Provider, application imports, or file materialization."""
    request, auth = fixture["request"], fixture["authorization"]
    for key in ("owner_id", "task_id"):
        if not (fixture[key] == auth[key] == request[key]):
            return "OWNER_OR_TASK_MISMATCH"
    prior = ledger.entries.get(request["command_id"])
    if prior:
        return "REPLAY" if prior["hash"] == request["request_hash"] else "IDEMPOTENCY_CONFLICT"
    if request["execution_state"] in UNCERTAIN:
        return "EXECUTION_UNKNOWN"
    if request["execution_state"] != "NOT_SUBMITTED":
        return "EXISTING_ATTEMPT_RECOVERY"
    if request["state_version"] != fixture["state_version"]:
        return "STALE_VERSION"
    for key in ("package_id", "locks_hash", "ruleset_hash"):
        if not (fixture[key] == auth[key] == request[key]):
            return "LOCK_OR_PACKAGE_CONFLICT"
    if request["user_stopped"]:
        return "USER_STOPPED"
    if datetime.fromisoformat(request["now"]) >= datetime.fromisoformat(auth["expires_at"]):
        return "AUTH_EXPIRED"
    if request["scope"] != auth["scope"]:
        return "SCOPE_MISMATCH"
    if request["scope"] == "STORYBOARD" and request["shot_id"] not in auth["shot_ids"]:
        return "SHOT_NOT_AUTHORIZED"
    if request["back_required"]:
        if request["back_evidence"] not in {"OBSERVED_REFERENCE", "USER_ASSUMED"}:
            return "BACK_UNDECIDED"
        if request["back_evidence"] == "USER_ASSUMED" and not request["back_confirmation_id"]:
            return "BACK_CONFIRMATION_REQUIRED"
    asset_result = validate_asset(fixture["asset"], fixture["owner_id"], contract["asset_required"])
    if asset_result != "VALID":
        return asset_result
    if not fixture["asset"]["canonical"]:
        return "CANONICAL_REQUIRED"
    index = request["revision_index"]
    maximum = auth["max_revisions"]
    if type(index) is not int or index < 0 or type(maximum) is not int or maximum < 0:
        return "INVALID_REVISION"
    if maximum > contract["loop"]["hard_max_revisions"] or index > maximum:
        return "LIMIT_REACHED"
    if index > 0:
        if not auth["loop_enabled"]:
            return "LOOP_NOT_AUTHORIZED"
        if not request["critic_capability_verified"] or not request["pixels_verified"]:
            return "UNVERIFIED_PIXELS"
        if not request["failed_region_evidence"]:
            return "FAILURE_EVIDENCE_REQUIRED"
        if request["no_progress_count"] >= contract["loop"]["no_progress_limit"]:
            return "NO_PROGRESS"
        if (not request["changed_modules"]
                or not set(request["changed_modules"]) <= set(auth["allowed_modules"])
                or set(request["changed_modules"]) & {"Product", "Brand", "UserLocks"}):
            return "LOCK_CONFLICT"
        expected_modules = contract["revision_pipeline"][:3]
    else:
        expected_modules = contract["pipeline"][:7]
    if request["modules_run"] != expected_modules:
        return "MODULE_ORDER_INVALID"
    return ledger.reserve(request, auth, ledger.version)


def validate_selections(fixture: dict) -> str:
    selections = fixture["selections"]
    if not selections:
        return "SELECTION_REQUIRED"
    shot_ids = [selection["shot_id"] for selection in selections]
    if len(set(shot_ids)) != len(shot_ids):
        return "DUPLICATE_SHOT"
    if len({selection["output_id"] for selection in selections}) != len(selections):
        return "DUPLICATE_OUTPUT"
    if sorted(selection["order"] for selection in selections) != list(
        range(1, len(selections) + 1)
    ):
        return "ORDER_INVALID"
    for selection in selections:
        if any(selection[key] != fixture[key] for key in ("owner_id", "task_id", "package_id")):
            return "SELECTION_BINDING_INVALID"
        if selection["shot_id"] != selection["output_shot_id"]:
            return "SHOT_OUTPUT_MISMATCH"
        if (selection["qualification_status"] != "QUALIFIED"
                or selection["reviewer_kind"] != "HUMAN"):
            return "HUMAN_REVIEW_REQUIRED"
        if selection["revoked"] or not selection["materialized"]:
            return "SELECTION_UNAVAILABLE"
        if (not SHA256.fullmatch(selection["sha256"])
                or selection["sha256"] != selection["materialized_sha256"]):
            return "SELECTION_HASH_MISMATCH"
    return "VALID"


def validate_contract(contract: dict) -> None:
    if contract["schema_version"] != "creative-workflow-preflight.v1":
        raise ValueError("unexpected contract version")
    if any(contract["approval"].values()):
        raise ValueError("preflight cannot authorize runtime or paid calls")
    if contract["plugin"]["precedence"] != [27, 26, 24, 23]:
        raise ValueError("plugin precedence drift")
    sources = contract["plugin"]["source_manifest"]
    if (not sources or len({entry["path"] for entry in sources}) != len(sources)
            or any(not SHA256.fullmatch(entry["sha256"]) for entry in sources)):
        raise ValueError("invalid plugin source manifest")
    if contract["pipeline"] != ["G0", "D1", "D2", "D3", "D4", "H1", "E1", "E2", "E3"]:
        raise ValueError("module order drift")
    if contract["revision_pipeline"] != ["D3", "D4", "E1", "E2", "E3"]:
        raise ValueError("revision order drift")
    if contract["reality_dimensions"] != [
        "Camera", "Lighting", "Composition", "Human Behavior", "Environment", "Imperfection",
    ]:
        raise ValueError("Reality dimension order drift")
    loop = contract["loop"]
    if (loop["enabled_by_default"] or loop["default_max_revisions"] != 1
            or loop["hard_max_revisions"] != 2 or loop["no_progress_limit"] != 2):
        raise ValueError("loop policy drift")
    if contract["authority"]["QualityDecision"] != "human_only":
        raise ValueError("model cannot qualify an output")
    if set(contract["uncertain_actions"]) != {"query", "reconcile"}:
        raise ValueError("unknown execution cannot resubmit")
    if not contract["fake_fixture"]["synthetic"]:
        raise ValueError("only synthetic fixture allowed")
    if any(item["status"] != "PENDING" for item in contract["decision_items"]):
        raise ValueError("human decisions need a separately recorded review")
    if decide_call(contract, deepcopy(contract["fake_fixture"]), FakeLedger()) != "RESERVED":
        raise ValueError("valid synthetic fixture failed")
    if validate_selections(contract["fake_fixture"]) != "VALID":
        raise ValueError("synthetic selection mapping failed")


def source_evidence(root: Path, role: str, contract: dict) -> list[dict]:
    findings = []
    for evidence in contract["source_evidence"]:
        file = (root / evidence["path"]).resolve()
        if not file.is_relative_to(root.resolve()):
            raise ValueError("source evidence escapes repository")
        status = evidence[role]
        if status == "NEW_BUILD":
            if file.exists():
                raise ValueError(f"baseline drift; newly present: {evidence['id']}")
            findings.append({"id": evidence["id"], "status": status, "present": False})
            continue
        data = file.read_bytes()
        tree = ast.parse(data.decode("utf-8-sig"))
        symbol = evidence["symbol"]
        if symbol and not any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == symbol for node in ast.walk(tree)
        ):
            raise ValueError(f"missing source symbol: {symbol}")
        findings.append({
            "id": evidence["id"], "status": status, "present": True,
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    return findings


def plugin_evidence(plugin_root: Path, archive: Path, contract: dict) -> dict:
    plugin = contract["plugin"]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != plugin["archive_sha256"]:
        raise ValueError("plugin archive drift")
    for entry in plugin["source_manifest"]:
        file = (plugin_root / plugin["reference_base"] / entry["path"]).resolve()
        if not file.is_relative_to(plugin_root.resolve()):
            raise ValueError("plugin evidence escapes audit directory")
        if hashlib.sha256(file.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"plugin source drift: {entry['path']}")
    return {"archive_verified": True, "source_hashes_verified": len(plugin["source_manifest"])}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--role", required=True, choices=["testing", "main"])
    parser.add_argument("--plugin-root", type=Path)
    parser.add_argument("--plugin-archive", type=Path)
    args = parser.parse_args()
    if bool(args.plugin_root) != bool(args.plugin_archive):
        parser.error("plugin-root and plugin-archive must be supplied together")
    contract = load_contract(args.root)
    validate_contract(contract)
    graph = migration_graph(args.root)
    expected = contract["expected_migrations"][args.role]
    if graph["heads"] != expected["heads"] or graph["count"] != expected["count"]:
        raise ValueError("migration baseline drift; re-audit before development")
    print(json.dumps({
        "result": "OFFLINE_CONTRACT_PASS_NOT_CW_GATE_APPROVAL",
        "role": args.role, "migration": graph,
        "sources": source_evidence(args.root, args.role, contract),
        "pending_decisions": [item["id"] for item in contract["decision_items"]],
        "pixel_critic": contract["loop"]["real_critic_capability"],
        "plugin_evidence": (
            plugin_evidence(args.plugin_root, args.plugin_archive, contract)
            if args.plugin_root else "NOT_RECHECKED_USE_RECORDED_SOURCE_HASHES"
        ),
        "paid_calls": 0,
    }, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
