"""The public protocol exception does not exempt private markers on its line."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('shipcheck_public_boundary', Path(__file__).resolve().parents[1]/'scripts/check.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class BoundaryProtocolTests(unittest.TestCase):
    def test_current_public_tree_satisfies_boundary_and_syntax(self):
        self.assertEqual(checker.main(), 0)

    def test_exact_quoted_protocol_is_the_only_exception(self):
        for quote in ('"', "'", '`'):
            with self.subTest(quote=quote):
                self.assertEqual(checker.boundary_violations(quote+checker.PUBLIC_WIRE_SCHEMA+quote), [])
        self.assertTrue(checker.boundary_violations(checker.PUBLIC_WIRE_SCHEMA))
        for variant in ('prefix'+checker.PUBLIC_WIRE_SCHEMA, checker.PUBLIC_WIRE_SCHEMA+'.extra', checker.PUBLIC_WIRE_SCHEMA.upper()):
            with self.subTest(variant=variant):
                self.assertTrue(checker.boundary_violations('"'+variant+'"'))

    def test_same_line_private_markers_are_still_refused(self):
        for marker in checker.FORBIDDEN:
            with self.subTest(marker=marker):
                self.assertTrue(checker.boundary_violations('"'+checker.PUBLIC_WIRE_SCHEMA+'"; '+marker))

    def test_personal_paths_are_refused_even_beside_public_protocol(self):
        paths = ['C:'+separator+'Users'+separator+'example' for separator in ('/', '\\', '\\\\')]
        paths += ['/'+folder+'/'+'example' for folder in ('home', 'Users')]
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(checker.boundary_violations('`'+checker.PUBLIC_WIRE_SCHEMA+'` '+path))
