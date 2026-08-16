import unittest

from pr_review_council.models import (
    FileChange,
    Finding,
    PullRequestSnapshot,
    Severity,
    ValidationError,
    digest,
    severity_counts,
)


def valid_input():
    return {
        "pr_id": "pr-7",
        "commit_sha": "a" * 40,
        "title": "Bounded change",
        "body": "Synthetic",
        "files": [{"path": "src/app.py", "patch": "+print('ok')\n", "additions": 1, "deletions": 0}],
    }


class PullRequestSnapshotTests(unittest.TestCase):
    def test_valid_snapshot_round_trip(self):
        snapshot = PullRequestSnapshot.from_dict(valid_input())
        self.assertEqual(snapshot.pr_id, "pr-7")
        self.assertEqual(snapshot.files[0].path, "src/app.py")
        self.assertEqual(snapshot.to_dict()["commit_sha"], "a" * 40)

    def test_sha_is_normalized_to_lowercase(self):
        data = valid_input()
        data["commit_sha"] = "A" * 40
        self.assertEqual(PullRequestSnapshot.from_dict(data).commit_sha, "a" * 40)

    def test_invalid_sha_is_rejected(self):
        data = valid_input()
        data["commit_sha"] = "not-a-sha"
        with self.assertRaisesRegex(ValidationError, "commit_sha"):
            PullRequestSnapshot.from_dict(data)

    def test_empty_files_are_rejected(self):
        data = valid_input()
        data["files"] = []
        with self.assertRaisesRegex(ValidationError, "non-empty"):
            PullRequestSnapshot.from_dict(data)

    def test_duplicate_paths_are_rejected(self):
        data = valid_input()
        data["files"] *= 2
        with self.assertRaisesRegex(ValidationError, "unique"):
            PullRequestSnapshot.from_dict(data)

    def test_parent_and_git_paths_are_rejected(self):
        for path in ("../secret", "/tmp/file", ".git/config", "src\\app.py"):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                FileChange.from_dict({"path": path, "patch": ""})

    def test_negative_counts_are_rejected(self):
        with self.assertRaisesRegex(ValidationError, "non-negative"):
            FileChange.from_dict({"path": "x.py", "patch": "", "additions": -1})

    def test_patch_size_is_bounded(self):
        with self.assertRaisesRegex(ValidationError, "exceeds"):
            FileChange.from_dict({"path": "x.py", "patch": "x" * 256_001})


class FindingTests(unittest.TestCase):
    def test_fingerprint_is_deterministic(self):
        kwargs = dict(
            rule_id="SEC001", reviewer="security", severity=Severity.HIGH,
            title="Risk", message="Fix it", path="src/a.py", line=3,
        )
        self.assertEqual(Finding.create(**kwargs).fingerprint, Finding.create(**kwargs).fingerprint)

    def test_invalid_line_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "positive"):
            Finding.create(
                rule_id="X", reviewer="r", severity=Severity.LOW,
                title="t", message="m", line=0,
            )

    def test_severity_counts_are_complete(self):
        finding = Finding.create(
            rule_id="X", reviewer="r", severity=Severity.LOW,
            title="t", message="m",
        )
        counts = severity_counts([finding])
        self.assertEqual(counts["low"], 1)
        self.assertEqual(counts["critical"], 0)

    def test_digest_ignores_mapping_insertion_order(self):
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))


if __name__ == "__main__":
    unittest.main()
