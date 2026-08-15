from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from safe_merge_gate.cli import main
from safe_merge_gate.probes import functional_counter_proof, liveness, readiness
from helpers import BASE, MERGE, NOW

ROOT = Path(__file__).resolve().parents[1]


class ProbeTests(unittest.TestCase):
    def test_liveness(self): self.assertTrue(liveness()["ok"])
    def test_readiness(self):
        with TemporaryDirectory() as directory: self.assertTrue(readiness(directory)["ok"])
    def test_functional_counter_proof(self):
        result = functional_counter_proof()
        self.assertTrue(result["ok"]); self.assertEqual(result["ready_decision"], "ready")
        self.assertEqual(result["counter_proof_decision"], "blocked")
        self.assertTrue(result["dry_run_unchanged"]); self.assertTrue(result["apply_verified"])
        self.assertTrue(result["rollback_exact"]); self.assertTrue(result["blocked_apply_rejected"])


class CliTests(unittest.TestCase):
    def run_cli(self, args):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error): code = main(args)
        return code, output.getvalue(), error.getvalue()

    def test_inventory(self):
        code, output, _ = self.run_cli(["inventory", "--snapshot", str(ROOT / "examples/ready-snapshot.json")])
        value = json.loads(output); self.assertEqual(code, 0); self.assertEqual(value["files"], 2); self.assertEqual(value["changed_lines"], 22)

    def test_ready_evaluate_writes_evidence(self):
        with TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.json"
            code, output, error = self.run_cli(["evaluate", "--snapshot", str(ROOT / "examples/ready-snapshot.json"), "--policy", str(ROOT / "examples/policy.json"), "--evidence", str(evidence), "--generated-at", NOW])
            self.assertEqual(code, 0, error); self.assertTrue(evidence.is_file()); self.assertEqual(json.loads(output)["decision"], "ready")

    def test_blocked_evaluate_returns_two(self):
        code, output, _ = self.run_cli(["evaluate", "--snapshot", str(ROOT / "examples/blocked-snapshot.json"), "--generated-at", NOW])
        self.assertEqual(code, 2); self.assertEqual(json.loads(output)["decision"], "blocked")

    def test_full_cli_transaction_and_exact_rollback(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); evidence = root / "evidence.json"; state = root / "state.json"; receipt = root / "receipt.json"
            original = (ROOT / "examples/local-state.json").read_bytes(); state.write_bytes(original)
            self.assertEqual(self.run_cli(["evaluate", "--snapshot", str(ROOT / "examples/ready-snapshot.json"), "--evidence", str(evidence), "--generated-at", NOW])[0], 0)
            self.assertEqual(self.run_cli(["dry-run", "--evidence", str(evidence), "--state", str(state)])[0], 0)
            self.assertEqual(state.read_bytes(), original)
            self.assertEqual(self.run_cli(["apply", "--evidence", str(evidence), "--state", str(state), "--receipt", str(receipt), "--created-at", NOW])[0], 0)
            self.assertEqual(json.loads(state.read_text())["current_sha"], MERGE)
            self.assertEqual(self.run_cli(["verify", "--receipt", str(receipt), "--state", str(state)])[0], 0)
            self.assertEqual(self.run_cli(["rollback", "--receipt", str(receipt), "--state", str(state)])[0], 0)
            self.assertEqual(state.read_bytes(), original)

    def test_inapplicable_dry_run_returns_two(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); evidence = root / "e.json"; state = root / "state.json"
            state.write_text(json.dumps({"current_sha": "9" * 40}))
            self.run_cli(["evaluate", "--snapshot", str(ROOT / "examples/ready-snapshot.json"), "--evidence", str(evidence), "--generated-at", NOW])
            code, output, _ = self.run_cli(["dry-run", "--evidence", str(evidence), "--state", str(state)])
            self.assertEqual(code, 2); self.assertFalse(json.loads(output)["applicable"])

    def test_apply_blocked_artifact_is_structured_error(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); evidence = root / "e.json"; state = root / "state.json"
            state.write_text(json.dumps({"current_sha": BASE}))
            self.run_cli(["evaluate", "--snapshot", str(ROOT / "examples/blocked-snapshot.json"), "--evidence", str(evidence), "--generated-at", NOW])
            code, _, error = self.run_cli(["apply", "--evidence", str(evidence), "--state", str(state), "--receipt", str(root / "r.json")])
            self.assertEqual(code, 1); self.assertFalse(json.loads(error)["success"])

    def test_tampered_evidence_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); evidence = root / "e.json"
            self.run_cli(["evaluate", "--snapshot", str(ROOT / "examples/ready-snapshot.json"), "--evidence", str(evidence), "--generated-at", NOW])
            value = json.loads(evidence.read_text()); value["decision"] = "blocked"; evidence.write_text(json.dumps(value))
            code, _, error = self.run_cli(["dry-run", "--evidence", str(evidence), "--state", str(ROOT / "examples/local-state.json")])
            self.assertEqual(code, 1); self.assertEqual(json.loads(error)["error"], "ContractError")

    def test_invalid_json_structured_error(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad"; path.write_text("not-json")
            code, _, error = self.run_cli(["inventory", "--snapshot", str(path)])
            self.assertEqual(code, 1); self.assertFalse(json.loads(error)["success"])

    def test_non_object_input_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad"; path.write_text("[]")
            code, _, error = self.run_cli(["inventory", "--snapshot", str(path)])
            self.assertEqual(code, 1); self.assertEqual(json.loads(error)["error"], "ContractError")

    def test_oversize_input_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "large"; path.write_text(" " * 1_000_001)
            code, _, error = self.run_cli(["inventory", "--snapshot", str(path)])
            self.assertEqual(code, 1); self.assertIn("exceeds", json.loads(error)["message"])

    def test_probe_cli(self):
        code, output, _ = self.run_cli(["probe", "functional"]); self.assertEqual(code, 0); self.assertTrue(json.loads(output)["ok"])


if __name__ == "__main__": unittest.main()
