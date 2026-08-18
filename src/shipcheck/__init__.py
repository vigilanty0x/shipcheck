"""Canonical Shipcheck public API.

The release-readiness engine owns the canonical ``shipcheck`` import surface.
The deterministic merge gate remains available at ``safe_merge_gate`` and
``shipcheck.merge_gate`` during the compatibility window.
"""

from . import merge_gate, release_gate
from .release_gate import (
    Decision,
    DecisionEngine,
    DecisionLedger,
    GateResult,
    ReleaseEvidence,
    ReleasePolicy,
    Waiver,
    explain_receipt,
    export_receipt,
    evaluate_release,
    normalize_bundle,
    normalize_cyclonedx,
    normalize_junit,
    normalize_sarif,
    verify_receipt,
)

__all__ = [
    "Decision",
    "DecisionEngine",
    "DecisionLedger",
    "GateResult",
    "ReleaseEvidence",
    "ReleasePolicy",
    "Waiver",
    "explain_receipt",
    "export_receipt",
    "evaluate_release",
    "merge_gate",
    "normalize_bundle",
    "normalize_cyclonedx",
    "normalize_junit",
    "normalize_sarif",
    "release_gate",
    "verify_receipt",
]
__version__ = release_gate.__version__
