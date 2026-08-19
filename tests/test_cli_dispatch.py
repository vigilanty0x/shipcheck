import contextlib
import io
import unittest

from shipcheck.cli import main


class UnifiedCliDispatchTests(unittest.TestCase):
    def test_merge_gate_command_family_remains_available(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["probe", "liveness"])
        self.assertEqual(0, rc)
        self.assertIn('"ok":true', out.getvalue().replace(" ", ""))

    def test_release_gate_command_family_is_available(self):
        out = io.BytesIO()
        wrapper = io.TextIOWrapper(out, encoding="utf-8")
        with contextlib.redirect_stdout(wrapper):
            rc = main(["capabilities"])
            wrapper.flush()
        self.assertEqual(0, rc)
        self.assertIn(b'"schema_version":"shipcheck/capabilities-v1"', out.getvalue())

    def test_explicit_release_gate_prefix_dispatches(self):
        out = io.BytesIO()
        wrapper = io.TextIOWrapper(out, encoding="utf-8")
        with contextlib.redirect_stdout(wrapper):
            rc = main(["release-gate", "capabilities"])
            wrapper.flush()
        self.assertEqual(0, rc)


if __name__ == "__main__":
    unittest.main()
