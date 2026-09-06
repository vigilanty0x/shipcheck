"""Bundled deterministic reviewers. They never call a network or model API."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Protocol

from .models import FileChange, Finding, PullRequestSnapshot, Severity


class Reviewer(Protocol):
    name: str

    def review(self, snapshot: PullRequestSnapshot) -> tuple[Finding, ...]: ...


HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def added_lines(change: FileChange) -> Iterable[tuple[int, str]]:
    """Yield target line numbers and added content from a bounded unified diff."""

    current = 0
    for raw in change.patch.splitlines():
        match = HUNK.match(raw)
        if match:
            current = int(match.group(1))
            continue
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if raw.startswith("+"):
            yield max(current, 1), raw[1:]
            current += 1
        elif raw.startswith("-"):
            continue
        elif not raw.startswith("\\"):
            current += 1


@dataclass(frozen=True, slots=True)
class SecurityReviewer:
    name: str = "security"

    _secret = re.compile(
        r"AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
        r"(?i:(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*['\"][^'\"]{8,})"
    )
    _code_execution = re.compile(r"\b(?:eval|exec)\s*\(|shell\s*=\s*True")

    def review(self, snapshot: PullRequestSnapshot) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        for change in snapshot.files:
            for line, content in added_lines(change):
                if self._secret.search(content):
                    findings.append(Finding.create(
                        rule_id="SEC001",
                        reviewer=self.name,
                        severity=Severity.CRITICAL,
                        title="Potential secret in added content",
                        message="A secret-shaped value was detected. Rotate it if real and replace it with a fixture or secret-store lookup.",
                        path=change.path,
                        line=line,
                    ))
                if self._code_execution.search(content):
                    findings.append(Finding.create(
                        rule_id="SEC002",
                        reviewer=self.name,
                        severity=Severity.HIGH,
                        title="Dynamic code or shell execution",
                        message="Avoid dynamic execution or shell parsing; use an allowlisted, argument-vector based operation.",
                        path=change.path,
                        line=line,
                    ))
        return tuple(findings)


@dataclass(frozen=True, slots=True)
class ReliabilityReviewer:
    name: str = "reliability"

    _network = re.compile(r"\b(?:requests|httpx)\.(?:get|post|put|patch|delete)\s*\(")
    _bare_except = re.compile(r"^\s*except\s*(?::|Exception\s*:)")

    def review(self, snapshot: PullRequestSnapshot) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        for change in snapshot.files:
            for line, content in added_lines(change):
                if self._network.search(content) and "timeout=" not in content:
                    findings.append(Finding.create(
                        rule_id="REL001",
                        reviewer=self.name,
                        severity=Severity.MEDIUM,
                        title="Network call without an explicit timeout",
                        message="Bound network latency with an explicit timeout and handle the timeout path.",
                        path=change.path,
                        line=line,
                    ))
                if self._bare_except.search(content):
                    findings.append(Finding.create(
                        rule_id="REL002",
                        reviewer=self.name,
                        severity=Severity.MEDIUM,
                        title="Over-broad exception handling",
                        message="Catch the narrow expected exception and preserve the failure signal.",
                        path=change.path,
                        line=line,
                    ))
        return tuple(findings)


def _is_test(path: str) -> bool:
    return path.startswith("tests/") or "/tests/" in path or path.endswith("_test.py") or path.endswith(".test.ts")


def _is_source(path: str) -> bool:
    return path.endswith((".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java")) and not _is_test(path)


@dataclass(frozen=True, slots=True)
class TestingReviewer:
    name: str = "testing"

    def review(self, snapshot: PullRequestSnapshot) -> tuple[Finding, ...]:
        source = [change for change in snapshot.files if _is_source(change.path)]
        tests = [change for change in snapshot.files if _is_test(change.path)]
        findings: list[Finding] = []
        if source and not tests:
            findings.append(Finding.create(
                rule_id="TST001",
                reviewer=self.name,
                severity=Severity.MEDIUM,
                title="Source change has no accompanying test change",
                message="Add or identify automated coverage for the changed behavior and its failure path.",
                path=source[0].path,
            ))
        for change in tests:
            if change.deletions > 0 and change.additions == 0:
                findings.append(Finding.create(
                    rule_id="TST002",
                    reviewer=self.name,
                    severity=Severity.HIGH,
                    title="Test file only removes coverage",
                    message="Explain the removed coverage or add a replacement assertion before merging.",
                    path=change.path,
                ))
        return tuple(findings)


@dataclass(frozen=True, slots=True)
class MaintainabilityReviewer:
    name: str = "maintainability"

    _debt = re.compile(r"\b(?:TODO|FIXME|HACK)\b")

    def review(self, snapshot: PullRequestSnapshot) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        for change in snapshot.files:
            if change.additions > 600:
                findings.append(Finding.create(
                    rule_id="MNT001",
                    reviewer=self.name,
                    severity=Severity.MEDIUM,
                    title="Large single-file change",
                    message="Split or document this large change so reviewers can verify it in bounded units.",
                    path=change.path,
                ))
            for line, content in added_lines(change):
                if self._debt.search(content):
                    findings.append(Finding.create(
                        rule_id="MNT002",
                        reviewer=self.name,
                        severity=Severity.LOW,
                        title="Untracked implementation debt marker",
                        message="Replace the debt marker with a tracked issue reference or resolve it in this change.",
                        path=change.path,
                        line=line,
                    ))
        return tuple(findings)


def default_reviewers() -> tuple[Reviewer, ...]:
    return (SecurityReviewer(), ReliabilityReviewer(), TestingReviewer(), MaintainabilityReviewer())
