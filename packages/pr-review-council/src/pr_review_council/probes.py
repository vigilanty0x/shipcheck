"""Separated liveness, readiness, and functional proof probes."""

from __future__ import annotations

from typing import Any

from . import __version__
from .config import CouncilConfig
from .council import ReviewCouncil
from .models import Decision, PullRequestSnapshot
from .reviewers import default_reviewers


def inventory() -> dict[str, Any]:
    reviewers = default_reviewers()
    return {
        "tool": "pr-review-council",
        "version": __version__,
        "runtime_dependencies": [],
        "reviewers": [reviewer.name for reviewer in reviewers],
        "states": ["planned", "applied", "verified", "rolled_back", "degraded", "blocked"],
        "schema_versions": {"input": "1.0", "report": "1.0", "receipt": "1.0"},
    }


def liveness_probe() -> dict[str, Any]:
    return {"probe": "liveness", "status": "alive", "version": __version__}


def readiness_probe(config: CouncilConfig | None = None) -> dict[str, Any]:
    chosen = config or CouncilConfig()
    council = ReviewCouncil(chosen)
    ready = len(council.reviewers) >= chosen.minimum_successful_reviewers
    return {
        "probe": "readiness",
        "status": "ready" if ready else "blocked",
        "reviewers": [reviewer.name for reviewer in council.reviewers],
        "minimum_successful_reviewers": chosen.minimum_successful_reviewers,
    }


def functional_probe() -> dict[str, Any]:
    snapshot = PullRequestSnapshot.from_dict({
        "pr_id": "functional-proof",
        "commit_sha": "a" * 40,
        "title": "Synthetic counter-proof",
        "body": "The bundled secret fixture must make the gate fall.",
        "files": [{
            "path": "src/example.py",
            "patch": "@@ -0,0 +1 @@\n+api_key = 'synthetic-secret-value'\n",
            "additions": 1,
            "deletions": 0,
        }],
    })
    report = ReviewCouncil().review(snapshot)
    proven = report.decision is Decision.BLOCKED and report.summary["critical"] >= 1
    return {
        "probe": "functional",
        "status": "proven" if proven else "blocked",
        "expected_decision": Decision.BLOCKED.value,
        "observed_decision": report.decision.value,
        "report_sha": report.report_sha,
        "counter_proof_triggered": proven,
    }
