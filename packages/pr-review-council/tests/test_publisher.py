import json
from pathlib import Path
import tempfile
import unittest

from pr_review_council.council import ReviewCouncil
from pr_review_council.models import PullRequestSnapshot, ValidationError
from pr_review_council.publisher import (
    PublicationError,
    ReportPublisher,
    TransactionReceipt,
    write_receipt,
)


def report(title="Publish"):
    snapshot = PullRequestSnapshot.from_dict({
        "pr_id": f"pr-{title.lower()}",
        "commit_sha": "d" * 40,
        "title": title,
        "body": "",
        "files": [
            {"path": "src/x.py", "patch": "+x = 1", "additions": 1},
            {"path": "tests/test_x.py", "patch": "+assert x == 1", "additions": 1},
        ],
    })
    return ReviewCouncil().review(snapshot)


class PublisherTests(unittest.TestCase):
    def test_plan_is_a_non_mutating_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            plan = ReportPublisher().plan(report(), output)
            self.assertFalse(output.exists())
            self.assertTrue(plan.creates_new)
            self.assertEqual(plan.steps, ("stage", "apply", "verify"))

    def test_apply_and_verify_new_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            publisher = ReportPublisher()
            receipt = publisher.apply(publisher.plan(report(), output), report())
            self.assertTrue(publisher.verify(receipt))
            self.assertIsNone(receipt.backup_path)

    def test_rollback_new_output_removes_exact_applied_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            publisher = ReportPublisher()
            item = report()
            receipt = publisher.apply(publisher.plan(item, output), item)
            result = publisher.rollback(receipt)
            self.assertFalse(output.exists())
            self.assertEqual(result["state"], "rolled_back")

    def test_rollback_restores_previous_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            output.write_text("known-good\n", encoding="utf-8")
            publisher = ReportPublisher()
            item = report()
            receipt = publisher.apply(publisher.plan(item, output), item)
            publisher.rollback(receipt)
            self.assertEqual(output.read_text(encoding="utf-8"), "known-good\n")

    def test_apply_refuses_output_changed_after_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            output.write_text("one", encoding="utf-8")
            publisher = ReportPublisher()
            item = report()
            plan = publisher.plan(item, output)
            output.write_text("two", encoding="utf-8")
            with self.assertRaisesRegex(PublicationError, "changed after planning"):
                publisher.apply(plan, item)

    def test_apply_refuses_report_changed_after_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            publisher = ReportPublisher()
            plan = publisher.plan(report("one"), Path(tmp) / "report.json")
            with self.assertRaisesRegex(PublicationError, "report changed"):
                publisher.apply(plan, report("two"))

    def test_rollback_refuses_to_clobber_later_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            publisher = ReportPublisher()
            item = report()
            receipt = publisher.apply(publisher.plan(item, output), item)
            output.write_text("later change", encoding="utf-8")
            with self.assertRaisesRegex(PublicationError, "no longer matches"):
                publisher.rollback(receipt)

    def test_existing_backup_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            output.write_text("old", encoding="utf-8")
            publisher = ReportPublisher()
            item = report()
            plan = publisher.plan(item, output)
            Path(plan.backup_path).write_text("do not overwrite", encoding="utf-8")
            with self.assertRaisesRegex(PublicationError, "backup"):
                publisher.apply(plan, item)

    def test_receipt_round_trip_and_file_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            publisher = ReportPublisher()
            item = report()
            receipt = publisher.apply(publisher.plan(item, output), item)
            receipt_path = Path(tmp) / "receipt.json"
            write_receipt(receipt, receipt_path)
            loaded = TransactionReceipt.from_dict(json.loads(receipt_path.read_text(encoding="utf-8")))
            self.assertEqual(loaded, receipt)

    def test_non_verified_receipt_is_rejected(self):
        data = {
            "schema_version": "1.0", "transaction_id": "x", "state": "blocked",
            "output_path": "/tmp/x", "backup_path": None, "previous_sha": None,
            "applied_sha": "a" * 64, "verified": False,
        }
        with self.assertRaises(ValidationError):
            TransactionReceipt.from_dict(data)


if __name__ == "__main__":
    unittest.main()
