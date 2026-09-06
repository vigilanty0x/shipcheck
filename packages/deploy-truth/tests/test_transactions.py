from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from deploy_truth.models import ContractError, Decision
from deploy_truth.transactions import (
    DeploymentPlan, OperationKind, TransactionOutcome, apply_plan, build_plan,
    rollback_plan, verify_applied,
)
import deploy_truth.transactions as transaction_module

from helpers import spec, write_layer


class TransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.bundle, self.live, self.rollback = root / "bundle", root / "live", root / "rollback"
        write_layer(self.bundle, {"bin/app": b"v2", "config/app.json": b'{"v":2}\n'})
        write_layer(self.live, {"bin/app": b"v1", "obsolete": b"old"})
        self.rollback.mkdir()
        self.spec = spec()
        self.plan = build_plan(self.spec, self.bundle, self.live)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def apply(self):
        return apply_plan(
            self.plan, self.spec, self.bundle, self.live, self.rollback,
            confirm_plan_id=self.plan.plan_id,
        )

    def rollback_plan(self):
        return rollback_plan(
            self.plan, self.spec, self.live, self.rollback,
            confirm_plan_id=self.plan.plan_id,
        )

    def test_plan_records_writes_and_delete(self) -> None:
        kinds = [operation.kind for operation in self.plan.operations]
        self.assertEqual(kinds.count(OperationKind.WRITE), 2)
        self.assertEqual(kinds.count(OperationKind.DELETE), 1)

    def test_plan_round_trip(self) -> None:
        self.assertEqual(DeploymentPlan.from_dict(self.plan.to_dict()), self.plan)

    def test_plan_tamper_rejected(self) -> None:
        value = self.plan.to_dict()
        value["release_version"] = "tampered"
        with self.assertRaisesRegex(ContractError, "plan_id"):
            DeploymentPlan.from_dict(value)

    def test_wrong_confirmation_blocks_without_changes(self) -> None:
        before = (self.live / "bin/app").read_bytes()
        result = apply_plan(
            self.plan, self.spec, self.bundle, self.live, self.rollback, confirm_plan_id="wrong"
        )
        self.assertEqual(result.decision, Decision.BLOCKED)
        self.assertEqual((self.live / "bin/app").read_bytes(), before)

    def test_live_change_after_plan_blocks(self) -> None:
        (self.live / "bin/app").write_bytes(b"changed-after-plan")
        result = self.apply()
        self.assertEqual(result.outcome, TransactionOutcome.BLOCKED)
        self.assertIn("changed after dry-run", result.outputs[0])

    def test_bundle_change_after_plan_blocks(self) -> None:
        (self.bundle / "bin/app").write_bytes(b"changed-after-plan")
        self.assertEqual(self.apply().decision, Decision.BLOCKED)

    def test_apply_matches_bundle_and_deletes_extra(self) -> None:
        result = self.apply()
        self.assertEqual((result.outcome, result.decision), (TransactionOutcome.APPLIED, Decision.VERIFIED))
        self.assertEqual((self.live / "bin/app").read_bytes(), b"v2")
        self.assertEqual((self.live / "config/app.json").read_bytes(), b'{"v":2}\n')
        self.assertFalse((self.live / "obsolete").exists())

    def test_apply_replay_is_idempotent(self) -> None:
        self.apply()
        before = {path.relative_to(self.live): path.read_bytes() for path in self.live.rglob("*") if path.is_file()}
        result = self.apply()
        after = {path.relative_to(self.live): path.read_bytes() for path in self.live.rglob("*") if path.is_file()}
        self.assertEqual(result.decision, Decision.VERIFIED)
        self.assertEqual(before, after)
        self.assertIn("already applied", result.outputs[0])

    def test_verify_applied_success(self) -> None:
        self.apply()
        result = verify_applied(self.plan, self.spec, self.live)
        self.assertEqual((result.outcome, result.decision), (TransactionOutcome.VERIFIED, Decision.VERIFIED))

    def test_verify_applied_detects_drift(self) -> None:
        self.apply()
        (self.live / "bin/app").write_bytes(b"drift")
        result = verify_applied(self.plan, self.spec, self.live)
        self.assertEqual(result.decision, Decision.DEGRADED)

    def test_rollback_restores_exact_previous_files(self) -> None:
        original = {
            path.relative_to(self.live): path.read_bytes() for path in self.live.rglob("*") if path.is_file()
        }
        self.apply()
        result = self.rollback_plan()
        restored = {
            path.relative_to(self.live): path.read_bytes() for path in self.live.rglob("*") if path.is_file()
        }
        self.assertEqual((result.outcome, result.decision), (TransactionOutcome.ROLLED_BACK, Decision.VERIFIED))
        self.assertEqual(restored, original)

    def test_second_rollback_blocks(self) -> None:
        self.apply()
        self.rollback_plan()
        self.assertEqual(self.rollback_plan().decision, Decision.BLOCKED)

    def test_missing_rollback_evidence_blocks(self) -> None:
        result = self.rollback_plan()
        self.assertEqual(result.decision, Decision.BLOCKED)

    def test_partial_apply_auto_restores(self) -> None:
        original = {
            path.relative_to(self.live): path.read_bytes() for path in self.live.rglob("*") if path.is_file()
        }
        real_copy = transaction_module._atomic_copy
        calls = [0]

        def fail_second(source: Path, destination: Path) -> None:
            calls[0] += 1
            if calls[0] == 2:
                raise OSError("synthetic partial failure")
            real_copy(source, destination)

        with patch("deploy_truth.transactions._atomic_copy", side_effect=fail_second):
            result = self.apply()
        restored = {
            path.relative_to(self.live): path.read_bytes() for path in self.live.rglob("*") if path.is_file()
        }
        self.assertEqual((result.outcome, result.decision), (TransactionOutcome.AUTO_ROLLED_BACK, Decision.BLOCKED))
        self.assertEqual(restored, original)

    def test_bundle_with_unexpected_file_cannot_plan(self) -> None:
        (self.bundle / "extra").write_bytes(b"x")
        with self.assertRaisesRegex(ContractError, "exactly"):
            build_plan(self.spec, self.bundle, self.live)

    def test_plan_with_no_changes_has_no_operations(self) -> None:
        write_layer(self.live, {"bin/app": b"v2", "config/app.json": b'{"v":2}\n'})
        if (self.live / "obsolete").exists():
            (self.live / "obsolete").unlink()
        plan = build_plan(self.spec, self.bundle, self.live)
        self.assertEqual(plan.operations, ())

    def test_result_evidence_is_present(self) -> None:
        self.assertEqual(len(self.apply().evidence_sha256), 64)


if __name__ == "__main__":
    unittest.main()

