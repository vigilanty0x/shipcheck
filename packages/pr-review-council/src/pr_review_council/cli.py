"""Bounded JSON CLI for local review, proof, publication, and rollback."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .council import ReviewCouncil
from .models import PullRequestSnapshot, ValidationError
from .probes import functional_probe, inventory, liveness_probe, readiness_probe
from .publisher import (
    PublicationError,
    ReportPublisher,
    TransactionReceipt,
    write_receipt,
)


MAX_INPUT_BYTES = 1_048_576


def _read_json(path: str) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise ValidationError(f"input file does not exist: {path}")
    if target.stat().st_size > MAX_INPUT_BYTES:
        raise ValidationError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON input: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("JSON input must be an object")
    return data


def _emit(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _snapshot(path: str) -> PullRequestSnapshot:
    return PullRequestSnapshot.from_dict(_read_json(path))


def _receipt(path: str) -> TransactionReceipt:
    return TransactionReceipt.from_dict(_read_json(path))


def _review(path: str):
    return ReviewCouncil().review(_snapshot(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pr-review-council",
        description="Run a deterministic council of specialized PR reviewers.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    review = commands.add_parser("review", help="Review a bounded PR snapshot")
    review.add_argument("--input", required=True)
    review.add_argument("--fail-on-gate", action="store_true")

    plan = commands.add_parser("plan", help="Dry-run transactional report publication")
    plan.add_argument("--input", required=True)
    plan.add_argument("--output", required=True)

    publish = commands.add_parser("publish", help="Apply and verify a report publication")
    publish.add_argument("--input", required=True)
    publish.add_argument("--output", required=True)
    publish.add_argument("--receipt", required=True)

    verify = commands.add_parser("verify", help="Verify the actually served report bytes")
    verify.add_argument("--receipt", required=True)

    rollback = commands.add_parser("rollback", help="Rollback an exact verified transaction")
    rollback.add_argument("--receipt", required=True)
    rollback.add_argument("--yes", action="store_true", help="Acknowledge the local file mutation")

    probe = commands.add_parser("probe", help="Run a separated operational probe")
    probe.add_argument("--level", choices=("liveness", "readiness", "functional"), required=True)

    commands.add_parser("inventory", help="Print the canonical component inventory")

    demo = commands.add_parser("demo", help="Run review, apply, verify, rollback, and replay locally")
    demo.add_argument("--workspace", required=True)
    return parser


def _run_demo(workspace: str) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    snapshot_path = root / "pr.json"
    output_path = root / "review-report.json"
    receipt_path = root / "receipt.json"
    snapshot_data = {
        "pr_id": "demo-42",
        "commit_sha": "b" * 40,
        "title": "Add a bounded HTTP client",
        "body": "Synthetic offline demonstration.",
        "files": [
            {
                "path": "src/client.py",
                "patch": "@@ -0,0 +1,2 @@\n+def fetch(client, url):\n+    return client.get(url, timeout=5)\n",
                "additions": 2,
                "deletions": 0,
            },
            {
                "path": "tests/test_client.py",
                "patch": "@@ -0,0 +1 @@\n+def test_timeout_is_bounded(): pass\n",
                "additions": 1,
                "deletions": 0,
            },
        ],
    }
    snapshot_path.write_text(json.dumps(snapshot_data, indent=2) + "\n", encoding="utf-8")
    output_path.write_text('{"previous":"known-good"}\n', encoding="utf-8")
    report = ReviewCouncil().review(PullRequestSnapshot.from_dict(snapshot_data))
    publisher = ReportPublisher()
    first_plan = publisher.plan(report, output_path)
    first_receipt = publisher.apply(first_plan, report)
    write_receipt(first_receipt, receipt_path)
    served_verified = publisher.verify(first_receipt)
    rollback = publisher.rollback(first_receipt)
    rollback_restored_previous = output_path.read_text(encoding="utf-8") == '{"previous":"known-good"}\n'
    replay_plan = publisher.plan(report, output_path)
    replay_receipt = publisher.apply(replay_plan, report)
    write_receipt(replay_receipt, receipt_path)
    return {
        "decision": report.decision.value,
        "report_sha": report.report_sha,
        "served_sha": replay_receipt.applied_sha,
        "served_verified": served_verified and publisher.verify(replay_receipt),
        "rollback": rollback,
        "rollback_restored_previous": rollback_restored_previous,
        "replay_verified": publisher.verify(replay_receipt),
        "workspace": str(root),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "review":
            report = _review(args.input)
            _emit(report.to_dict())
            return 3 if args.fail_on_gate and report.decision.value != "approved" else 0
        if args.command == "plan":
            report = _review(args.input)
            plan = ReportPublisher().plan(report, args.output)
            _emit({"dry_run": True, "report": report.to_dict(), "plan": plan.to_dict()})
            return 0
        if args.command == "publish":
            report = _review(args.input)
            publisher = ReportPublisher()
            plan = publisher.plan(report, args.output)
            receipt = publisher.apply(plan, report)
            try:
                write_receipt(receipt, args.receipt)
            except Exception:
                publisher.rollback(receipt)
                raise
            _emit({"decision": report.decision.value, "report_sha": report.report_sha, "receipt": receipt.to_dict()})
            return 0
        if args.command == "verify":
            receipt = _receipt(args.receipt)
            verified = ReportPublisher().verify(receipt)
            _emit({"transaction_id": receipt.transaction_id, "state": "verified" if verified else "blocked", "verified": verified})
            return 0 if verified else 4
        if args.command == "rollback":
            if not args.yes:
                raise ValidationError("rollback requires --yes")
            _emit(ReportPublisher().rollback(_receipt(args.receipt)))
            return 0
        if args.command == "probe":
            result = {
                "liveness": liveness_probe,
                "readiness": readiness_probe,
                "functional": functional_probe,
            }[args.level]()
            _emit(result)
            return 0 if result["status"] in {"alive", "ready", "proven"} else 5
        if args.command == "inventory":
            _emit(inventory())
            return 0
        if args.command == "demo":
            _emit(_run_demo(args.workspace))
            return 0
        raise AssertionError("unreachable command")
    except (ValidationError, PublicationError, OSError) as exc:
        _emit({"error": str(exc)[:1_000], "type": type(exc).__name__})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
