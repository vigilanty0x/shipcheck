import unittest

from pr_review_council.probes import functional_probe, inventory, liveness_probe, readiness_probe


class ProbeTests(unittest.TestCase):
    def test_liveness_only_proves_process_and_version(self):
        result = liveness_probe()
        self.assertEqual(result["status"], "alive")
        self.assertEqual(result["version"], "0.1.0")

    def test_readiness_proves_reviewer_inventory(self):
        result = readiness_probe()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["reviewers"]), 4)

    def test_functional_probe_requires_counter_proof_to_block(self):
        result = functional_probe()
        self.assertEqual(result["status"], "proven")
        self.assertTrue(result["counter_proof_triggered"])
        self.assertEqual(result["observed_decision"], "blocked")

    def test_inventory_is_canonical_and_dependency_free(self):
        result = inventory()
        self.assertEqual(result["runtime_dependencies"], [])
        self.assertIn("rolled_back", result["states"])
        self.assertEqual(result["schema_versions"]["report"], "1.0")


if __name__ == "__main__":
    unittest.main()
