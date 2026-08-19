import unittest

import safe_merge_gate
import shipcheck


class CompatibilityAliasesTests(unittest.TestCase):
    def test_legacy_public_api_is_preserved_at_canonical_root(self):
        self.assertEqual(shipcheck.__version__, safe_merge_gate.__version__)
        self.assertTrue(set(safe_merge_gate.__all__).issubset(set(shipcheck.__all__)))
        self.assertIn("release_gate", shipcheck.__all__)
        for name in safe_merge_gate.__all__:
            self.assertIs(getattr(shipcheck, name), getattr(safe_merge_gate, name))

    def test_legacy_cli_remains_available_behind_dispatcher(self):
        from safe_merge_gate.cli import main as legacy_main
        from shipcheck.cli import main as canonical_main

        self.assertIsNot(canonical_main, legacy_main)
        self.assertEqual(0, canonical_main(["probe", "liveness"]))
        self.assertEqual(0, canonical_main(["merge-gate", "probe", "liveness"]))


if __name__ == "__main__":
    unittest.main()
