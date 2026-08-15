"""Offline liveness, readiness, and transactional counter-proof probes."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .contract import Change, CheckState, GatePolicy, MergeSnapshot
from .gate import evaluate
from .transaction import ApplyBlocked, LocalMergeTransaction

BASE_SHA = "1" * 40
MERGE_SHA = "2" * 40
NOW = "2026-01-01T00:00:00Z"


def synthetic_snapshot(*, observed_sha: str = BASE_SHA, tests_passed: bool = True) -> MergeSnapshot:
    return MergeSnapshot(
        repository="synthetic/example", expected_sha=BASE_SHA, observed_sha=observed_sha,
        merge_sha=MERGE_SHA, captured_at=NOW,
        ci={"build": CheckState.SUCCESS, "test": CheckState.SUCCESS},
        required_ci=("build", "test"), optional_ci=(),
        tests_complete=True, tests_passed=tests_passed,
        secret_scan_complete=True, secret_findings=(), clean_tree=True,
        changes=(Change("src/example.py", 8, 2), Change("tests/test_example.py", 12, 0)),
    )


def liveness() -> dict[str, object]:
    return {"probe": "liveness", "ok": True, "contract": "1.0"}


def readiness(directory: str | Path) -> dict[str, object]:
    path = Path(directory)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".safe-merge-gate-readiness"
        probe.write_bytes(b"ready")
        exact = probe.read_bytes() == b"ready"
        probe.unlink()
    except OSError as exc:
        return {"probe": "readiness", "ok": False, "reason": type(exc).__name__}
    return {"probe": "readiness", "ok": exact, "writable": exact}


def functional_counter_proof() -> dict[str, object]:
    transaction = LocalMergeTransaction()
    with TemporaryDirectory(prefix="safe-merge-gate-") as directory:
        root = Path(directory)
        state = root / "state.json"
        receipt_path = root / "receipt.json"
        original = b'{\n  "current_sha": "' + BASE_SHA.encode() + b'",\n  "note": "exact bytes"\n}\n'
        state.write_bytes(original)
        ready = evaluate(synthetic_snapshot(), GatePolicy(), generated_at=NOW)
        preview = transaction.dry_run(ready, state)
        unchanged_after_dry_run = state.read_bytes() == original
        receipt = transaction.apply(ready, state, receipt_path, created_at=NOW)
        verified = transaction.verify(receipt, state)
        rolled_back = transaction.rollback(receipt, state)
        exact_rollback = state.read_bytes() == original

        blocked = evaluate(synthetic_snapshot(observed_sha="3" * 40), generated_at=NOW)
        counter_proof_blocked = False
        try:
            transaction.apply(blocked, state, root / "blocked-receipt.json", created_at=NOW)
        except ApplyBlocked:
            counter_proof_blocked = True
        ok = all((
            ready.ready, preview["applicable"], unchanged_after_dry_run,
            verified["verified"], rolled_back["rolled_back"], exact_rollback,
            not blocked.ready, counter_proof_blocked,
        ))
        return {
            "probe": "functional", "ok": ok, "ready_decision": ready.decision.value,
            "counter_proof_decision": blocked.decision.value,
            "dry_run_unchanged": unchanged_after_dry_run,
            "apply_verified": verified["verified"], "rollback_exact": exact_rollback,
            "blocked_apply_rejected": counter_proof_blocked,
            "artifact_sha256": ready.sha256,
        }

