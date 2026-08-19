"""Atomic report publication with verification receipts and explicit rollback."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .models import ReviewReport, ValidationError, canonical_json


class PublicationError(RuntimeError):
    """Raised when a publication or rollback cannot be proven safe."""


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def report_payload(report: ReviewReport) -> bytes:
    return (json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")


@dataclass(frozen=True, slots=True)
class PublicationPlan:
    output_path: str
    backup_path: str
    payload_sha: str
    previous_sha: str | None
    creates_new: bool
    steps: tuple[str, ...] = ("stage", "apply", "verify")

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_path": self.output_path,
            "backup_path": self.backup_path,
            "payload_sha": self.payload_sha,
            "previous_sha": self.previous_sha,
            "creates_new": self.creates_new,
            "steps": list(self.steps),
        }


@dataclass(frozen=True, slots=True)
class TransactionReceipt:
    schema_version: str
    transaction_id: str
    state: str
    output_path: str
    backup_path: str | None
    previous_sha: str | None
    applied_sha: str
    verified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "transaction_id": self.transaction_id,
            "state": self.state,
            "output_path": self.output_path,
            "backup_path": self.backup_path,
            "previous_sha": self.previous_sha,
            "applied_sha": self.applied_sha,
            "verified": self.verified,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TransactionReceipt":
        required = {
            "schema_version", "transaction_id", "state", "output_path",
            "backup_path", "previous_sha", "applied_sha", "verified",
        }
        if not isinstance(data, dict) or not required.issubset(data):
            raise ValidationError("invalid transaction receipt")
        if data["schema_version"] != "1.0" or data["state"] != "verified":
            raise ValidationError("unsupported or non-verified transaction receipt")
        return cls(**{key: data[key] for key in required})


class ReportPublisher:
    def plan(self, report: ReviewReport, output_path: str | Path) -> PublicationPlan:
        output = Path(output_path).expanduser().resolve()
        if output.exists() and not output.is_file():
            raise PublicationError("output path exists and is not a regular file")
        payload_sha = _sha_bytes(report_payload(report))
        backup = output.with_name(f".{output.name}.{payload_sha[:12]}.bak")
        previous_sha = _sha_file(output) if output.exists() else None
        return PublicationPlan(
            output_path=str(output),
            backup_path=str(backup),
            payload_sha=payload_sha,
            previous_sha=previous_sha,
            creates_new=not output.exists(),
        )

    def apply(self, plan: PublicationPlan, report: ReviewReport) -> TransactionReceipt:
        output = Path(plan.output_path)
        backup = Path(plan.backup_path)
        payload = report_payload(report)
        if _sha_bytes(payload) != plan.payload_sha:
            raise PublicationError("report changed after planning")
        if output.exists() != (not plan.creates_new):
            raise PublicationError("output existence changed after planning")
        if output.exists() and _sha_file(output) != plan.previous_sha:
            raise PublicationError("output content changed after planning")
        if backup.exists():
            raise PublicationError("refusing to overwrite an existing rollback backup")
        output.parent.mkdir(parents=True, exist_ok=True)
        moved_old = False
        try:
            if output.exists():
                os.replace(output, backup)
                moved_old = True
            with tempfile.NamedTemporaryFile("wb", dir=output.parent, prefix=f".{output.name}.", delete=False) as stream:
                staged = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staged, output)
        except Exception:
            if moved_old and backup.exists() and not output.exists():
                os.replace(backup, output)
            raise
        verified = output.is_file() and _sha_file(output) == plan.payload_sha
        transaction_id = hashlib.sha256(
            canonical_json([plan.output_path, plan.payload_sha, plan.previous_sha]).encode("utf-8")
        ).hexdigest()
        receipt = TransactionReceipt(
            schema_version="1.0",
            transaction_id=transaction_id,
            state="verified" if verified else "blocked",
            output_path=plan.output_path,
            backup_path=str(backup) if moved_old else None,
            previous_sha=plan.previous_sha,
            applied_sha=plan.payload_sha,
            verified=verified,
        )
        if not verified:
            self._rollback_unverified(receipt)
            raise PublicationError("functional verification failed; rollback attempted")
        return receipt

    def verify(self, receipt: TransactionReceipt) -> bool:
        output = Path(receipt.output_path)
        return receipt.verified and output.is_file() and _sha_file(output) == receipt.applied_sha

    def rollback(self, receipt: TransactionReceipt) -> dict[str, Any]:
        output = Path(receipt.output_path)
        if not output.is_file() or _sha_file(output) != receipt.applied_sha:
            raise PublicationError("refusing rollback because the served output no longer matches the receipt")
        if receipt.backup_path:
            backup = Path(receipt.backup_path)
            if not backup.is_file() or _sha_file(backup) != receipt.previous_sha:
                raise PublicationError("rollback backup is missing or changed")
            os.replace(backup, output)
        else:
            output.unlink()
        restored = (
            output.is_file() and receipt.previous_sha is not None and _sha_file(output) == receipt.previous_sha
        ) or (receipt.previous_sha is None and not output.exists())
        if not restored:
            raise PublicationError("rollback could not be verified")
        return {
            "transaction_id": receipt.transaction_id,
            "state": "rolled_back",
            "restored_sha": receipt.previous_sha,
            "verified": True,
        }

    def _rollback_unverified(self, receipt: TransactionReceipt) -> None:
        output = Path(receipt.output_path)
        backup = Path(receipt.backup_path) if receipt.backup_path else None
        if backup and backup.exists():
            os.replace(backup, output)
        elif output.exists():
            output.unlink()


def write_receipt(receipt: TransactionReceipt, path: str | Path) -> None:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(receipt.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile("wb", dir=target.parent, prefix=f".{target.name}.", delete=False) as stream:
        staged = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staged, target)
