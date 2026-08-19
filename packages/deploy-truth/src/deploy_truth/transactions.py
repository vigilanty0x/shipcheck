"""Local, preconditioned release plans with exact rollback evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Mapping

from .inventory import CaptureLimits, capture_directory
from .io import write_json_atomic
from .models import (
    CaptureState, ContractError, Decision, LayerInventory, LayerName, ReleaseSpec,
    canonical_json, sha256_json, validate_relative_path,
)


class OperationKind(StrEnum):
    WRITE = "write"
    DELETE = "delete"


class TransactionOutcome(StrEnum):
    APPLIED = "applied"
    VERIFIED = "verified"
    ROLLED_BACK = "rolled_back"
    AUTO_ROLLED_BACK = "auto_rolled_back"
    BLOCKED = "blocked"


def content_sha256(inventory: LayerInventory) -> str:
    return sha256_json([artifact.to_dict() for artifact in inventory.artifacts])


@dataclass(frozen=True, slots=True)
class Operation:
    kind: OperationKind
    path: str
    bundle_sha256: str | None
    previous_live_sha256: str | None

    def __post_init__(self) -> None:
        validate_relative_path(self.path)
        if self.kind is OperationKind.WRITE and self.bundle_sha256 is None:
            raise ContractError("write operations require bundle_sha256")
        for value in (self.bundle_sha256, self.previous_live_sha256):
            if value is not None and (len(value) != 64 or any(c not in "0123456789abcdef" for c in value)):
                raise ContractError("operation sha256 is invalid")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["kind"] = self.kind.value
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Operation":
        if set(value) != {"kind", "path", "bundle_sha256", "previous_live_sha256"}:
            raise ContractError("operation fields do not match schema 1.0")
        try:
            return cls(
                OperationKind(value["kind"]), value["path"],
                value["bundle_sha256"], value["previous_live_sha256"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError(f"invalid operation: {exc}") from exc


@dataclass(frozen=True, slots=True)
class DeploymentPlan:
    schema_version: str
    spec_sha256: str
    release_version: str
    expected_live_content_sha256: str
    desired_bundle_content_sha256: str
    operations: tuple[Operation, ...]
    plan_id: str

    @classmethod
    def create(
        cls, spec: ReleaseSpec, bundle: LayerInventory, live: LayerInventory,
    ) -> "DeploymentPlan":
        if bundle.state is CaptureState.BLOCKED or live.state is CaptureState.BLOCKED:
            raise ContractError("cannot plan from a blocked inventory")
        expected_paths = set(spec.artifact_components())
        bundle_index = {item.path: item for item in bundle.artifacts}
        live_index = {item.path: item for item in live.artifacts}
        if set(bundle_index) != expected_paths:
            raise ContractError("bundle must contain exactly the release spec artifacts before planning")
        operations: list[Operation] = []
        for path in sorted(expected_paths):
            desired = bundle_index[path]
            previous = live_index.get(path)
            if previous is None or previous.sha256 != desired.sha256 or previous.size != desired.size:
                operations.append(Operation(
                    OperationKind.WRITE, path, desired.sha256, previous.sha256 if previous else None,
                ))
        for path in sorted(set(live_index) - expected_paths):
            operations.append(Operation(OperationKind.DELETE, path, None, live_index[path].sha256))
        identity = {
            "schema_version": "1.0", "spec_sha256": spec.spec_sha256,
            "release_version": spec.release_version,
            "expected_live_content_sha256": content_sha256(live),
            "desired_bundle_content_sha256": content_sha256(bundle),
            "operations": [operation.to_dict() for operation in operations],
        }
        return cls(
            "1.0", spec.spec_sha256, spec.release_version,
            identity["expected_live_content_sha256"], identity["desired_bundle_content_sha256"],
            tuple(operations), sha256_json(identity),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "spec_sha256": self.spec_sha256,
            "release_version": self.release_version,
            "expected_live_content_sha256": self.expected_live_content_sha256,
            "desired_bundle_content_sha256": self.desired_bundle_content_sha256,
            "operations": [item.to_dict() for item in self.operations], "plan_id": self.plan_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DeploymentPlan":
        if set(value) != {
            "schema_version", "spec_sha256", "release_version", "expected_live_content_sha256",
            "desired_bundle_content_sha256", "operations", "plan_id",
        } or value["schema_version"] != "1.0":
            raise ContractError("plan fields do not match schema 1.0")
        if not isinstance(value["operations"], list):
            raise ContractError("plan operations must be a list")
        operations = tuple(Operation.from_dict(item) for item in value["operations"])
        if len(operations) > 4096:
            raise ContractError("plan operation limit exceeded")
        identity = {
            "schema_version": "1.0", "spec_sha256": value["spec_sha256"],
            "release_version": value["release_version"],
            "expected_live_content_sha256": value["expected_live_content_sha256"],
            "desired_bundle_content_sha256": value["desired_bundle_content_sha256"],
            "operations": [operation.to_dict() for operation in operations],
        }
        expected_id = sha256_json(identity)
        if value["plan_id"] != expected_id:
            raise ContractError("plan_id does not match plan content")
        return cls(
            "1.0", value["spec_sha256"], value["release_version"],
            value["expected_live_content_sha256"], value["desired_bundle_content_sha256"],
            operations, expected_id,
        )


@dataclass(frozen=True, slots=True)
class TransactionResult:
    plan_id: str
    outcome: TransactionOutcome
    decision: Decision
    outputs: tuple[str, ...]
    before_content_sha256: str | None
    after_content_sha256: str | None
    rollback_content_sha256: str | None
    evidence_sha256: str

    @classmethod
    def create(
        cls, plan_id: str, outcome: TransactionOutcome, decision: Decision, outputs: Iterable[str],
        before: str | None, after: str | None, rollback: str | None,
    ) -> "TransactionResult":
        bounded = tuple(str(item)[:512] for item in outputs)
        identity = {
            "plan_id": plan_id, "outcome": outcome.value, "decision": decision.value,
            "outputs": list(bounded), "before_content_sha256": before,
            "after_content_sha256": after, "rollback_content_sha256": rollback,
        }
        return cls(plan_id, outcome, decision, bounded, before, after, rollback, sha256_json(identity))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0", "plan_id": self.plan_id, "outcome": self.outcome.value,
            "decision": self.decision.value, "outputs": list(self.outputs),
            "before_content_sha256": self.before_content_sha256,
            "after_content_sha256": self.after_content_sha256,
            "rollback_content_sha256": self.rollback_content_sha256,
            "evidence_sha256": self.evidence_sha256,
        }


def build_plan(
    spec: ReleaseSpec, bundle_root: Path, live_root: Path,
    *, limits: CaptureLimits = CaptureLimits(),
) -> DeploymentPlan:
    bundle = capture_directory(LayerName.BUNDLE, bundle_root, spec, limits)
    live = capture_directory(LayerName.LIVE, live_root, spec, limits)
    return DeploymentPlan.create(spec, bundle, live)


def _safe_root(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.exists() or not path.is_dir():
        raise ContractError(f"{label} must be an existing non-symlink directory")
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or len(resolved.parts) < 3:
        raise ContractError(f"{label} is too broad for a local transaction")
    return resolved


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(descriptor)
    try:
        shutil.copyfile(source, temporary, follow_symlinks=False)
        with open(temporary, "rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _clear_directory(root: Path) -> None:
    for child in root.iterdir():
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


def _restore_snapshot(snapshot: Path, live_root: Path) -> None:
    _clear_directory(live_root)
    for source in sorted(snapshot.rglob("*")):
        relative = source.relative_to(snapshot)
        destination = live_root / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif source.is_file() and not source.is_symlink():
            _atomic_copy(source, destination)
        else:
            raise ContractError("rollback snapshot contains a forbidden entry")


def _marker_path(rollback_root: Path, plan: DeploymentPlan) -> Path:
    return rollback_root / plan.plan_id / "state.json"


def apply_plan(
    plan: DeploymentPlan, spec: ReleaseSpec, bundle_root: Path, live_root: Path, rollback_root: Path,
    *, confirm_plan_id: str, limits: CaptureLimits = CaptureLimits(),
) -> TransactionResult:
    if confirm_plan_id != plan.plan_id or spec.spec_sha256 != plan.spec_sha256:
        return TransactionResult.create(
            plan.plan_id, TransactionOutcome.BLOCKED, Decision.BLOCKED,
            ("plan confirmation or release spec does not match",), None, None, None,
        )
    bundle = _safe_root(bundle_root, "bundle_root")
    live = _safe_root(live_root, "live_root")
    rollback = rollback_root.resolve()
    if rollback == live or rollback == bundle or live in rollback.parents or bundle in rollback.parents:
        raise ContractError("rollback_root must be separate from bundle and live roots")
    current_bundle = capture_directory(LayerName.BUNDLE, bundle, spec, limits)
    current_live = capture_directory(LayerName.LIVE, live, spec, limits)
    before = content_sha256(current_live)
    if current_bundle.state is CaptureState.BLOCKED or current_live.state is CaptureState.BLOCKED:
        return TransactionResult.create(
            plan.plan_id, TransactionOutcome.BLOCKED, Decision.BLOCKED,
            ("precondition inventory capture was blocked",), before, None, None,
        )
    transaction_dir = rollback / plan.plan_id
    snapshot = transaction_dir / "snapshot"
    marker = transaction_dir / "state.json"
    if marker.exists():
        try:
            state = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
        bundle_matches = content_sha256(current_bundle) == plan.desired_bundle_content_sha256
        if state.get("status") == "applied" and bundle_matches and before == plan.desired_bundle_content_sha256:
            return TransactionResult.create(
                plan.plan_id, TransactionOutcome.APPLIED, Decision.VERIFIED,
                ("plan was already applied; no bytes changed",), before, before, None,
            )
        return TransactionResult.create(
            plan.plan_id, TransactionOutcome.BLOCKED, Decision.BLOCKED,
            ("transaction evidence already exists in a non-replayable state",), before, before, None,
        )
    if content_sha256(current_bundle) != plan.desired_bundle_content_sha256 or before != plan.expected_live_content_sha256:
        return TransactionResult.create(
            plan.plan_id, TransactionOutcome.BLOCKED, Decision.BLOCKED,
            ("bundle or live bytes changed after dry-run",), before, None, None,
        )
    transaction_dir.mkdir(parents=True, exist_ok=False)
    shutil.copytree(live, snapshot, symlinks=True)
    outputs: list[str] = []
    try:
        for operation in plan.operations:
            destination = live / operation.path
            if operation.kind is OperationKind.WRITE:
                source = bundle / operation.path
                if source.is_symlink() or not source.is_file():
                    raise ContractError(f"bundle artifact unavailable during apply: {operation.path}")
                _atomic_copy(source, destination)
                outputs.append(f"write {operation.path}")
            else:
                if destination.exists() or destination.is_symlink():
                    if destination.is_dir() and not destination.is_symlink():
                        raise ContractError(f"refusing to delete directory operation: {operation.path}")
                    destination.unlink()
                outputs.append(f"delete {operation.path}")
        after_inventory = capture_directory(LayerName.LIVE, live, spec, limits)
        after = content_sha256(after_inventory)
        if after != plan.desired_bundle_content_sha256:
            raise ContractError("post-apply live content does not match the bundle")
        write_json_atomic(marker, {"schema_version": "1.0", "plan_id": plan.plan_id, "status": "applied"})
        return TransactionResult.create(
            plan.plan_id, TransactionOutcome.APPLIED, Decision.VERIFIED,
            (*outputs, "post-apply live content matches bundle"), before, after, None,
        )
    except Exception as exc:
        _restore_snapshot(snapshot, live)
        restored = content_sha256(capture_directory(LayerName.LIVE, live, spec, limits))
        write_json_atomic(marker, {
            "schema_version": "1.0", "plan_id": plan.plan_id, "status": "auto_rolled_back",
            "error": type(exc).__name__,
        })
        return TransactionResult.create(
            plan.plan_id, TransactionOutcome.AUTO_ROLLED_BACK, Decision.BLOCKED,
            (*outputs, f"apply failed: {type(exc).__name__}", "original live snapshot restored"),
            before, None, restored,
        )


def verify_applied(
    plan: DeploymentPlan, spec: ReleaseSpec, live_root: Path,
    *, limits: CaptureLimits = CaptureLimits(),
) -> TransactionResult:
    live = capture_directory(LayerName.LIVE, live_root, spec, limits)
    current = content_sha256(live)
    matched = live.state is CaptureState.CAPTURED and current == plan.desired_bundle_content_sha256
    return TransactionResult.create(
        plan.plan_id, TransactionOutcome.VERIFIED if matched else TransactionOutcome.BLOCKED,
        Decision.VERIFIED if matched else Decision.DEGRADED,
        ("live content matches planned bundle",) if matched else ("live content drifts from planned bundle",),
        None, current, None,
    )


def rollback_plan(
    plan: DeploymentPlan, spec: ReleaseSpec, live_root: Path, rollback_root: Path,
    *, confirm_plan_id: str, limits: CaptureLimits = CaptureLimits(),
) -> TransactionResult:
    if confirm_plan_id != plan.plan_id:
        return TransactionResult.create(
            plan.plan_id, TransactionOutcome.BLOCKED, Decision.BLOCKED,
            ("plan confirmation does not match",), None, None, None,
        )
    live = _safe_root(live_root, "live_root")
    marker = _marker_path(rollback_root.resolve(), plan)
    snapshot = marker.parent / "snapshot"
    if not marker.is_file() or not snapshot.is_dir():
        return TransactionResult.create(
            plan.plan_id, TransactionOutcome.BLOCKED, Decision.BLOCKED,
            ("rollback evidence or snapshot is missing",), None, None, None,
        )
    try:
        state = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    if state.get("plan_id") != plan.plan_id or state.get("status") != "applied":
        return TransactionResult.create(
            plan.plan_id, TransactionOutcome.BLOCKED, Decision.BLOCKED,
            ("transaction is not in an applied state",), None, None, None,
        )
    before = content_sha256(capture_directory(LayerName.LIVE, live, spec, limits))
    _restore_snapshot(snapshot, live)
    restored = content_sha256(capture_directory(LayerName.LIVE, live, spec, limits))
    if restored != plan.expected_live_content_sha256:
        return TransactionResult.create(
            plan.plan_id, TransactionOutcome.BLOCKED, Decision.BLOCKED,
            ("rollback completed but original live hash was not restored",), before, None, restored,
        )
    write_json_atomic(marker, {"schema_version": "1.0", "plan_id": plan.plan_id, "status": "rolled_back"})
    return TransactionResult.create(
        plan.plan_id, TransactionOutcome.ROLLED_BACK, Decision.VERIFIED,
        ("original live snapshot restored exactly",), before, None, restored,
    )
