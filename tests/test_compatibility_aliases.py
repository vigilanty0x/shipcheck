import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import safe_merge_gate
import shipcheck


class CompatibilityAliasesTests(unittest.TestCase):
    def test_public_api_is_preserved(self):
        self.assertEqual(shipcheck.__version__, safe_merge_gate.__version__)
        self.assertEqual(set(shipcheck.__all__) - set(safe_merge_gate.__all__), {'release_gate'})
        self.assertTrue(set(safe_merge_gate.__all__) <= set(shipcheck.__all__))
        for name in safe_merge_gate.__all__:
            self.assertIs(getattr(shipcheck, name), getattr(safe_merge_gate, name))
        self.assertTrue(callable(shipcheck.release_gate.DecisionEngine))
        self.assertIsNot(shipcheck.release_gate.Decision, shipcheck.Decision)

    def capture(self, main, args):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(args)
        return code, output.getvalue(), error.getvalue()

    def test_cli_preserves_legacy_commands_outputs_and_exit_codes(self):
        from safe_merge_gate.cli import main as legacy_main
        from shipcheck.cli import main as canonical_main
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as directory:
            bad = Path(directory) / 'bad.json'; bad.write_text('[]', encoding='utf-8')
            cases = [
                (['probe', 'liveness'], 0),
                (['inventory', '--snapshot', str(root/'examples/ready-snapshot.json')], 0),
                (['evaluate', '--snapshot', str(root/'examples/ready-snapshot.json'), '--generated-at', '2026-01-01T00:00:00Z'], 0),
                (['evaluate', '--snapshot', str(root/'examples/blocked-snapshot.json'), '--generated-at', '2026-01-01T00:00:00Z'], 2),
                (['inventory', '--snapshot', str(bad)], 1),
            ]
            for args, expected in cases:
                with self.subTest(command=args[0], expected=expected):
                    legacy = self.capture(legacy_main, args)
                    self.assertEqual(legacy[0], expected)
                    self.assertEqual(self.capture(canonical_main, args), legacy)
                    self.assertEqual(self.capture(canonical_main, ['merge-gate', *args]), legacy)

    def test_both_entries_preserve_physical_apply_verify_and_exact_rollback(self):
        from safe_merge_gate.cli import main as legacy_main
        from shipcheck.cli import main as canonical_main
        root = Path(__file__).resolve().parents[1]
        for main, prefix in [(legacy_main, []), (canonical_main, []), (canonical_main, ['merge-gate'])]:
            with self.subTest(entry=main.__module__, prefix=prefix), TemporaryDirectory() as directory:
                base = Path(directory)
                evidence, state, receipt = (base/name for name in ('evidence.json', 'state.json', 'receipt.json'))
                original = (root/'examples/local-state.json').read_bytes(); state.write_bytes(original)
                def call(args):
                    code, out, err = self.capture(main, [*prefix, *args])
                    self.assertEqual(code, 0, err)
                    return json.loads(out)
                call(['evaluate', '--snapshot', str(root/'examples/ready-snapshot.json'), '--evidence', str(evidence), '--generated-at', '2026-01-01T00:00:00Z'])
                self.assertTrue(call(['dry-run', '--evidence', str(evidence), '--state', str(state)])['applicable'])
                self.assertEqual(state.read_bytes(), original)
                call(['apply', '--evidence', str(evidence), '--state', str(state), '--receipt', str(receipt), '--created-at', '2026-01-01T00:00:00Z'])
                self.assertNotEqual(state.read_bytes(), original)
                self.assertTrue(call(['verify', '--receipt', str(receipt), '--state', str(state)])['verified'])
                self.assertTrue(call(['rollback', '--receipt', str(receipt), '--state', str(state)])['rolled_back'])
                self.assertEqual(state.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
