"""Bounded offline CLI for deterministic merge decisions and local transactions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from typing import Any, Mapping

from .contract import ContractError, GateArtifact, GatePolicy, MergeSnapshot, canonical_json
from .gate import evaluate
from .probes import functional_counter_proof, liveness, readiness
from .transaction import LocalMergeTransaction, Receipt, TransactionError

MAX_INPUT_BYTES = 1_000_000


def _load(path: Path) -> Mapping[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ContractError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ContractError("input root must be an object")
    return value


def _write(path: Path, value: Mapping[str, object]) -> None:
    data = (canonical_json(value) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists(): temporary.unlink()


def _artifact(path: Path) -> GateArtifact:
    return GateArtifact.from_dict(_load(path))


def _receipt(path: Path) -> Receipt:
    return Receipt.from_dict(_load(path))


def _inventory(args: argparse.Namespace) -> int:
    snapshot = MergeSnapshot.from_dict(_load(args.snapshot))
    print(canonical_json({**snapshot.inventory, "inventory_sha256": snapshot.inventory_sha256}))
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    snapshot = MergeSnapshot.from_dict(_load(args.snapshot))
    policy = GatePolicy.from_dict(_load(args.policy)) if args.policy else GatePolicy()
    artifact = evaluate(snapshot, policy, generated_at=args.generated_at)
    if args.evidence:
        _write(args.evidence, artifact.to_dict())
    print(canonical_json(artifact.to_dict()))
    return 0 if artifact.ready else 2


def _dry_run(args: argparse.Namespace) -> int:
    result = LocalMergeTransaction().dry_run(_artifact(args.evidence), args.state)
    print(canonical_json(result))
    return 0 if result["applicable"] else 2


def _apply(args: argparse.Namespace) -> int:
    receipt = LocalMergeTransaction().apply(
        _artifact(args.evidence), args.state, args.receipt, created_at=args.created_at,
    )
    print(canonical_json(receipt.to_dict()))
    return 0


def _verify(args: argparse.Namespace) -> int:
    result = LocalMergeTransaction().verify(_receipt(args.receipt), args.state)
    print(canonical_json(result))
    return 0


def _rollback(args: argparse.Namespace) -> int:
    result = LocalMergeTransaction().rollback(_receipt(args.receipt), args.state)
    print(canonical_json(result))
    return 0


def _probe(args: argparse.Namespace) -> int:
    if args.kind == "liveness": result = liveness()
    elif args.kind == "readiness": result = readiness(args.directory)
    else: result = functional_counter_proof()
    print(canonical_json(result))
    return 0 if result["ok"] else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="safe-merge-gate", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("inventory", help="print a canonical change inventory")
    inventory.add_argument("--snapshot", type=Path, required=True); inventory.set_defaults(run=_inventory)
    decision = commands.add_parser("evaluate", help="evaluate a snapshot and emit evidence")
    decision.add_argument("--snapshot", type=Path, required=True)
    decision.add_argument("--policy", type=Path)
    decision.add_argument("--evidence", type=Path)
    decision.add_argument("--generated-at")
    decision.set_defaults(run=_evaluate)
    dry = commands.add_parser("dry-run", help="check local applicability without writes")
    dry.add_argument("--evidence", type=Path, required=True); dry.add_argument("--state", type=Path, required=True)
    dry.set_defaults(run=_dry_run)
    apply = commands.add_parser("apply", help="transactionally apply a ready artifact locally")
    apply.add_argument("--evidence", type=Path, required=True); apply.add_argument("--state", type=Path, required=True)
    apply.add_argument("--receipt", type=Path, required=True); apply.add_argument("--created-at")
    apply.set_defaults(run=_apply)
    verify = commands.add_parser("verify", help="verify applied bytes against a receipt")
    verify.add_argument("--receipt", type=Path, required=True); verify.add_argument("--state", type=Path, required=True)
    verify.set_defaults(run=_verify)
    rollback = commands.add_parser("rollback", help="restore exact pre-apply bytes")
    rollback.add_argument("--receipt", type=Path, required=True); rollback.add_argument("--state", type=Path, required=True)
    rollback.set_defaults(run=_rollback)
    probe = commands.add_parser("probe", help="run an offline health probe")
    probe.add_argument("kind", choices=("liveness", "readiness", "functional"))
    probe.add_argument("--directory", type=Path, default=Path(".")); probe.set_defaults(run=_probe)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.run(args))
    except (ContractError, TransactionError, OSError, json.JSONDecodeError) as exc:
        print(canonical_json({"error": type(exc).__name__, "message": str(exc), "success": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
