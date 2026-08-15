"""Public API for Safe Merge Gate."""

from .contract import (
    Change, Check, CheckState, ContractError, Decision, GateArtifact,
    GatePolicy, MergeSnapshot, SecretFinding,
)
from .gate import evaluate
from .transaction import (
    ApplyBlocked, LocalMergeTransaction, Receipt, TransactionConflict,
    TransactionVerificationError,
)

__all__ = [
    "ApplyBlocked", "Change", "Check", "CheckState", "ContractError", "Decision",
    "GateArtifact", "GatePolicy", "LocalMergeTransaction", "MergeSnapshot", "Receipt",
    "SecretFinding", "TransactionConflict", "TransactionVerificationError", "evaluate",
]

__version__ = "0.1.0"

