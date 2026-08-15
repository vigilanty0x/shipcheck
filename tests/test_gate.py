import unittest

from safe_merge_gate.contract import Change, CheckState, Decision
from safe_merge_gate.gate import evaluate
from helpers import NOW, finding, policy, snapshot


class GateTests(unittest.TestCase):
    def evaluate(self, **changes): return evaluate(snapshot(**changes), generated_at=NOW)
    def test_nominal_ready(self):
        item = self.evaluate(); self.assertEqual(item.decision, Decision.READY); self.assertTrue(item.ready)
    def test_expected_observed_mismatch_blocked(self):
        item = self.evaluate(observed_sha="3" * 40); self.assertEqual(item.decision, Decision.BLOCKED); self.assertFalse(item.ready)
    def test_required_ci_failure_blocked(self):
        item = self.evaluate(ci={"build": CheckState.FAILURE, "test": CheckState.SUCCESS, "style": CheckState.SUCCESS})
        self.assertEqual(item.decision, Decision.BLOCKED)
    def test_required_ci_pending_blocked(self):
        self.assertEqual(self.evaluate(ci={"build": CheckState.PENDING, "test": CheckState.SUCCESS}).decision, Decision.BLOCKED)
    def test_required_ci_missing_blocked(self):
        item = self.evaluate(ci={"test": CheckState.SUCCESS}); self.assertEqual(item.decision, Decision.BLOCKED)
        self.assertEqual(next(c for c in item.checks if c.name == "ci:build").state, CheckState.MISSING)
    def test_optional_ci_failure_degraded(self):
        item = self.evaluate(ci={"build": CheckState.SUCCESS, "test": CheckState.SUCCESS, "style": CheckState.FAILURE})
        self.assertEqual(item.decision, Decision.DEGRADED); self.assertFalse(item.ready)
    def test_optional_ci_missing_degraded(self):
        self.assertEqual(self.evaluate(ci={"build": CheckState.SUCCESS, "test": CheckState.SUCCESS}).decision, Decision.DEGRADED)
    def test_incomplete_tests_blocked(self): self.assertEqual(self.evaluate(tests_complete=False).decision, Decision.BLOCKED)
    def test_failed_tests_blocked(self): self.assertEqual(self.evaluate(tests_passed=False).decision, Decision.BLOCKED)
    def test_incomplete_secret_scan_blocked(self): self.assertEqual(self.evaluate(secret_scan_complete=False).decision, Decision.BLOCKED)
    def test_secret_finding_blocked(self):
        item = self.evaluate(secret_findings=(finding(),)); self.assertEqual(item.decision, Decision.BLOCKED)
        self.assertEqual(next(c for c in item.checks if c.name == "secrets").evidence["finding_count"], 1)
    def test_dirty_tree_blocked(self): self.assertEqual(self.evaluate(clean_tree=False).decision, Decision.BLOCKED)
    def test_file_limit_blocked(self): self.assertEqual(evaluate(snapshot(), policy(max_changed_files=1), generated_at=NOW).decision, Decision.BLOCKED)
    def test_line_limit_blocked(self): self.assertEqual(evaluate(snapshot(), policy(max_changed_lines=21), generated_at=NOW).decision, Decision.BLOCKED)
    def test_line_limit_is_inclusive(self): self.assertEqual(evaluate(snapshot(), policy(max_changed_lines=22), generated_at=NOW).decision, Decision.READY)
    def test_binary_limit_blocked(self):
        item = snapshot(changes=(Change("a.bin", 0, 0, True),))
        self.assertEqual(evaluate(item, policy(max_binary_files=0), generated_at=NOW).decision, Decision.BLOCKED)
    def test_optional_tests_failure_degraded(self):
        self.assertEqual(evaluate(snapshot(tests_passed=False), policy(require_tests=False), generated_at=NOW).decision, Decision.DEGRADED)
    def test_optional_secret_scan_failure_degraded(self):
        self.assertEqual(evaluate(snapshot(secret_scan_complete=False), policy(require_secret_scan=False), generated_at=NOW).decision, Decision.DEGRADED)
    def test_optional_clean_tree_failure_degraded(self):
        self.assertEqual(evaluate(snapshot(clean_tree=False), policy(require_clean_tree=False), generated_at=NOW).decision, Decision.DEGRADED)
    def test_outputs_count_failures(self):
        artifact = self.evaluate(observed_sha="3" * 40, tests_passed=False)
        self.assertEqual(artifact.outputs["required_failures"], 2); self.assertEqual(artifact.outputs["optional_failures"], 0)
    def test_failure_checks_never_success(self):
        failure = next(c for c in self.evaluate(tests_passed=False).checks if c.name == "tests"); self.assertFalse(failure.success)
    def test_reproducible_evidence(self): self.assertEqual(self.evaluate().to_dict(), self.evaluate().to_dict())


if __name__ == "__main__": unittest.main()
