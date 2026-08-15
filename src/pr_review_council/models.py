"""Validated public data contracts for reviews and evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any, Iterable


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MAX_PATCH_BYTES = 256_000
MAX_FILES = 500


class ValidationError(ValueError):
    """Raised when an external input violates the bounded schema."""


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Decision(str, Enum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class ReviewerStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


def _bounded_text(value: Any, field: str, limit: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    text = value.strip()
    if not text and not allow_empty:
        raise ValidationError(f"{field} must not be empty")
    if len(value.encode("utf-8")) > limit:
        raise ValidationError(f"{field} exceeds {limit} bytes")
    return value


def _safe_path(value: Any) -> str:
    path = _bounded_text(value, "file path", 1_024)
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValidationError(f"unsafe file path: {path!r}")
    if candidate.parts[0] == ".git" or "\\" in path:
        raise ValidationError(f"unsafe file path: {path!r}")
    return candidate.as_posix()


@dataclass(frozen=True, slots=True)
class FileChange:
    path: str
    patch: str
    additions: int = 0
    deletions: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileChange":
        if not isinstance(data, dict):
            raise ValidationError("each file change must be an object")
        additions = data.get("additions", 0)
        deletions = data.get("deletions", 0)
        if not isinstance(additions, int) or additions < 0:
            raise ValidationError("additions must be a non-negative integer")
        if not isinstance(deletions, int) or deletions < 0:
            raise ValidationError("deletions must be a non-negative integer")
        return cls(
            path=_safe_path(data.get("path")),
            patch=_bounded_text(data.get("patch", ""), "patch", MAX_PATCH_BYTES, allow_empty=True),
            additions=additions,
            deletions=deletions,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "patch": self.patch,
            "additions": self.additions,
            "deletions": self.deletions,
        }


@dataclass(frozen=True, slots=True)
class PullRequestSnapshot:
    pr_id: str
    commit_sha: str
    title: str
    body: str
    files: tuple[FileChange, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PullRequestSnapshot":
        if not isinstance(data, dict):
            raise ValidationError("pull request input must be an object")
        sha = _bounded_text(data.get("commit_sha"), "commit_sha", 40).lower()
        if not SHA_PATTERN.fullmatch(sha):
            raise ValidationError("commit_sha must be exactly 40 lowercase hexadecimal characters")
        raw_files = data.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            raise ValidationError("files must be a non-empty array")
        if len(raw_files) > MAX_FILES:
            raise ValidationError(f"files exceeds {MAX_FILES} entries")
        files = tuple(FileChange.from_dict(item) for item in raw_files)
        paths = [item.path for item in files]
        if len(paths) != len(set(paths)):
            raise ValidationError("file paths must be unique")
        return cls(
            pr_id=_bounded_text(data.get("pr_id"), "pr_id", 128),
            commit_sha=sha,
            title=_bounded_text(data.get("title"), "title", 300),
            body=_bounded_text(data.get("body", ""), "body", 200_000, allow_empty=True),
            files=files,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pr_id": self.pr_id,
            "commit_sha": self.commit_sha,
            "title": self.title,
            "body": self.body,
            "files": [item.to_dict() for item in self.files],
        }


@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    reviewer: str
    severity: Severity
    title: str
    message: str
    path: str | None
    line: int | None
    fingerprint: str

    @classmethod
    def create(
        cls,
        *,
        rule_id: str,
        reviewer: str,
        severity: Severity,
        title: str,
        message: str,
        path: str | None = None,
        line: int | None = None,
    ) -> "Finding":
        rule_id = _bounded_text(rule_id, "rule_id", 128)
        reviewer = _bounded_text(reviewer, "reviewer", 128)
        title = _bounded_text(title, "finding title", 300)
        message = _bounded_text(message, "finding message", 2_000)
        if path is not None:
            path = _safe_path(path)
        if line is not None and (not isinstance(line, int) or line < 1):
            raise ValidationError("finding line must be a positive integer")
        identity = json.dumps(
            [rule_id, reviewer, severity.value, path, line, title],
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            rule_id=rule_id,
            reviewer=reviewer,
            severity=severity,
            title=title,
            message=message,
            path=path,
            line=line,
            fingerprint=hashlib.sha256(identity).hexdigest(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "reviewer": self.reviewer,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "path": self.path,
            "line": self.line,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ReviewerOutcome:
    reviewer: str
    status: ReviewerStatus
    finding_count: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewer": self.reviewer,
            "status": self.status.value,
            "finding_count": self.finding_count,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class ReviewReport:
    schema_version: str
    tool_version: str
    pr_id: str
    commit_sha: str
    decision: Decision
    degraded: bool
    outcomes: tuple[ReviewerOutcome, ...]
    findings: tuple[Finding, ...]
    summary: dict[str, int]
    report_sha: str

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "pr_id": self.pr_id,
            "commit_sha": self.commit_sha,
            "decision": self.decision.value,
            "degraded": self.degraded,
            "outcomes": [item.to_dict() for item in self.outcomes],
            "findings": [item.to_dict() for item in self.findings],
            "summary": dict(sorted(self.summary.items())),
        }

    def to_dict(self) -> dict[str, Any]:
        result = self.unsigned_dict()
        result["report_sha"] = self.report_sha
        return result


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def digest(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def severity_counts(findings: Iterable[Finding]) -> dict[str, int]:
    counts = {severity.value: 0 for severity in Severity}
    for finding in findings:
        counts[finding.severity.value] += 1
    return counts
