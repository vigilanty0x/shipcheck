from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from pr_review_council.cli import main


def snapshot_data():
    return {
        "pr_id": "cli-1",
        "commit_sha": "e" * 40,
        "title": "CLI fixture",
        "body": "",
        "files": [
            {"path": "src/x.py", "patch": "+x = 1", "additions": 1},
            {"path": "tests/test_x.py", "patch": "+assert x == 1", "additions": 1},
        ],
    }


def invoke(argv):
    output = StringIO()
    with redirect_stdout(output):
        code = main(argv)
    return code, json.loads(output.getvalue())


class CliTests(unittest.TestCase):
    def test_review_prints_structured_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "pr.json"
            source.write_text(json.dumps(snapshot_data()), encoding="utf-8")
            code, result = invoke(["review", "--input", str(source)])
            self.assertEqual(code, 0)
            self.assertEqual(result["decision"], "approved")

    def test_fail_on_gate_has_distinct_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "pr.json"
            data = snapshot_data()
            data["files"] = [data["files"][0]]
            source.write_text(json.dumps(data), encoding="utf-8")
            code, result = invoke(["review", "--input", str(source), "--fail-on-gate"])
            self.assertEqual(code, 3)
            self.assertEqual(result["decision"], "changes_requested")

    def test_plan_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "pr.json"
            output = Path(tmp) / "report.json"
            source.write_text(json.dumps(snapshot_data()), encoding="utf-8")
            code, result = invoke(["plan", "--input", str(source), "--output", str(output)])
            self.assertEqual(code, 0)
            self.assertTrue(result["dry_run"])
            self.assertFalse(output.exists())

    def test_publish_verify_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "pr.json"
            output = Path(tmp) / "report.json"
            receipt = Path(tmp) / "receipt.json"
            source.write_text(json.dumps(snapshot_data()), encoding="utf-8")
            self.assertEqual(invoke(["publish", "--input", str(source), "--output", str(output), "--receipt", str(receipt)])[0], 0)
            self.assertEqual(invoke(["verify", "--receipt", str(receipt)])[1]["state"], "verified")
            code, result = invoke(["rollback", "--receipt", str(receipt), "--yes"])
            self.assertEqual(code, 0)
            self.assertEqual(result["state"], "rolled_back")
            self.assertFalse(output.exists())

    def test_rollback_requires_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "receipt.json"
            receipt.write_text("{}", encoding="utf-8")
            code, result = invoke(["rollback", "--receipt", str(receipt)])
            self.assertEqual(code, 2)
            self.assertIn("--yes", result["error"])

    def test_invalid_json_is_bounded_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "pr.json"
            source.write_text("{broken", encoding="utf-8")
            code, result = invoke(["review", "--input", str(source)])
            self.assertEqual(code, 2)
            self.assertEqual(result["type"], "ValidationError")
            self.assertLess(len(result["error"]), 1_000)

    def test_functional_probe(self):
        code, result = invoke(["probe", "--level", "functional"])
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "proven")

    def test_demo_exercises_rollback_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, result = invoke(["demo", "--workspace", tmp])
            self.assertEqual(code, 0)
            self.assertTrue(result["rollback_restored_previous"])
            self.assertTrue(result["replay_verified"])
            self.assertTrue(Path(tmp, "review-report.json").is_file())


if __name__ == "__main__":
    unittest.main()
