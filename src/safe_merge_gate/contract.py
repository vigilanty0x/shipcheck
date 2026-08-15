"""Bounded, machine-readable contracts for offline merge decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0"
TOOL_VERSION = "0.1.0"
MAX_TEXT = 4_096
MAX_CHANGES = 500
MAX_CHECKS = 100
MAX_FINDINGS = 100


class ContractError(ValueError):
    pass


class CheckState(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    MISSING = "missing"


class Decision(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: object, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{name} must be a string")
    value = value.strip()
    if not value and not allow_empty:
        raise ContractError(f"{name} must not be empty")
    if len(value) > MAX_TEXT:
        raise ContractError(f"{name} exceeds {MAX_TEXT} characters")
    return value


def _sha(value: object, name: str) -> str:
    value = _text(value, name).lower()
    if len(value) not in {40, 64} or any(char not in "0123456789abcdef" for char in value):
        raise ContractError(f"{name} must be a 40- or 64-character hexadecimal SHA")
    return value


def _timestamp(value: object) -> str:
    value = _text(value, "captured_at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("captured_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ContractError("captured_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Change:
    path: str
    additions: int
    deletions: int
    binary: bool = False

    def __post_init__(self) -> None:
        path = _text(self.path, "change.path")
        posix = PurePosixPath(path)
        if posix.is_absolute() or ".." in posix.parts or path.startswith("./") or "\\" in path:
            raise ContractError("change.path must be a normalized relative POSIX path")
        object.__setattr__(self, "path", path)
        for name, value in (("additions", self.additions), ("deletions", self.deletions)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ContractError(f"change.{name} must be a non-negative integer")
        if not isinstance(self.binary, bool):
            raise ContractError("change.binary must be boolean")

    @property
    def changed_lines(self) -> int:
        return self.additions + self.deletions

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "additions": self.additions, "deletions": self.deletions, "binary": self.binary}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Change":
        return cls(value.get("path"), value.get("additions"), value.get("deletions"), value.get("binary", False))


@dataclass(frozen=True, slots=True)
class SecretFinding:
    fingerprint: str
    path: str
    kind: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "fingerprint", _sha(self.fingerprint, "finding.fingerprint"))
        clean_path = Change(self.path, 0, 0).path
        object.__setattr__(self, "path", clean_path)
        object.__setattr__(self, "kind", _text(self.kind, "finding.kind"))

    def to_dict(self) -> dict[str, str]:
        return {"fingerprint": self.fingerprint, "path": self.path, "kind": self.kind}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SecretFinding":
        return cls(value.get("fingerprint"), value.get("path"), value.get("kind"))


@dataclass(frozen=True, slots=True)
class MergeSnapshot:
    repository: str
    expected_sha: str
    observed_sha: str
    merge_sha: str
    captured_at: str
    ci: Mapping[str, CheckState]
    required_ci: tuple[str, ...]
    optional_ci: tuple[str, ...]
    tests_complete: bool
    tests_passed: bool
    secret_scan_complete: bool
    secret_findings: tuple[SecretFinding, ...]
    clean_tree: bool
    changes: tuple[Change, ...]
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractError(f"unsupported schema_version: {self.schema_version}")
        object.__setattr__(self, "repository", _text(self.repository, "repository"))
        object.__setattr__(self, "expected_sha", _sha(self.expected_sha, "expected_sha"))
        object.__setattr__(self, "observed_sha", _sha(self.observed_sha, "observed_sha"))
        object.__setattr__(self, "merge_sha", _sha(self.merge_sha, "merge_sha"))
        object.__setattr__(self, "captured_at", _timestamp(self.captured_at))
        if len(self.ci) > MAX_CHECKS:
            raise ContractError(f"ci exceeds {MAX_CHECKS} checks")
        clean_ci: dict[str, CheckState] = {}
        for key, value in self.ci.items():
            key = _text(key, "ci name")
            try:
                clean_ci[key] = value if isinstance(value, CheckState) else CheckState(value)
            except ValueError as exc:
                raise ContractError(f"invalid CI state for {key}") from exc
        object.__setattr__(self, "ci", dict(sorted(clean_ci.items())))
        required = tuple(_text(item, "required_ci") for item in self.required_ci)
        optional = tuple(_text(item, "optional_ci") for item in self.optional_ci)
        if len(set(required)) != len(required) or len(set(optional)) != len(optional):
            raise ContractError("CI check names must be unique")
        if set(required) & set(optional):
            raise ContractError("required_ci and optional_ci must not overlap")
        object.__setattr__(self, "required_ci", tuple(sorted(required)))
        object.__setattr__(self, "optional_ci", tuple(sorted(optional)))
        for name in ("tests_complete", "tests_passed", "secret_scan_complete", "clean_tree"):
            if not isinstance(getattr(self, name), bool):
                raise ContractError(f"{name} must be boolean")
        if len(self.secret_findings) > MAX_FINDINGS:
            raise ContractError(f"secret_findings exceeds {MAX_FINDINGS}")
        if len(self.changes) > MAX_CHANGES:
            raise ContractError(f"changes exceeds {MAX_CHANGES}")
        paths = [change.path for change in self.changes]
        if len(paths) != len(set(paths)):
            raise ContractError("change paths must be unique")
        object.__setattr__(self, "changes", tuple(sorted(self.changes, key=lambda item: item.path)))
        object.__setattr__(self, "secret_findings", tuple(sorted(self.secret_findings, key=lambda item: (item.path, item.fingerprint))))

    @property
    def inventory(self) -> dict[str, object]:
        changes = [item.to_dict() for item in self.changes]
        return {
            "files": len(changes),
            "changed_lines": sum(item.changed_lines for item in self.changes),
            "binary_files": sum(item.binary for item in self.changes),
            "changes": changes,
        }

    @property
    def inventory_sha256(self) -> str:
        return sha256_json(self.inventory)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version, "repository": self.repository,
            "expected_sha": self.expected_sha, "observed_sha": self.observed_sha,
            "merge_sha": self.merge_sha, "captured_at": self.captured_at,
            "ci": {key: value.value for key, value in self.ci.items()},
            "required_ci": list(self.required_ci), "optional_ci": list(self.optional_ci),
            "tests_complete": self.tests_complete, "tests_passed": self.tests_passed,
            "secret_scan_complete": self.secret_scan_complete,
            "secret_findings": [item.to_dict() for item in self.secret_findings],
            "clean_tree": self.clean_tree, "inventory": self.inventory,
        }

    @property
    def sha256(self) -> str:
        return sha256_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MergeSnapshot":
        inventory = value.get("inventory")
        if not isinstance(inventory, Mapping):
            raise ContractError("inventory must be an object")
        raw_changes = inventory.get("changes")
        raw_findings = value.get("secret_findings", [])
        if not isinstance(raw_changes, Sequence) or isinstance(raw_changes, (str, bytes)):
            raise ContractError("inventory.changes must be an array")
        if not isinstance(raw_findings, Sequence) or isinstance(raw_findings, (str, bytes)):
            raise ContractError("secret_findings must be an array")
        ci = value.get("ci")
        if not isinstance(ci, Mapping):
            raise ContractError("ci must be an object")
        item = cls(
            repository=value.get("repository"), expected_sha=value.get("expected_sha"),
            observed_sha=value.get("observed_sha"), merge_sha=value.get("merge_sha"),
            captured_at=value.get("captured_at"), ci=ci,
            required_ci=tuple(value.get("required_ci", ())), optional_ci=tuple(value.get("optional_ci", ())),
            tests_complete=value.get("tests_complete"), tests_passed=value.get("tests_passed"),
            secret_scan_complete=value.get("secret_scan_complete"),
            secret_findings=tuple(SecretFinding.from_dict(item) for item in raw_findings if isinstance(item, Mapping)),
            clean_tree=value.get("clean_tree"),
            changes=tuple(Change.from_dict(item) for item in raw_changes if isinstance(item, Mapping)),
            schema_version=value.get("schema_version", ""),
        )
        for name in ("files", "changed_lines", "binary_files"):
            if name in inventory and inventory.get(name) != item.inventory[name]:
                raise ContractError(f"inventory {name} does not match canonical changes")
        return item


@dataclass(frozen=True, slots=True)
class GatePolicy:
    max_changed_files: int = 100
    max_changed_lines: int = 5_000
    max_binary_files: int = 5
    require_clean_tree: bool = True
    require_tests: bool = True
    require_secret_scan: bool = True
    policy_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("max_changed_files", "max_changed_lines", "max_binary_files"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ContractError(f"{name} must be a non-negative integer")
        for name in ("require_clean_tree", "require_tests", "require_secret_scan"):
            if not isinstance(getattr(self, name), bool):
                raise ContractError(f"{name} must be boolean")
        object.__setattr__(self, "policy_version", _text(self.policy_version, "policy_version"))

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "max_changed_files": self.max_changed_files,
            "max_changed_lines": self.max_changed_lines,
            "max_binary_files": self.max_binary_files,
            "require_clean_tree": self.require_clean_tree,
            "require_tests": self.require_tests,
            "require_secret_scan": self.require_secret_scan,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GatePolicy":
        return cls(
            max_changed_files=value.get("max_changed_files", 100),
            max_changed_lines=value.get("max_changed_lines", 5_000),
            max_binary_files=value.get("max_binary_files", 5),
            require_clean_tree=value.get("require_clean_tree", True),
            require_tests=value.get("require_tests", True),
            require_secret_scan=value.get("require_secret_scan", True),
            policy_version=value.get("policy_version", "1.0"),
        )


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    state: CheckState
    required: bool
    message: str
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "check.name"))
        if not isinstance(self.state, CheckState):
            try:
                object.__setattr__(self, "state", CheckState(self.state))
            except ValueError as exc:
                raise ContractError("invalid check state") from exc
        if not isinstance(self.required, bool):
            raise ContractError("check.required must be boolean")
        object.__setattr__(self, "message", _text(self.message, "check.message"))
        if not isinstance(self.evidence, Mapping):
            raise ContractError("check.evidence must be an object")

    @property
    def success(self) -> bool:
        return self.state is CheckState.SUCCESS

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name, "state": self.state.value, "success": self.success,
            "required": self.required, "message": self.message, "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Check":
        return cls(
            _text(value.get("name"), "check.name"), CheckState(value.get("state")),
            value.get("required"), _text(value.get("message"), "check.message"),
            value.get("evidence", {}),
        )


@dataclass(frozen=True, slots=True)
class GateArtifact:
    decision: Decision
    snapshot: MergeSnapshot
    policy: GatePolicy
    checks: tuple[Check, ...]
    generated_at: str
    outputs: Mapping[str, object]
    tool_version: str = TOOL_VERSION
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractError(f"unsupported artifact schema_version: {self.schema_version}")
        if self.tool_version != TOOL_VERSION:
            raise ContractError(f"unsupported tool_version: {self.tool_version}")
        if not isinstance(self.decision, Decision):
            object.__setattr__(self, "decision", Decision(self.decision))
        object.__setattr__(self, "generated_at", _timestamp(self.generated_at))
        if not isinstance(self.outputs, Mapping):
            raise ContractError("artifact outputs must be an object")
        if self.decision is Decision.READY and any(check.required and not check.success for check in self.checks):
            raise ContractError("ready artifact contains a failing required check")

    @property
    def ready(self) -> bool:
        return self.decision is Decision.READY

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version, "tool_version": self.tool_version,
            "generated_at": self.generated_at, "decision": self.decision.value,
            "ready": self.ready, "snapshot_sha256": self.snapshot.sha256,
            "inventory_sha256": self.snapshot.inventory_sha256,
            "policy": self.policy.to_dict(), "policy_sha256": sha256_json(self.policy.to_dict()),
            "checks": [item.to_dict() for item in self.checks], "outputs": dict(self.outputs),
            "snapshot": self.snapshot.to_dict(),
        }

    @property
    def sha256(self) -> str:
        return sha256_json(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        return {**self.body_dict(), "artifact_sha256": self.sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, verify: bool = True) -> "GateArtifact":
        snapshot = value.get("snapshot")
        policy = value.get("policy")
        checks = value.get("checks")
        if not isinstance(snapshot, Mapping) or not isinstance(policy, Mapping) or not isinstance(checks, Sequence):
            raise ContractError("artifact snapshot/policy/checks malformed")
        item = cls(
            decision=Decision(value.get("decision")), snapshot=MergeSnapshot.from_dict(snapshot),
            policy=GatePolicy.from_dict(policy),
            checks=tuple(Check.from_dict(check) for check in checks if isinstance(check, Mapping)),
            generated_at=_timestamp(value.get("generated_at")), outputs=value.get("outputs", {}),
            tool_version=value.get("tool_version", ""), schema_version=value.get("schema_version", ""),
        )
        summaries = {
            "ready": item.ready,
            "snapshot_sha256": item.snapshot.sha256,
            "inventory_sha256": item.snapshot.inventory_sha256,
            "policy_sha256": sha256_json(item.policy.to_dict()),
        }
        for name, expected in summaries.items():
            if value.get(name) != expected:
                raise ContractError(f"artifact {name} does not match canonical content")
        if verify and value.get("artifact_sha256") != item.sha256:
            raise ContractError("artifact SHA-256 mismatch")
        return item
