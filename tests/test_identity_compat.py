from __future__ import annotations

import unittest

import safe_merge_gate
import shipcheck
from shipcheck import merge_gate, release_gate
from shipcheck import cli as canonical_cli


class IdentityCompatibilityTests(unittest.TestCase):
    def test_canonical_api_is_release_gate_api(self) -> None:
        self.assertIs(shipcheck.DecisionEngine, release_gate.DecisionEngine)
        self.assertIs(shipcheck.DecisionLedger, release_gate.DecisionLedger)
        self.assertEqual(shipcheck.__version__, release_gate.__version__)

    def test_merge_gate_legacy_import_remains_explicit_and_identical(self) -> None:
        self.assertIs(merge_gate.evaluate, safe_merge_gate.evaluate)
        self.assertEqual(merge_gate.__version__, safe_merge_gate.__version__)
        self.assertEqual(tuple(merge_gate.__all__), tuple(safe_merge_gate.__all__))

    def test_unified_cli_has_disjoint_release_dispatch(self) -> None:
        self.assertIn("selftest", canonical_cli.RELEASE_COMMANDS)
        self.assertIn("decide", canonical_cli.RELEASE_COMMANDS)
        self.assertNotIn("evaluate", canonical_cli.RELEASE_COMMANDS)
        self.assertNotIn("probe", canonical_cli.RELEASE_COMMANDS)


if __name__ == "__main__":
    unittest.main()
