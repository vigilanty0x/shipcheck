import unittest

from pr_review_council.models import FileChange, PullRequestSnapshot, Severity
from pr_review_council.reviewers import (
    MaintainabilityReviewer,
    ReliabilityReviewer,
    SecurityReviewer,
    TestingReviewer,
    added_lines,
)


def snapshot(files):
    return PullRequestSnapshot.from_dict({
        "pr_id": "pr-review",
        "commit_sha": "b" * 40,
        "title": "Synthetic review",
        "body": "",
        "files": files,
    })


class AddedLinesTests(unittest.TestCase):
    def test_tracks_target_line_numbers(self):
        change = FileChange("src/x.py", "@@ -9,2 +10,3 @@\n old\n+new\n-old2\n+new2\n", 2, 1)
        self.assertEqual(list(added_lines(change)), [(11, "new"), (12, "new2")])

    def test_ignores_diff_headers(self):
        change = FileChange("x", "--- a/x\n+++ b/x\n@@ -0,0 +1 @@\n+value\n", 1, 0)
        self.assertEqual(list(added_lines(change)), [(1, "value")])


class SecurityReviewerTests(unittest.TestCase):
    def test_secret_fixture_is_critical_and_not_echoed(self):
        pr = snapshot([{"path": "x.py", "patch": "+password = 'synthetic-password'", "additions": 1}])
        finding = SecurityReviewer().review(pr)[0]
        self.assertEqual(finding.severity, Severity.CRITICAL)
        self.assertNotIn("synthetic-password", finding.message)

    def test_shell_true_is_high(self):
        pr = snapshot([{"path": "x.py", "patch": "+subprocess.run(cmd, shell=True)", "additions": 1}])
        self.assertEqual(SecurityReviewer().review(pr)[0].rule_id, "SEC002")

    def test_safe_argument_vector_has_no_finding(self):
        pr = snapshot([{"path": "x.py", "patch": "+subprocess.run(['git', 'status'], check=True)", "additions": 1}])
        self.assertEqual(SecurityReviewer().review(pr), ())


class ReliabilityReviewerTests(unittest.TestCase):
    def test_network_call_without_timeout_is_found(self):
        pr = snapshot([{"path": "x.py", "patch": "+requests.get(url)", "additions": 1}])
        self.assertEqual(ReliabilityReviewer().review(pr)[0].rule_id, "REL001")

    def test_network_call_with_timeout_is_clear(self):
        pr = snapshot([{"path": "x.py", "patch": "+requests.get(url, timeout=5)", "additions": 1}])
        self.assertEqual(ReliabilityReviewer().review(pr), ())

    def test_bare_except_is_found(self):
        pr = snapshot([{"path": "x.py", "patch": "+except:\n+    raise", "additions": 2}])
        self.assertEqual(ReliabilityReviewer().review(pr)[0].rule_id, "REL002")


class TestingReviewerTests(unittest.TestCase):
    def test_source_without_test_requests_changes(self):
        pr = snapshot([{"path": "src/x.py", "patch": "+value = 1", "additions": 1}])
        self.assertEqual(TestingReviewer().review(pr)[0].rule_id, "TST001")

    def test_source_with_test_is_clear(self):
        pr = snapshot([
            {"path": "src/x.py", "patch": "+value = 1", "additions": 1},
            {"path": "tests/test_x.py", "patch": "+assert value == 1", "additions": 1},
        ])
        self.assertEqual(TestingReviewer().review(pr), ())

    def test_test_only_deletion_is_high(self):
        pr = snapshot([{"path": "tests/test_x.py", "patch": "-assert value", "deletions": 1}])
        self.assertEqual(TestingReviewer().review(pr)[0].severity, Severity.HIGH)


class MaintainabilityReviewerTests(unittest.TestCase):
    def test_large_change_is_found(self):
        pr = snapshot([{"path": "src/x.py", "patch": "+x", "additions": 601}])
        self.assertEqual(MaintainabilityReviewer().review(pr)[0].rule_id, "MNT001")

    def test_debt_marker_is_found(self):
        pr = snapshot([{"path": "src/x.py", "patch": "+# TODO track this", "additions": 1}])
        self.assertEqual(MaintainabilityReviewer().review(pr)[0].rule_id, "MNT002")


if __name__ == "__main__":
    unittest.main()
