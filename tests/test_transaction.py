import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from safe_merge_gate.contract import ContractError
from safe_merge_gate.gate import evaluate
from safe_merge_gate.transaction import (
    ApplyBlocked, LocalMergeTransaction, Receipt, TransactionConflict,
    TransactionVerificationError,
)
from helpers import BASE, MERGE, NOW, snapshot


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.state = self.root / "state.json"
        self.receipt_path = self.root / "receipt.json"
        self.original = b'{\n  "current_sha": "' + BASE.encode() + b'",\n  "note": "keep formatting"\n}\n'
        self.state.write_bytes(self.original)
        self.artifact = evaluate(snapshot(), generated_at=NOW)
        self.transaction = LocalMergeTransaction()

    def tearDown(self): self.directory.cleanup()

    def apply(self): return self.transaction.apply(self.artifact, self.state, self.receipt_path, created_at=NOW)

    def test_dry_run_is_applicable(self):
        result = self.transaction.dry_run(self.artifact, self.state); self.assertTrue(result["applicable"])

    def test_dry_run_does_not_change_bytes(self):
        self.transaction.dry_run(self.artifact, self.state); self.assertEqual(self.state.read_bytes(), self.original)

    def test_dry_run_rejects_wrong_local_sha(self):
        self.state.write_text(json.dumps({"current_sha": "3" * 40}))
        self.assertFalse(self.transaction.dry_run(self.artifact, self.state)["applicable"])

    def test_dry_run_absent_state_not_applicable(self):
        self.state.unlink(); self.assertFalse(self.transaction.dry_run(self.artifact, self.state)["applicable"])

    def test_apply_changes_current_sha(self):
        self.apply(); self.assertEqual(json.loads(self.state.read_text())["current_sha"], MERGE)

    def test_apply_records_artifact_sha(self):
        self.apply(); self.assertEqual(json.loads(self.state.read_text())["artifact_sha256"], self.artifact.sha256)

    def test_apply_creates_verified_receipt(self):
        receipt = self.apply(); self.assertTrue(self.receipt_path.is_file())
        self.assertEqual(Receipt.from_dict(json.loads(self.receipt_path.read_text())), receipt)

    def test_verify_applied_state(self):
        receipt = self.apply(); self.assertTrue(self.transaction.verify(receipt, self.state)["verified"])

    def test_verify_detects_byte_tampering(self):
        receipt = self.apply(); self.state.write_bytes(self.state.read_bytes() + b" ")
        with self.assertRaisesRegex(TransactionVerificationError, "bytes"): self.transaction.verify(receipt, self.state)

    def test_apply_rejects_blocked_artifact(self):
        blocked = evaluate(snapshot(observed_sha="3" * 40), generated_at=NOW)
        with self.assertRaises(ApplyBlocked): self.transaction.apply(blocked, self.state, self.receipt_path, created_at=NOW)
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_apply_rejects_degraded_artifact(self):
        degraded = evaluate(snapshot(ci={"build": "success", "test": "success"}), generated_at=NOW)
        with self.assertRaises(ApplyBlocked): self.transaction.apply(degraded, self.state, self.receipt_path, created_at=NOW)

    def test_apply_rejects_wrong_local_sha(self):
        self.state.write_text(json.dumps({"current_sha": "3" * 40}))
        with self.assertRaises(TransactionConflict): self.apply()

    def test_apply_refuses_existing_receipt(self):
        self.receipt_path.write_text("occupied")
        with self.assertRaisesRegex(TransactionConflict, "already exists"): self.apply()

    def test_rollback_restores_exact_bytes(self):
        receipt = self.apply(); self.transaction.rollback(receipt, self.state)
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_rollback_is_idempotent(self):
        receipt = self.apply(); first = self.transaction.rollback(receipt, self.state)
        second = self.transaction.rollback(receipt, self.state)
        self.assertFalse(first["idempotent"]); self.assertTrue(second["idempotent"])

    def test_rollback_refuses_diverged_state(self):
        receipt = self.apply(); self.state.write_text(json.dumps({"current_sha": "4" * 40}))
        with self.assertRaisesRegex(TransactionConflict, "changed after apply"): self.transaction.rollback(receipt, self.state)

    def test_apply_and_rollback_absent_prior_file(self):
        self.state.unlink()
        # An absent file has no current SHA, so it cannot safely match an immutable base.
        with self.assertRaises(TransactionConflict): self.apply()

    def test_verify_wrong_path_rejected(self):
        receipt = self.apply()
        with self.assertRaisesRegex(TransactionVerificationError, "path"): self.transaction.verify(receipt, self.root / "other")

    def test_rollback_wrong_path_rejected(self):
        receipt = self.apply()
        with self.assertRaisesRegex(TransactionConflict, "path"): self.transaction.rollback(receipt, self.root / "other")

    def test_receipt_sha_tampering_rejected(self):
        self.apply(); value = json.loads(self.receipt_path.read_text()); value["merge_sha"] = "9" * 40
        with self.assertRaisesRegex(ContractError, "mismatch"): Receipt.from_dict(value)

    def test_receipt_prior_bytes_tampering_rejected_even_with_rehashed_envelope(self):
        receipt = self.apply(); value = receipt.to_dict(); value["before_bytes_b64"] = "AAAA"
        body = {key: value[key] for key in value if key != "receipt_sha256"}
        import hashlib
        from safe_merge_gate.contract import canonical_json
        value["receipt_sha256"] = hashlib.sha256(canonical_json(body).encode()).hexdigest()
        with self.assertRaisesRegex(ContractError, "before-byte"): Receipt.from_dict(value)


if __name__ == "__main__": unittest.main()

