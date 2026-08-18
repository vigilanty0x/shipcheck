from __future__ import annotations

import unittest

import safe_merge_gate
import safe_merge_gate.cli
import shipcheck
import shipcheck.cli


class IdentityCompatibilityTests(unittest.TestCase):
    def test_canonical_api_reexports_legacy_core(self) -> None:
        self.assertIs(shipcheck.evaluate, safe_merge_gate.evaluate)
        self.assertEqual(shipcheck.__version__, safe_merge_gate.__version__)
        self.assertEqual(tuple(shipcheck.__all__), tuple(safe_merge_gate.__all__))

    def test_canonical_cli_delegates_to_legacy_core(self) -> None:
        self.assertIs(shipcheck.cli.main, safe_merge_gate.cli.main)


if __name__ == "__main__":
    unittest.main()
