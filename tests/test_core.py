import unittest

from diff_risk_scorer import probe, score

BASE = {"path": "src/a", "additions": 1, "deletions": 0}


class Tests(unittest.TestCase):
    def test_low_and_sensitive(self):
        self.assertEqual(score([BASE])["band"], "low")
        self.assertGreaterEqual(score([{**BASE, "sensitive": True}])["score"], 30)

    def test_bool_is_not_count_and_flags_are_strict(self):
        for item in ({**BASE, "additions": True}, {**BASE, "deletions": False},
                     {**BASE, "sensitive": 1}, {**BASE, "binary": "yes"}):
            self.assertFalse(score([item])["ok"])

    def test_paths_entries_and_bounds(self):
        self.assertFalse(score([{**BASE, "path": "../x"}])["ok"])
        self.assertFalse(score([BASE, BASE])["ok"])
        self.assertFalse(score([{**BASE, "additions": 1_000_001}])["ok"])
        self.assertFalse(score(None)["ok"])

    def test_probe(self):
        self.assertTrue(probe()["ok"])


if __name__ == "__main__":
    unittest.main()
