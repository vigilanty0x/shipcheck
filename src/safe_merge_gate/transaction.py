"""Local file transaction with dry-run, verification, and exact rollback."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping

from .contract import ContractError, Decision, GateArtifact, canonical_json, utc_now


class TransactionError(RuntimeError):
    pass


class ApplyBlocked(TransactionError):
    pass


class TransactionConflict(TransactionError):
    pass


class TransactionVerificationError(TransactionError):
    pass


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_replace(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
class Receipt:
    state_path: str
    artifact_sha256: str
    expected_before_sha: str
    merge_sha: str
    before_exists: bool
    before_bytes_b64: str
    before_bytes_sha256: str
    after_bytes_sha256: str
    created_at: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.schema_version != "1.0":
            raise ContractError("unsupported receipt schema_version")
        if not isinstance(self.state_path, str) or not self.state_path:
            raise ContractError("receipt state_path must be a non-empty string")
        for name in ("artifact_sha256", "before_bytes_sha256", "after_bytes_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ContractError(f"receipt {name} must be a SHA-256")
        for name in ("expected_before_sha", "merge_sha"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) not in {40, 64} or any(c not in "0123456789abcdef" for c in value):
                raise ContractError(f"receipt {name} must be a Git SHA")
        if not isinstance(self.before_exists, bool):
            raise ContractError("receipt before_exists must be boolean")
        if not isinstance(self.before_bytes_b64, str):
            raise ContractError("receipt before_bytes_b64 must be a string")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise ContractError("receipt created_at must be a string")

    def to_dict(self) -> dict[str, object]:
        body = {
            "schema_version": self.schema_version, "state_path": self.state_path,
            "artifact_sha256": self.artifact_sha256,
            "expected_before_sha": self.expected_before_sha, "merge_sha": self.merge_sha,
            "before_exists": self.before_exists, "before_bytes_b64": self.before_bytes_b64,
            "before_bytes_sha256": self.before_bytes_sha256,
            "after_bytes_sha256": self.after_bytes_sha256, "created_at": self.created_at,
        }
        return {**body, "receipt_sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Receipt":
        kwargs = {key: value.get(key) for key in (
            "state_path", "artifact_sha256", "expected_before_sha", "merge_sha",
            "before_exists", "before_bytes_b64", "before_bytes_sha256",
            "after_bytes_sha256", "created_at", "schema_version",
        )}
        item = cls(**kwargs)
        if value.get("receipt_sha256") != item.to_dict()["receipt_sha256"]:
            raise ContractError("receipt SHA-256 mismatch")
        try:
            before = base64.b64decode(item.before_bytes_b64, validate=True)
        except ValueError as exc:
            raise ContractError("receipt before bytes are invalid") from exc
        if _digest(before) != item.before_bytes_sha256:
            raise ContractError("receipt before-byte SHA-256 mismatch")
        return item


class LocalMergeTransaction:
    def dry_run(self, artifact: GateArtifact, state_path: str | os.PathLike[str]) -> dict[str, object]:
        path = Path(state_path)
        current = self._read_current(path)
        applicable = artifact.decision is Decision.READY and current == artifact.snapshot.observed_sha
        reasons: list[str] = []
        if artifact.decision is not Decision.READY:
            reasons.append(f"decision is {artifact.decision.value}")
        if current != artifact.snapshot.observed_sha:
            reasons.append("local SHA differs from artifact observed SHA")
        return {
            "mode": "dry-run", "applicable": applicable, "state_path": str(path),
            "current_sha": current, "merge_sha": artifact.snapshot.merge_sha,
            "artifact_sha256": artifact.sha256, "reasons": reasons,
        }

    def apply(
        self, artifact: GateArtifact, state_path: str | os.PathLike[str],
        receipt_path: str | os.PathLike[str], *, created_at: str | None = None,
    ) -> Receipt:
        path, receipt_file = Path(state_path), Path(receipt_path)
        if receipt_file.exists():
            raise TransactionConflict("receipt path already exists")
        preview = self.dry_run(artifact, path)
        if artifact.decision is not Decision.READY:
            raise ApplyBlocked(f"artifact decision is {artifact.decision.value}")
        if not preview["applicable"]:
            raise TransactionConflict("local SHA differs from artifact observed SHA")
        before_exists = path.exists()
        before = path.read_bytes() if before_exists else b""
        after_object = {
            "schema_version": "1.0", "repository": artifact.snapshot.repository,
            "current_sha": artifact.snapshot.merge_sha, "artifact_sha256": artifact.sha256,
        }
        after = (canonical_json(after_object) + "\n").encode("utf-8")
        receipt = Receipt(
            state_path=str(path), artifact_sha256=artifact.sha256,
            expected_before_sha=artifact.snapshot.observed_sha, merge_sha=artifact.snapshot.merge_sha,
            before_exists=before_exists, before_bytes_b64=base64.b64encode(before).decode("ascii"),
            before_bytes_sha256=_digest(before), after_bytes_sha256=_digest(after),
            created_at=created_at or utc_now(),
        )
        _write_new(receipt_file, (canonical_json(receipt.to_dict()) + "\n").encode("utf-8"))
        try:
            _atomic_replace(path, after)
            self.verify(receipt, path)
        except Exception:
            self._restore(receipt, path)
            raise
        return receipt

    def verify(self, receipt: Receipt, state_path: str | os.PathLike[str]) -> dict[str, object]:
        path = Path(state_path)
        if str(path) != receipt.state_path:
            raise TransactionVerificationError("state path differs from receipt")
        if not path.exists():
            raise TransactionVerificationError("applied state is missing")
        data = path.read_bytes()
        if _digest(data) != receipt.after_bytes_sha256:
            raise TransactionVerificationError("applied bytes differ from receipt")
        current = self._read_current(path)
        if current != receipt.merge_sha:
            raise TransactionVerificationError("applied SHA differs from receipt")
        return {"verified": True, "current_sha": current, "bytes_sha256": _digest(data)}

    def rollback(self, receipt: Receipt, state_path: str | os.PathLike[str]) -> dict[str, object]:
        path = Path(state_path)
        if str(path) != receipt.state_path:
            raise TransactionConflict("state path differs from receipt")
        before = base64.b64decode(receipt.before_bytes_b64, validate=True)
        if _digest(before) != receipt.before_bytes_sha256:
            raise TransactionVerificationError("receipt before bytes are corrupt")
        if path.exists():
            current_digest = _digest(path.read_bytes())
            if current_digest == receipt.before_bytes_sha256 and receipt.before_exists:
                return {"rolled_back": True, "idempotent": True, "restored_sha256": current_digest}
            if current_digest != receipt.after_bytes_sha256:
                raise TransactionConflict("state changed after apply; refusing rollback")
        elif receipt.before_exists:
            raise TransactionConflict("state disappeared after apply; refusing rollback")
        self._restore(receipt, path)
        restored = path.read_bytes() if path.exists() else b""
        if _digest(restored) != receipt.before_bytes_sha256 or path.exists() != receipt.before_exists:
            raise TransactionVerificationError("rollback did not restore exact prior state")
        return {"rolled_back": True, "idempotent": False, "restored_sha256": _digest(restored)}

    @staticmethod
    def _restore(receipt: Receipt, path: Path) -> None:
        before = base64.b64decode(receipt.before_bytes_b64)
        if receipt.before_exists:
            _atomic_replace(path, before)
        elif path.exists():
            path.unlink()

    @staticmethod
    def _read_current(path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransactionConflict("state file is not valid UTF-8 JSON") from exc
        if not isinstance(value, Mapping):
            raise TransactionConflict("state root must be an object")
        current = value.get("current_sha")
        if not isinstance(current, str):
            raise TransactionConflict("state current_sha is missing")
        return current.lower()
