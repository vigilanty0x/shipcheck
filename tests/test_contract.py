import unittest

from safe_merge_gate.contract import (
    Change, Check, CheckState, ContractError, Decision, GateArtifact, GatePolicy,
    MergeSnapshot, SecretFinding, canonical_json, sha256_json,
)
from safe_merge_gate.gate import evaluate
from helpers import NOW, finding, policy, snapshot


class ChangeTests(unittest.TestCase):
    def test_changed_lines(self): self.assertEqual(Change("a.py", 3, 4).changed_lines, 7)
    def test_absolute_path_rejected(self):
        with self.assertRaises(ContractError): Change("/etc/file", 0, 0)
    def test_parent_path_rejected(self):
        with self.assertRaises(ContractError): Change("../file", 0, 0)
    def test_backslash_rejected(self):
        with self.assertRaises(ContractError): Change("src\\file", 0, 0)
    def test_dot_prefix_rejected(self):
        with self.assertRaises(ContractError): Change("./file", 0, 0)
    def test_negative_additions_rejected(self):
        with self.assertRaises(ContractError): Change("a", -1, 0)
    def test_boolean_count_rejected(self):
        with self.assertRaises(ContractError): Change("a", True, 0)
    def test_binary_must_be_boolean(self):
        with self.assertRaises(ContractError): Change("a", 0, 0, 1)
    def test_round_trip(self):
        item = Change("src/a.py", 2, 1, False); self.assertEqual(Change.from_dict(item.to_dict()), item)


class SnapshotTests(unittest.TestCase):
    def test_inventory_is_sorted(self):
        item = snapshot(changes=(Change("z", 1, 0), Change("a", 2, 1)))
        self.assertEqual([x["path"] for x in item.inventory["changes"]], ["a", "z"])
    def test_inventory_totals(self):
        item = snapshot(changes=(Change("a", 2, 1), Change("b", 0, 0, True)))
        self.assertEqual((item.inventory["files"], item.inventory["changed_lines"], item.inventory["binary_files"]), (2, 3, 1))
    def test_inventory_sha_is_order_independent(self):
        a, b = Change("a", 1, 0), Change("b", 2, 0)
        self.assertEqual(snapshot(changes=(a, b)).inventory_sha256, snapshot(changes=(b, a)).inventory_sha256)
    def test_duplicate_paths_rejected(self):
        with self.assertRaisesRegex(ContractError, "unique"): snapshot(changes=(Change("a", 1, 0), Change("a", 2, 0)))
    def test_bad_sha_rejected(self):
        with self.assertRaises(ContractError): snapshot(expected_sha="xyz")
    def test_sha_64_supported(self):
        item = snapshot(expected_sha="a" * 64, observed_sha="a" * 64, merge_sha="b" * 64); self.assertEqual(len(item.expected_sha), 64)
    def test_timestamp_normalized(self): self.assertEqual(snapshot(captured_at="2026-01-01T01:00:00+01:00").captured_at, NOW)
    def test_naive_timestamp_rejected(self):
        with self.assertRaisesRegex(ContractError, "timezone"): snapshot(captured_at="2026-01-01T00:00:00")
    def test_ci_names_sorted(self): self.assertEqual(snapshot(required_ci=("test", "build")).required_ci, ("build", "test"))
    def test_ci_overlap_rejected(self):
        with self.assertRaisesRegex(ContractError, "overlap"): snapshot(required_ci=("build",), optional_ci=("build",))
    def test_invalid_ci_state_rejected(self):
        with self.assertRaisesRegex(ContractError, "invalid CI"): snapshot(ci={"build": "maybe"})
    def test_boolean_attestation_required(self):
        with self.assertRaisesRegex(ContractError, "boolean"): snapshot(clean_tree=1)
    def test_secret_finding_round_trip(self):
        item = finding(); self.assertEqual(SecretFinding.from_dict(item.to_dict()), item)
    def test_snapshot_round_trip(self):
        item = snapshot(secret_findings=(finding(),)); self.assertEqual(MergeSnapshot.from_dict(item.to_dict()), item)
    def test_snapshot_sha_detects_change(self): self.assertNotEqual(snapshot().sha256, snapshot(clean_tree=False).sha256)
    def test_declared_inventory_total_mismatch_rejected(self):
        value = snapshot().to_dict(); value["inventory"]["files"] = 99
        with self.assertRaisesRegex(ContractError, "canonical"): MergeSnapshot.from_dict(value)


class PolicyAndArtifactTests(unittest.TestCase):
    def test_negative_limit_rejected(self):
        with self.assertRaises(ContractError): GatePolicy(max_changed_files=-1)
    def test_policy_round_trip(self):
        item = policy(max_changed_lines=10); self.assertEqual(GatePolicy.from_dict(item.to_dict()), item)
    def test_check_required_must_be_boolean(self):
        with self.assertRaises(ContractError): Check("x", CheckState.SUCCESS, 1, "ok")
    def test_canonical_json_is_stable(self): self.assertEqual(canonical_json({"b": 2, "a": 1}), '{"a":1,"b":2}')
    def test_sha_json_is_order_independent(self): self.assertEqual(sha256_json({"a": 1, "b": 2}), sha256_json({"b": 2, "a": 1}))
    def test_artifact_round_trip_and_sha(self):
        artifact = evaluate(snapshot(), generated_at=NOW); restored = GateArtifact.from_dict(artifact.to_dict())
        self.assertEqual(restored, artifact); self.assertEqual(restored.sha256, artifact.to_dict()["artifact_sha256"])
    def test_artifact_tampering_rejected(self):
        value = evaluate(snapshot(), generated_at=NOW).to_dict(); value["decision"] = "blocked"
        with self.assertRaisesRegex(ContractError, "canonical content"): GateArtifact.from_dict(value)
    def test_artifact_summary_tampering_rejected(self):
        value = evaluate(snapshot(), generated_at=NOW).to_dict(); value["inventory_sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "canonical"): GateArtifact.from_dict(value)
    def test_ready_with_failed_required_check_rejected(self):
        good = evaluate(snapshot(), generated_at=NOW); bad = Check("x", CheckState.FAILURE, True, "failed")
        with self.assertRaisesRegex(ContractError, "ready"): GateArtifact(Decision.READY, good.snapshot, good.policy, (bad,), NOW, {})
    def test_unknown_tool_version_rejected(self):
        good = evaluate(snapshot(), generated_at=NOW)
        with self.assertRaisesRegex(ContractError, "tool_version"): GateArtifact(good.decision, good.snapshot, good.policy, good.checks, NOW, {}, tool_version="9")


if __name__ == "__main__": unittest.main()
