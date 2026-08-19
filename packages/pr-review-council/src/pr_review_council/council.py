"""Council orchestration and structured, fail-closed synthesis."""

from __future__ import annotations

from dataclasses import replace

from . import __version__
from .config import CouncilConfig
from .models import (
    Decision,
    Finding,
    PullRequestSnapshot,
    ReviewerOutcome,
    ReviewerStatus,
    ReviewReport,
    Severity,
    ValidationError,
    digest,
    severity_counts,
)
from .reviewers import Reviewer, default_reviewers


SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


class ReviewCouncil:
    def __init__(
        self,
        config: CouncilConfig | None = None,
        reviewers: tuple[Reviewer, ...] | None = None,
    ) -> None:
        self.config = config or CouncilConfig()
        candidates = reviewers or default_reviewers()
        by_name = {reviewer.name: reviewer for reviewer in candidates}
        if len(by_name) != len(candidates):
            raise ValidationError("reviewer names must be unique")
        missing = set(self.config.enabled_reviewers) - set(by_name)
        if missing:
            raise ValidationError(f"enabled reviewers are unavailable: {sorted(missing)}")
        self.reviewers = tuple(by_name[name] for name in self.config.enabled_reviewers)

    def review(self, snapshot: PullRequestSnapshot) -> ReviewReport:
        findings: list[Finding] = []
        outcomes: list[ReviewerOutcome] = []
        for reviewer in self.reviewers:
            try:
                result = reviewer.review(snapshot)
                if not isinstance(result, tuple) or not all(isinstance(item, Finding) for item in result):
                    raise TypeError("reviewer returned an invalid result")
                findings.extend(result)
                outcomes.append(ReviewerOutcome(reviewer.name, ReviewerStatus.SUCCESS, len(result)))
            except Exception as exc:  # Boundary: a reviewer failure must remain visible.
                error = f"{type(exc).__name__}: {exc}"[:500]
                outcomes.append(ReviewerOutcome(reviewer.name, ReviewerStatus.FAILED, 0, error))

        findings.sort(key=lambda item: (
            SEVERITY_ORDER[item.severity],
            item.reviewer,
            item.path or "",
            item.line or 0,
            item.rule_id,
        ))
        successful = sum(item.status is ReviewerStatus.SUCCESS for item in outcomes)
        failed = len(outcomes) - successful
        degraded = failed > 0
        if successful < self.config.minimum_successful_reviewers:
            decision = Decision.BLOCKED
        elif any(item.severity in self.config.blocking_severities for item in findings):
            decision = Decision.BLOCKED
        elif degraded:
            decision = Decision.DEGRADED
        elif any(item.severity in (Severity.HIGH, Severity.MEDIUM) for item in findings):
            decision = Decision.CHANGES_REQUESTED
        else:
            decision = Decision.APPROVED

        summary = severity_counts(findings)
        summary.update({
            "successful_reviewers": successful,
            "failed_reviewers": failed,
            "total_findings": len(findings),
        })
        report = ReviewReport(
            schema_version="1.0",
            tool_version=__version__,
            pr_id=snapshot.pr_id,
            commit_sha=snapshot.commit_sha,
            decision=decision,
            degraded=degraded,
            outcomes=tuple(outcomes),
            findings=tuple(findings),
            summary=summary,
            report_sha="",
        )
        return replace(report, report_sha=digest(report.unsigned_dict()))
