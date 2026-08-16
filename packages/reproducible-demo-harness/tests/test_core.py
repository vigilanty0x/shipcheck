import hashlib
from pathlib import Path
import tempfile
import unittest

from reproducible_demo_harness import evaluate


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = b"deterministic output\n"
        (self.root / "result.txt").write_bytes(self.data)
        self.good = {"artifact_path": "result.txt", "expected_sha256": hashlib.sha256(self.data).hexdigest()}

    def tearDown(self):
        self.temp.cleanup()

    def test_hashes_real_artifact_without_execution(self):
        result = evaluate(self.good, allowed_root=self.root)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["verification"]["matched"])
        self.assertFalse(result["verification"]["executed"])

    def test_caller_supplied_actual_digest_is_rejected(self):
        self.assertEqual(evaluate({**self.good, "actual_sha256": self.good["expected_sha256"]}, allowed_root=self.root)["status"], "failed")

    def test_digest_mismatch_fails(self):
        self.assertEqual(evaluate({**self.good, "expected_sha256": "a" * 64}, allowed_root=self.root)["status"], "failed")

    def test_traversal_outside_allowed_root_fails(self):
        outside = self.root.parent / "outside-demo.txt"
        outside.write_bytes(self.data)
        try:
            self.assertEqual(evaluate({**self.good, "artifact_path": "../outside-demo.txt"}, allowed_root=self.root)["status"], "failed")
        finally:
            outside.unlink()

    def test_absolute_path_fails(self):
        self.assertEqual(evaluate({**self.good, "artifact_path": str(self.root / "result.txt")}, allowed_root=self.root)["status"], "failed")

    def test_symlink_fails(self):
        (self.root / "link.txt").symlink_to(self.root / "result.txt")
        self.assertEqual(evaluate({**self.good, "artifact_path": "link.txt"}, allowed_root=self.root)["status"], "failed")

    def test_non_object_and_missing_field_fail_closed(self):
        self.assertEqual(evaluate([], allowed_root=self.root)["status"], "failed")
        self.assertEqual(evaluate({}, allowed_root=self.root)["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
