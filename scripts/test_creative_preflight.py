from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from check_creative_preflight import (
    FakeLedger,
    decide_call,
    load_contract,
    migration_graph,
    validate_asset,
    validate_contract,
    validate_selections,
)

ROOT = Path(__file__).resolve().parents[1]


class PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_contract(ROOT)
        self.fixture = deepcopy(self.contract["fake_fixture"])
        self.ledger = FakeLedger()

    def decide(self) -> str:
        return decide_call(self.contract, self.fixture, self.ledger)

    def test_contract_and_synthetic_happy_path(self):
        validate_contract(self.contract)
        self.assertEqual(self.decide(), "RESERVED")

    def test_no_runtime_approval_can_be_smuggled_in(self):
        for key in self.contract["approval"]:
            with self.subTest(key=key):
                contract = deepcopy(self.contract)
                contract["approval"][key] = True
                with self.assertRaises(ValueError):
                    validate_contract(contract)

    def test_module_and_reality_order(self):
        for key in ("pipeline", "revision_pipeline", "reality_dimensions"):
            with self.subTest(key=key):
                contract = deepcopy(self.contract)
                contract[key].reverse()
                with self.assertRaises(ValueError):
                    validate_contract(contract)
        self.fixture["request"]["modules_run"] = ["E1", "D4", "D3"]
        self.assertEqual(self.decide(), "MODULE_ORDER_INVALID")

    def test_unknown_and_write_uncertain_never_replace_submission(self):
        for status in ("UNKNOWN", "WRITE_UNCERTAIN"):
            with self.subTest(status=status):
                self.fixture["request"]["execution_state"] = status
                self.assertEqual(self.decide(), "EXECUTION_UNKNOWN")
                self.assertEqual(len(self.ledger.entries), 0)

    def test_existing_attempt_is_recovered_not_resubmitted(self):
        self.fixture["request"]["execution_state"] = "SUCCEEDED"
        self.assertEqual(self.decide(), "EXISTING_ATTEMPT_RECOVERY")

    def test_owner_and_task_isolation(self):
        for key in ("owner_id", "task_id"):
            with self.subTest(key=key):
                fixture = deepcopy(self.fixture)
                fixture["request"][key] = "other"
                self.assertEqual(
                    decide_call(self.contract, fixture, self.ledger), "OWNER_OR_TASK_MISMATCH"
                )

    def test_package_locks_ruleset_and_stale_results(self):
        for key in ("package_id", "locks_hash", "ruleset_hash"):
            with self.subTest(key=key):
                fixture = deepcopy(self.fixture)
                fixture["request"][key] = "changed"
                self.assertEqual(
                    decide_call(self.contract, fixture, self.ledger), "LOCK_OR_PACKAGE_CONFLICT"
                )
        self.fixture["request"]["state_version"] -= 1
        self.assertEqual(self.decide(), "STALE_VERSION")

    def test_scope_and_shot_authorization(self):
        self.fixture["request"]["scope"] = "VIDEO"
        self.assertEqual(self.decide(), "SCOPE_MISMATCH")
        self.fixture["request"].update(scope="STORYBOARD", shot_id="S03")
        self.assertEqual(self.decide(), "SHOT_NOT_AUTHORIZED")

    def test_exact_expiry_and_user_stop(self):
        self.fixture["request"]["now"] = self.fixture["authorization"]["expires_at"]
        self.assertEqual(self.decide(), "AUTH_EXPIRED")
        self.fixture["request"]["user_stopped"] = True
        self.assertEqual(self.decide(), "USER_STOPPED")

    def test_back_assumption_does_not_turn_into_observed_evidence(self):
        self.fixture["request"]["back_required"] = True
        self.assertEqual(self.decide(), "BACK_UNDECIDED")
        self.fixture["request"]["back_evidence"] = "USER_ASSUMED"
        self.assertEqual(self.decide(), "BACK_CONFIRMATION_REQUIRED")
        self.fixture["request"]["back_confirmation_id"] = "fake-confirmation-for-package-r1"
        self.assertEqual(self.decide(), "RESERVED")
        self.assertEqual(self.fixture["request"]["back_evidence"], "USER_ASSUMED")

    def test_pixels_capability_and_failure_evidence(self):
        for key, result in (
            ("pixels_verified", "UNVERIFIED_PIXELS"),
            ("critic_capability_verified", "UNVERIFIED_PIXELS"),
            ("failed_region_evidence", "FAILURE_EVIDENCE_REQUIRED"),
        ):
            with self.subTest(key=key):
                fixture = deepcopy(self.fixture)
                fixture["request"][key] = False
                self.assertEqual(decide_call(self.contract, fixture, self.ledger), result)

    def test_loop_off_and_hard_limit_and_no_progress(self):
        self.fixture["authorization"]["loop_enabled"] = False
        self.assertEqual(self.decide(), "LOOP_NOT_AUTHORIZED")
        self.fixture["authorization"].update(loop_enabled=True, max_revisions=3)
        self.assertEqual(self.decide(), "LIMIT_REACHED")
        self.fixture["authorization"]["max_revisions"] = 1
        self.fixture["request"]["revision_index"] = 2
        self.assertEqual(self.decide(), "LIMIT_REACHED")
        self.fixture["request"].update(revision_index=1, no_progress_count=2)
        self.assertEqual(self.decide(), "NO_PROGRESS")

    def test_locked_module_cannot_be_changed(self):
        self.fixture["request"]["changed_modules"] = ["Product"]
        self.fixture["authorization"]["allowed_modules"].append("Product")
        self.assertEqual(self.decide(), "LOCK_CONFLICT")

    def test_initial_draft_requires_whole_pipeline(self):
        self.fixture["request"].update(revision_index=0, modules_run=self.contract["pipeline"][:7])
        self.fixture["authorization"]["loop_enabled"] = False
        self.assertEqual(self.decide(), "RESERVED")

    def test_asset_integrity_license_revoke_and_materialization(self):
        mutations = [
            ("owner_id", "other", "OWNER_MISMATCH"),
            ("sha256", "broken", "HASH_INVALID"),
            ("object_key", "../secret", "OBJECT_KEY_INVALID"),
            ("width", 0, "DIMENSIONS_INVALID"),
            ("revoked", True, "ASSET_UNAVAILABLE"),
            ("expired", True, "ASSET_UNAVAILABLE"),
            ("materialized", False, "ASSET_NOT_MATERIALIZED"),
            ("license_status", "UNKNOWN", "LICENSE_UNVERIFIED"),
            ("source_type", "GENERATED", "CANONICAL_SOURCE_INVALID"),
        ]
        for key, value, result in mutations:
            with self.subTest(key=key):
                asset = deepcopy(self.fixture["asset"])
                asset[key] = value
                self.assertEqual(validate_asset(
                    asset, self.fixture["owner_id"], self.contract["asset_required"]
                ), result)

    def test_generated_source_and_human_qualification(self):
        asset = self.fixture["asset"]
        asset.update(canonical=False, source_type="GENERATED", role="STORYBOARD")
        self.assertEqual(validate_asset(
            asset, self.fixture["owner_id"], self.contract["asset_required"]
        ), "HUMAN_REVIEW_REQUIRED")
        asset["qualification_status"] = "QUALIFIED"
        self.assertEqual(self.decide(), "CANONICAL_REQUIRED")

    def test_idempotent_replay_does_not_double_reserve(self):
        self.assertEqual(self.decide(), "RESERVED")
        self.fixture["request"]["now"] = "2027-01-01T00:00:00+00:00"
        self.assertEqual(self.decide(), "REPLAY")
        self.assertEqual(self.ledger.charged_or_held(), 30)
        self.fixture["request"]["request_hash"] = "changed"
        self.assertEqual(self.decide(), "IDEMPOTENCY_CONFLICT")

    def test_unknown_cost_is_held(self):
        self.assertEqual(self.decide(), "RESERVED")
        self.assertEqual(self.ledger.settle("fake-cmd-1", "UNKNOWN"), "HOLD")
        self.assertEqual(self.ledger.charged_or_held(), 30)
        self.assertEqual(self.ledger.settle("fake-cmd-1", "SUCCEEDED"), "RECONCILIATION_REQUIRED")
        self.assertEqual(self.ledger.settle("fake-cmd-1", "SUCCEEDED", 31), "QUOTE_EXCEEDED")
        self.assertEqual(self.ledger.charged_or_held(), 30)
        self.assertEqual(self.ledger.settle("fake-cmd-1", "SUCCEEDED", 20), "SETTLED")
        self.assertEqual(self.ledger.charged_or_held(), 20)

    def test_settlement_replay_and_old_unknown_cannot_regress_terminal_record(self):
        self.assertEqual(self.decide(), "RESERVED")
        self.assertEqual(self.ledger.settle("fake-cmd-1", "SUCCEEDED", 20), "SETTLED")
        version = self.ledger.version
        self.assertEqual(self.ledger.settle("fake-cmd-1", "SUCCEEDED", 20), "SETTLED")
        self.assertEqual(self.ledger.version, version)
        self.assertEqual(self.ledger.settle("fake-cmd-1", "UNKNOWN"), "SETTLEMENT_CONFLICT")
        self.assertEqual(self.ledger.charged_or_held(), 20)

    def test_shared_budget_stage_cap_model_cap_and_cas(self):
        self.assertEqual(self.decide(), "RESERVED")
        request = deepcopy(self.fixture["request"])
        request["command_id"] = "second"
        auth = self.fixture["authorization"]
        self.assertEqual(self.ledger.reserve(request, auth, 0), "STALE_LEDGER")
        request["reserved_cost_micros"] = 80
        self.assertEqual(self.ledger.reserve(request, auth, 1), "BUDGET_EXHAUSTED")
        request["reserved_cost_micros"] = 51
        self.assertEqual(self.ledger.reserve(request, auth, 1), "STAGE_BUDGET_EXHAUSTED")
        request["reserved_cost_micros"] = -1
        self.assertEqual(self.ledger.reserve(request, auth, 1), "INVALID_COST")
        request["reserved_cost_micros"] = 30
        auth["model_call_caps"]["fake-image"] = 1
        self.assertEqual(self.ledger.reserve(request, auth, 1), "MODEL_CALL_LIMIT")

    def test_missing_asset_field(self):
        del self.fixture["asset"]["source_id"]
        self.assertEqual(self.decide(), "ASSET_INCOMPLETE")

    def test_contract_roundtrip(self):
        self.assertEqual(json.loads(json.dumps(self.contract)), self.contract)

    def test_shot_mapping_survives_reordering_and_rejects_cross_shot_output(self):
        self.fixture["selections"].reverse()
        self.assertEqual(validate_selections(self.fixture), "VALID")
        self.fixture["selections"][0]["output_shot_id"] = "S01"
        self.assertEqual(validate_selections(self.fixture), "SHOT_OUTPUT_MISMATCH")

    def test_selection_requires_human_review_ownership_hash_and_availability(self):
        for key, value, result in [
            ("reviewer_kind", "MODEL", "HUMAN_REVIEW_REQUIRED"),
            ("qualification_status", "PENDING", "HUMAN_REVIEW_REQUIRED"),
            ("owner_id", "other", "SELECTION_BINDING_INVALID"),
            ("package_id", "old", "SELECTION_BINDING_INVALID"),
            ("revoked", True, "SELECTION_UNAVAILABLE"),
            ("materialized_sha256", "wrong", "SELECTION_HASH_MISMATCH"),
            ("order", 3, "ORDER_INVALID"),
        ]:
            with self.subTest(key=key):
                fixture = deepcopy(self.fixture)
                fixture["selections"][0][key] = value
                self.assertEqual(validate_selections(fixture), result)

    def test_multiple_candidates_require_one_selection_per_shot(self):
        self.fixture["selections"].append(deepcopy(self.fixture["selections"][0]))
        self.assertEqual(validate_selections(self.fixture), "DUPLICATE_SHOT")

    def test_graph_branches_and_merge_without_importing_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            versions = root / "backend/alembic/versions"
            versions.mkdir(parents=True)
            for name, parents in [("a", None), ("b", "a"), ("c", "a"), ("d", ("b", "c"))]:
                # Synthetic migrations contain a trap: execution must never occur.
                (versions / f"{name}.py").write_text(
                    f"raise RuntimeError('must not import')\nrevision = {name!r}\n"
                    f"down_revision = {parents!r}\n", encoding="utf-8",
                )
            self.assertEqual(migration_graph(root)["heads"], ["d"])
            (versions / "d.py").write_text(
                "revision = 'd'\ndown_revision = 'missing'\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "missing"):
                migration_graph(root)

    def test_graph_rejects_duplicate_and_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            versions = root / "backend/alembic/versions"
            versions.mkdir(parents=True)
            (versions / "a.py").write_text(
                "revision = 'a'\ndown_revision = 'b'\n", encoding="utf-8"
            )
            (versions / "b.py").write_text(
                "revision = 'b'\ndown_revision = 'a'\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "cycle"):
                migration_graph(root)
            (versions / "b.py").write_text(
                "revision = 'a'\ndown_revision = None\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "duplicate"):
                migration_graph(root)


if __name__ == "__main__":
    unittest.main()
