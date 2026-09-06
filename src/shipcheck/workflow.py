"""One evidence-to-rollback workflow across both Shipcheck engines.

This verifies existing test reports; it never executes repository commands.
Rollback is exercised on a new private copy, never the supplied live state.
The original state and artifacts are rechecked before the final receipt.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from safe_merge_gate import GatePolicy, MergeSnapshot, LocalMergeTransaction
from safe_merge_gate import evaluate as evaluate_merge
from .release_gate import DecisionEngine, ReleaseEvidence, ReleasePolicy
from .release_gate.adapters import normalize_junit
from .release_gate.artifacts import hash_artifact
from .release_gate.canonical import canonical_json, object_digest
from .release_gate.errors import ValidationError
from .release_gate.limits import load_json_file, loads_strict
from .release_gate.risk import normalize_repo_path, score_diff
from .release_gate.secureio import read_regular_file, read_secret_file
from .release_gate.trust import TrustStore
from .producer_receipts import check_root, verify_producer_bundle, recheck_producer_files


def _path(root, relative):
    relative = normalize_repo_path(relative)
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ValidationError("workflow refuses linked inputs")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValidationError("workflow input leaves its root")
    return current


def _new_bytes(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _new_json(path, value):
    _new_bytes(path, canonical_json(value) + b"\n")


def run_workflow(request, *, root, output, trust_store=None, clock=None):
    root, output = Path(root), Path(output)
    required = {"schema_version", "release_evidence", "release_policy", "merge_snapshot",
                "merge_policy", "artifacts", "junit", "state_path", "allow_lab"}
    if (not isinstance(request, dict) or not required <= set(request)
            or set(request) - required - {"producer_bundle"}
            or request["schema_version"] != "shipcheck/workflow-v1"):
        raise ValidationError("workflow schema or fields invalid")
    if type(request["allow_lab"]) is not bool:
        raise ValidationError("allow_lab must be explicit boolean")
    if "producer_bundle" in request: check_root(root)
    root = root.resolve(strict=True)
    if not root.is_dir(): raise ValidationError("workflow root must be a directory")
    # Validate all contracts before creating the run directory.
    evidence = ReleaseEvidence.from_dict(request["release_evidence"])
    policy = ReleasePolicy.from_dict(request["release_policy"])
    snapshot = MergeSnapshot.from_dict(request["merge_snapshot"])
    merge_policy = GatePolicy.from_dict(request["merge_policy"])
    if (snapshot.repository != evidence.candidate.repository
            or snapshot.expected_sha != evidence.candidate.base_commit
            or snapshot.observed_sha != evidence.candidate.base_commit
            or snapshot.merge_sha != evidence.candidate.head_commit):
        raise ValidationError("merge and release candidate identity mismatch")
    bindings, junit = request["artifacts"], request["junit"]
    if (not isinstance(bindings, list) or not 1 <= len(bindings) <= 100
            or not isinstance(junit, list) or not 1 <= len(junit) <= 100):
        raise ValidationError("bounded artifact and JUnit lists required")
    names = []
    for item in bindings:
        if not isinstance(item, dict) or set(item) != {"name", "path"}:
            raise ValidationError("artifact binding requires name and path")
        if not isinstance(item["name"], str): raise ValidationError("artifact name required")
        _path(root, item["path"])
        names.append(item["name"])
    if len(names) != len(set(names)) or set(names) != set(policy.required_artifacts):
        raise ValidationError("artifact bindings must match required artifacts exactly")
    if any(not isinstance(item, str) for item in junit) or len(junit) != len(set(junit)):
        raise ValidationError("JUnit paths must be unique strings")
    state_path = _path(root, request["state_path"])
    before = read_regular_file(state_path, max_bytes=1024 * 1024)
    state = loads_strict(before)
    if not isinstance(state, dict) or state.get("current_sha") != snapshot.observed_sha or state.get("repository") != snapshot.repository:
        raise ValidationError("local state does not match candidate base")
    # All ancestors of the new output must be real directories. Never follow
    # an existing output symlink or reuse an old receipt directory.
    for parent in (output, *output.parents):
        if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
            raise ValidationError("linked workflow output refused")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    result = {"schema_version": "shipcheck/workflow-result-v1", "request_digest": object_digest(request),
        "candidate_digest": evidence.candidate.digest, "status": "blocked", "production_ready": False,
        "publication": False, "state_scope": "new_local_copy_drill", "tests_executed_here": False,
        "stages": [], "source_state_sha256": hashlib.sha256(before).hexdigest()}
    try:
        producer_proof = None
        if "producer_bundle" in request:
            producer_proof = verify_producer_bundle(request["producer_bundle"], root=root,
                                                   candidate=evidence.candidate, clock=clock)
            _new_json(output / "producer-receipts.json", producer_proof)
            result["stages"].append({"stage": "producer_receipts", "status": "passed" if producer_proof["passed"] else "blocked",
                "verification_digest": producer_proof["verification_digest"], "subject_binding": "declared_only",
                "authenticity_established": False, "reason_code": producer_proof["reason_code"]})
            if not producer_proof["passed"]:
                raise ValidationError("producer receipt consistency veto")
        observed_artifacts = []
        for binding in bindings:
            observed = hash_artifact(root, binding["path"], max_bytes=64 * 1024 * 1024)
            claims = [o.payload for o in evidence.observations if o.kind == "artifact" and o.payload.get("name") == binding["name"]]
            if len(claims) != 1 or any(observed[k] != claims[0].get(k) for k in ("digest", "size_bytes")):
                raise ValidationError("observed artifact bytes differ from release evidence")
            observed_artifacts.append({**observed, "name": binding["name"]})
        result["stages"].append({"stage": "evidence", "status": "passed", "artifacts": observed_artifacts})
        diffs = [o.payload for o in evidence.observations if o.kind == "diff"]
        if len(diffs) != 1: raise ValidationError("one diff observation required")
        risk = score_diff(diffs[0])
        # The two engines must be judging the same changed files and sizes.
        expected_changes = sorted((c.path, c.additions, c.deletions, c.binary) for c in snapshot.changes)
        observed_changes = sorted((c["path"], c["additions"], c["deletions"], c["binary"]) for c in diffs[0]["files"])
        if expected_changes != observed_changes:
            raise ValidationError("merge and release diff inventory mismatch")
        result["stages"].append({"stage": "risk", "status": "measured", "assessment": risk.to_dict()})
        records, test_inputs = {}, []
        for relative in junit:
            raw = read_regular_file(_path(root, relative), max_bytes=2 * 1024 * 1024)
            normalized = normalize_junit(raw)
            test_inputs.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest()})
            for record in normalized["records"]:
                payload = record["payload"]
                name = payload["suite"]
                if name in records: raise ValidationError("duplicate JUnit suite")
                records[name] = payload
        if set(records) != set(policy.required_test_suites):
            raise ValidationError("JUnit suites must match required suites exactly")
        for name, record in records.items():
            claims = [o.payload for o in evidence.observations if o.kind == "test_summary" and o.payload.get("suite") == name]
            if len(claims) != 1 or any(record[k] != claims[0].get(k) for k in ("total", "passed", "failed", "skipped")):
                raise ValidationError("JUnit result contradicts release test evidence")
            if record["total"] <= 0 or record["failed"] or record["skipped"]:
                raise ValidationError("JUnit tests incomplete or failed")
        result["stages"].append({"stage": "tests", "status": "passed", "origin": "supplied_junit_cross_checked",
                                 "reports": test_inputs, "suites": len(records)})
        decision = DecisionEngine(trust_store=trust_store, clock=clock).evaluate(evidence, policy)
        merge = evaluate_merge(snapshot, merge_policy)
        _new_json(output / "release-decision.json", decision.to_dict())
        _new_json(output / "merge-decision.json", merge.to_dict())
        result["stages"].append({"stage": "release_gate", "status": decision.outcome,
            "decision_digest": decision.digest, "merge_decision": merge.decision.value,
            "merge_digest": merge.sha256, "production_ready": decision.production_ready})
        if decision.outcome != "READY" or merge.decision.value != "ready":
            raise ValidationError("release or merge decision blocks rollback rehearsal")
        if not decision.production_ready and not request["allow_lab"]:
            raise ValidationError("LAB evidence cannot authorize production")
        # Always create the state before apply, so rollback never needs to
        # remove a file. Retain every drill file and receipt for inspection.
        drill_state = output / "drill-state.json"
        _new_bytes(drill_state, before)
        transaction = LocalMergeTransaction()
        preview = transaction.dry_run(merge, drill_state)
        if preview["applicable"] is not True: raise ValidationError("rollback drill not applicable")
        receipt = transaction.apply(merge, drill_state, output / "rollback-receipt.json")
        verified = transaction.verify(receipt, drill_state)
        restored = transaction.rollback(receipt, drill_state)
        if verified["verified"] is not True or restored["rolled_back"] is not True or drill_state.read_bytes() != before:
            raise ValidationError("rollback drill did not restore exact bytes")
        result["stages"].append({"stage": "rollback", "status": "passed", "scope": "new_local_copy",
            "before_sha256": receipt.before_bytes_sha256, "applied_sha256": receipt.after_bytes_sha256,
            "restored_sha256": restored["restored_sha256"]})
        if read_regular_file(state_path, max_bytes=1024 * 1024) != before:
            raise ValidationError("source state changed during workflow")
        for binding, prior in zip(bindings, observed_artifacts):
            again = hash_artifact(root, binding["path"], max_bytes=64 * 1024 * 1024)
            if any(again[k] != prior[k] for k in ("digest", "size_bytes")):
                raise ValidationError("artifact changed during workflow")
        for report in test_inputs:
            again = read_regular_file(_path(root, report["path"]), max_bytes=2 * 1024 * 1024)
            if hashlib.sha256(again).hexdigest() != report["sha256"]:
                raise ValidationError("JUnit changed during workflow")
        if producer_proof is not None:
            recheck_producer_files(producer_proof, root=root, clock=clock)
            result['producer_files_rechecked'] = True
        result.update(status="ready" if decision.production_ready else "ready_lab",
                      production_ready=decision.production_ready)
    except Exception as exc:
        result.update(error_code=type(exc).__name__, status="blocked", production_ready=False)
        result["stages"].append({"stage": "stop", "status": "blocked", "error_code": type(exc).__name__})
    result["receipt_digest"] = object_digest(result)
    _new_json(output / "workflow-receipt.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(prog="shipcheck workflow")
    parser.add_argument("request", type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--trust-store", type=Path)
    args = parser.parse_args(argv)
    try:
        trust = None if args.trust_store is None else TrustStore.from_dict(loads_strict(
            read_secret_file(args.trust_store, max_bytes=1024 * 1024)))
        result = run_workflow(load_json_file(args.request), root=args.root, output=args.output, trust_store=trust)
    except Exception as exc:
        result = {"status": "blocked", "error_code": type(exc).__name__, "publication": False}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] in {"ready", "ready_lab"} else 2
