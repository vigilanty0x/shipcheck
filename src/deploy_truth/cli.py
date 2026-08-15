"""Offline CLI for release evidence and local transactional deployment."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any, Sequence

from .api import capture_and_verify
from .evidence import verify_evidence_document
from .fixtures import SyntheticFixture
from .io import load_object, load_spec, write_json_atomic
from .models import ContractError, Decision
from .probes import functional_probe, liveness_probe, readiness_probe
from .transactions import (
    DeploymentPlan, apply_plan, build_plan, rollback_plan, verify_applied,
)


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _decision_code(decision: Decision) -> int:
    return {Decision.VERIFIED: 0, Decision.DEGRADED: 2, Decision.BLOCKED: 3}[decision]


def _load_plan(path: Path) -> DeploymentPlan:
    return DeploymentPlan.from_dict(load_object(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deploy-truth", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    verify = commands.add_parser("verify", help="compare local source, bundle, and live roots")
    verify.add_argument("--spec", type=Path, required=True)
    verify.add_argument("--source", type=Path, required=True)
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--live", type=Path, required=True)
    verify.add_argument("--output", type=Path)

    fixture = commands.add_parser("fixture", help="verify a purely synthetic fixture")
    fixture.add_argument("path", type=Path)
    fixture.add_argument("--output", type=Path)

    evidence = commands.add_parser("verify-evidence", help="verify report and inventory content hashes")
    evidence.add_argument("path", type=Path)

    plan = commands.add_parser("plan", help="dry-run a local bundle-to-live transaction")
    plan.add_argument("--spec", type=Path, required=True)
    plan.add_argument("--bundle", type=Path, required=True)
    plan.add_argument("--live", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)

    apply = commands.add_parser("apply", help="apply an exact preconditioned local plan")
    _transaction_arguments(apply, include_bundle=True, include_rollback=True)

    transaction_verify = commands.add_parser("verify-transaction", help="verify live against a plan")
    _transaction_arguments(transaction_verify, include_bundle=False, include_rollback=False)

    rollback = commands.add_parser("rollback", help="restore the exact pre-apply live snapshot")
    _transaction_arguments(rollback, include_bundle=False, include_rollback=True)

    probe = commands.add_parser("probe", help="run an operational probe")
    probe.add_argument("mode", choices=("liveness", "readiness", "functional"))

    demo = commands.add_parser("demo", help="run a local synthetic plan/apply/verify/rollback demo")
    demo.add_argument("directory", type=Path)
    return parser


def _transaction_arguments(
    parser: argparse.ArgumentParser, *, include_bundle: bool, include_rollback: bool,
) -> None:
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    if include_bundle:
        parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--live", type=Path, required=True)
    if include_rollback:
        parser.add_argument("--rollback-root", type=Path, required=True)
    if include_bundle or include_rollback:
        parser.add_argument("--confirm-plan-id", required=True)


def _write_demo_inputs(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    source, bundle, live, rollback = (root / name for name in ("source", "bundle", "live", "rollback"))
    for directory in (source, bundle, live, rollback):
        directory.mkdir(parents=True, exist_ok=True)
    spec_path = root / "release.json"
    spec_value = {
        "schema_version": "1.0", "release_version": "demo-1.0",
        "components": [{
            "name": "web", "version": "1.0", "dependencies": [], "state": "ready",
            "artifacts": ["web/app.bin", "web/config.json"],
        }],
    }
    write_json_atomic(spec_path, spec_value)
    for directory in (source, bundle):
        (directory / "web").mkdir(parents=True, exist_ok=True)
        (directory / "web" / "app.bin").write_bytes(b"demo-release-v1")
        (directory / "web" / "config.json").write_bytes(b'{"mode":"demo"}\n')
    (live / "web").mkdir(parents=True, exist_ok=True)
    (live / "web" / "app.bin").write_bytes(b"old-release")
    (live / "obsolete.txt").write_bytes(b"remove-me")
    return spec_path, source, bundle, live, rollback


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "verify":
            report = capture_and_verify(load_spec(args.spec), args.source, args.bundle, args.live)
            if args.output:
                write_json_atomic(args.output, report.to_dict())
            _emit(report.to_dict())
            return _decision_code(report.decision)
        if args.command == "fixture":
            report = SyntheticFixture.load(args.path).verify()
            if args.output:
                write_json_atomic(args.output, report.to_dict())
            _emit(report.to_dict())
            return _decision_code(report.decision)
        if args.command == "verify-evidence":
            digest = verify_evidence_document(load_object(args.path))
            _emit({"schema_version": "1.0", "valid": True, "evidence_sha256": digest})
            return 0
        if args.command == "plan":
            plan = build_plan(load_spec(args.spec), args.bundle, args.live)
            write_json_atomic(args.output, plan.to_dict())
            _emit(plan.to_dict())
            return 0
        if args.command == "apply":
            result = apply_plan(
                _load_plan(args.plan), load_spec(args.spec), args.bundle, args.live, args.rollback_root,
                confirm_plan_id=args.confirm_plan_id,
            )
            _emit(result.to_dict())
            return _decision_code(result.decision)
        if args.command == "verify-transaction":
            result = verify_applied(_load_plan(args.plan), load_spec(args.spec), args.live)
            _emit(result.to_dict())
            return _decision_code(result.decision)
        if args.command == "rollback":
            result = rollback_plan(
                _load_plan(args.plan), load_spec(args.spec), args.live, args.rollback_root,
                confirm_plan_id=args.confirm_plan_id,
            )
            _emit(result.to_dict())
            return _decision_code(result.decision)
        if args.command == "probe":
            probes = {"liveness": liveness_probe, "readiness": readiness_probe, "functional": functional_probe}
            result = probes[args.mode]()
            _emit(result.to_dict())
            return 0 if result.healthy else 3
        if args.command == "demo":
            spec_path, source, bundle, live, rollback = _write_demo_inputs(args.directory)
            spec = load_spec(spec_path)
            before = capture_and_verify(spec, source, bundle, live)
            plan = build_plan(spec, bundle, live)
            plan_path = args.directory / "plan.json"
            write_json_atomic(plan_path, plan.to_dict())
            applied = apply_plan(plan, spec, bundle, live, rollback, confirm_plan_id=plan.plan_id)
            verified = verify_applied(plan, spec, live)
            rolled_back = rollback_plan(plan, spec, live, rollback, confirm_plan_id=plan.plan_id)
            restored = capture_and_verify(spec, source, bundle, live)
            output = {
                "schema_version": "1.0", "before_decision": before.decision.value,
                "plan_id": plan.plan_id, "operations": len(plan.operations),
                "apply": applied.to_dict(), "verify": verified.to_dict(),
                "rollback": rolled_back.to_dict(), "restored_decision": restored.decision.value,
                "plan": str(plan_path),
            }
            _emit(output)
            return 0 if applied.decision is Decision.VERIFIED and verified.decision is Decision.VERIFIED and rolled_back.decision is Decision.VERIFIED else 3
        raise AssertionError("unreachable command")
    except ContractError as exc:
        _emit({"success": False, "decision": "blocked", "error": "contract_error", "message": str(exc)})
        return 4
    except OSError as exc:
        _emit({"success": False, "decision": "blocked", "error": "io_error", "message": str(exc)})
        return 5


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
