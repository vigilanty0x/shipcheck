import importlib
import unittest

import shipcheck
from shipcheck import release_gate


class ReleaseGateNamespaceTests(unittest.TestCase):
    def test_namespace_is_exposed_without_replacing_legacy_types(self):
        self.assertIs(shipcheck.release_gate, release_gate)
        self.assertTrue(hasattr(release_gate, "DecisionEngine"))
        self.assertTrue(hasattr(release_gate, "evaluate_release"))
        self.assertTrue(hasattr(release_gate, "DecisionLedger"))
        self.assertTrue(hasattr(release_gate, "verify_receipt"))
        self.assertTrue(hasattr(shipcheck, "evaluate"))
        self.assertIsNot(shipcheck.Decision, release_gate.Decision)

    def test_historical_release_gate_module_imports_resolve(self):
        for name in (
            "adapters",
            "api",
            "artifacts",
            "canonical",
            "demo",
            "engine",
            "errors",
            "ledger",
            "limits",
            "models",
            "receipt",
            "redaction",
            "report",
            "risk",
            "secureio",
            "selftest",
            "trust",
        ):
            legacy = importlib.import_module(f"shipcheck.{name}")
            absorbed = importlib.import_module(f"shipcheck.release_gate.{name}")
            self.assertIs(legacy, absorbed)


if __name__ == "__main__":
    unittest.main()
