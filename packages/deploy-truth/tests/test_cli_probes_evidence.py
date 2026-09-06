from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from deploy_truth.cli import run
from deploy_truth.evidence import verify_evidence_document
from deploy_truth.fixtures import SyntheticFixture
from deploy_truth.io import write_json_atomic
from deploy_truth.models import ContractError, Decision
from deploy_truth.probes import functional_probe, liveness_probe, readiness_probe


ROOT = Path(__file__).resolve().parents[1]


def call_cli(arguments: list[str]) -> tuple[int, dict]:
    output = StringIO()
    with redirect_stdout(output):
        code = run(arguments)
    return code, json.loads(output.getvalue())


class ProbeTests(unittest.TestCase):
    def test_liveness(self) -> None:
        self.assertTrue(liveness_probe().healthy)

    def test_readiness(self) -> None:
        self.assertTrue(readiness_probe().healthy)

    def test_functional_counterproof(self) -> None:
        result = functional_probe()
        self.assertTrue(result.healthy)
        self.assertTrue(all(check["passed"] for check in result.checks))
        names = {check["name"] for check in result.checks}
        self.assertIn("byte_drift_not_success", names)
        self.assertIn("partial_release_blocked", names)

    def test_functional_is_reproducible(self) -> None:
        self.assertEqual(functional_probe().to_dict(), functional_probe().to_dict())


class EvidenceTests(unittest.TestCase):
    def report(self) -> dict:
        return SyntheticFixture.load(ROOT / "examples/exact-release.json").verify().to_dict()

    def test_valid_evidence(self) -> None:
        report = self.report()
        self.assertEqual(verify_evidence_document(report), report["evidence_sha256"])

    def test_tampered_artifact_hash_rejected(self) -> None:
        report = self.report()
        report["live"]["artifacts"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "inventory hash"):
            verify_evidence_document(report)

    def test_tampered_decision_rejected(self) -> None:
        report = self.report()
        report["decision"] = "degraded"
        with self.assertRaisesRegex(ContractError, "evidence_sha256"):
            verify_evidence_document(report)

    def test_unknown_field_rejected(self) -> None:
        report = self.report()
        report["host"] = "synthetic"
        with self.assertRaises(ContractError):
            verify_evidence_document(report)


class CliTests(unittest.TestCase):
    def test_exact_fixture_exit_zero(self) -> None:
        code, output = call_cli(["fixture", str(ROOT / "examples/exact-release.json")])
        self.assertEqual(code, 0)
        self.assertEqual(output["decision"], "verified")

    def test_fixture_output_then_verify_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "truth.json"
            self.assertEqual(call_cli([
                "fixture", str(ROOT / "examples/exact-release.json"), "--output", str(path)
            ])[0], 0)
            code, output = call_cli(["verify-evidence", str(path)])
            self.assertEqual(code, 0)
            self.assertTrue(output["valid"])

    def test_invalid_evidence_returns_blocked_contract_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{}", encoding="utf-8")
            code, output = call_cli(["verify-evidence", str(path)])
            self.assertEqual(code, 4)
            self.assertEqual(output["decision"], "blocked")

    def test_probe_cli(self) -> None:
        code, output = call_cli(["probe", "functional"])
        self.assertEqual(code, 0)
        self.assertTrue(output["healthy"])

    def test_demo_apply_verify_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, output = call_cli(["demo", str(Path(directory) / "demo")])
            self.assertEqual(code, 0)
            self.assertEqual(output["apply"]["decision"], "verified")
            self.assertEqual(output["verify"]["decision"], "verified")
            self.assertEqual(output["rollback"]["decision"], "verified")
            self.assertEqual(output["before_decision"], "blocked")
            self.assertEqual(output["restored_decision"], "blocked")


if __name__ == "__main__":
    unittest.main()

