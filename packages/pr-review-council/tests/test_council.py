import unittest

from pr_review_council.config import CouncilConfig
from pr_review_council.council import ReviewCouncil
from pr_review_council.models import Decision, Finding, PullRequestSnapshot, Severity, ValidationError
from pr_review_council.reviewers import default_reviewers


def clean_snapshot():
    return PullRequestSnapshot.from_dict({
        "pr_id": "pr-clean",
        "commit_sha": "c" * 40,
        "title": "Clean change",
        "body": "",
        "files": [
            {"path": "src/x.py", "patch": "+value = 1", "additions": 1},
            {"path": "tests/test_x.py", "patch": "+assert value == 1", "additions": 1},
        ],
    })


class FailingReviewer:
    name = "failing"

    def review(self, snapshot):
        raise RuntimeError("synthetic reviewer failure")


class InvalidReviewer:
    name = "invalid"

    def review(self, snapshot):
        return ["not a finding"]


class CriticalReviewer:
    name = "critical"

    def review(self, snapshot):
        return (Finding.create(
            rule_id="CRIT", reviewer=self.name, severity=Severity.CRITICAL,
            title="Critical", message="Synthetic counter-proof",
        ),)


class CouncilTests(unittest.TestCase):
    def test_clean_review_is_approved(self):
        report = ReviewCouncil().review(clean_snapshot())
        self.assertEqual(report.decision, Decision.APPROVED)
        self.assertFalse(report.degraded)
        self.assertEqual(report.summary["successful_reviewers"], 4)

    def test_medium_finding_requests_changes(self):
        data = clean_snapshot().to_dict()
        data["files"] = [data["files"][0]]
        report = ReviewCouncil().review(PullRequestSnapshot.from_dict(data))
        self.assertEqual(report.decision, Decision.CHANGES_REQUESTED)

    def test_critical_finding_blocks(self):
        config = CouncilConfig(enabled_reviewers=("critical",), minimum_successful_reviewers=1)
        report = ReviewCouncil(config, (CriticalReviewer(),)).review(clean_snapshot())
        self.assertEqual(report.decision, Decision.BLOCKED)

    def test_partial_failure_is_degraded_never_approved(self):
        reviewers = default_reviewers() + (FailingReviewer(),)
        config = CouncilConfig(
            enabled_reviewers=tuple(item.name for item in reviewers),
            minimum_successful_reviewers=3,
        )
        report = ReviewCouncil(config, reviewers).review(clean_snapshot())
        self.assertEqual(report.decision, Decision.DEGRADED)
        self.assertTrue(report.degraded)
        self.assertIn("RuntimeError", report.outcomes[-1].error)

    def test_quorum_failure_blocks(self):
        config = CouncilConfig(enabled_reviewers=("security", "failing"), minimum_successful_reviewers=2)
        report = ReviewCouncil(config, (default_reviewers()[0], FailingReviewer())).review(clean_snapshot())
        self.assertEqual(report.decision, Decision.BLOCKED)

    def test_invalid_reviewer_output_is_visible_failure(self):
        config = CouncilConfig(enabled_reviewers=("invalid",), minimum_successful_reviewers=1)
        report = ReviewCouncil(config, (InvalidReviewer(),)).review(clean_snapshot())
        self.assertEqual(report.decision, Decision.BLOCKED)
        self.assertEqual(report.summary["failed_reviewers"], 1)

    def test_report_sha_is_deterministic(self):
        council = ReviewCouncil()
        self.assertEqual(council.review(clean_snapshot()).report_sha, council.review(clean_snapshot()).report_sha)

    def test_findings_are_sorted_by_severity(self):
        data = clean_snapshot().to_dict()
        data["files"][0]["patch"] = "+password = 'synthetic-password'\n+# TODO track\n"
        report = ReviewCouncil().review(PullRequestSnapshot.from_dict(data))
        self.assertEqual(report.findings[0].severity, Severity.CRITICAL)

    def test_missing_enabled_reviewer_is_rejected(self):
        config = CouncilConfig(enabled_reviewers=("missing",), minimum_successful_reviewers=1)
        with self.assertRaisesRegex(ValidationError, "unavailable"):
            ReviewCouncil(config)

    def test_duplicate_reviewer_names_are_rejected(self):
        security = default_reviewers()[0]
        with self.assertRaisesRegex(ValidationError, "unique"):
            ReviewCouncil(CouncilConfig(enabled_reviewers=("security",), minimum_successful_reviewers=1), (security, security))


class ConfigTests(unittest.TestCase):
    def test_empty_reviewer_set_is_rejected(self):
        with self.assertRaises(ValidationError):
            CouncilConfig(enabled_reviewers=(), minimum_successful_reviewers=1)

    def test_quorum_must_fit_reviewer_set(self):
        with self.assertRaises(ValidationError):
            CouncilConfig(enabled_reviewers=("security",), minimum_successful_reviewers=2)


if __name__ == "__main__":
    unittest.main()
