import unittest

import safe_merge_gate
import shipcheck


class CompatibilityAliasesTests(unittest.TestCase):
    def test_public_api_is_preserved(self):
        self.assertEqual(shipcheck.__version__, safe_merge_gate.__version__)
        self.assertEqual(set(shipcheck.__all__), set(safe_merge_gate.__all__))
        for name in safe_merge_gate.__all__:
            self.assertIs(getattr(shipcheck, name), getattr(safe_merge_gate, name))

    def test_cli_alias_uses_same_main(self):
        from safe_merge_gate.cli import main as legacy_main
        from shipcheck.cli import main as canonical_main

        self.assertIs(canonical_main, legacy_main)


if __name__ == "__main__":
    unittest.main()
