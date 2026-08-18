"""Unified Shipcheck CLI dispatcher.

Release-readiness commands use the absorbed release-gate engine. Existing merge
gate commands retain their previous behavior through ``safe_merge_gate``.
"""

from __future__ import annotations

import sys

from safe_merge_gate.cli import main as merge_gate_main
from .release_gate.cli import main as release_gate_main

RELEASE_COMMANDS = frozenset({
    "capabilities",
    "selftest",
    "demo",
    "validate",
    "decide",
    "artifact",
    "normalize",
    "ledger",
    "promotion",
    "receipt",
    "serve",
})


def _help() -> None:
    print(
        "Shipcheck combines two offline evidence gates.\n\n"
        "Release readiness: capabilities, selftest, demo, validate, decide, "
        "artifact, normalize, ledger, promotion, receipt, serve.\n"
        "Merge compatibility: inventory, evaluate, dry-run, apply, verify, "
        "rollback, probe.\n\n"
        "Use `shipcheck <command> --help` for command-specific options. "
        "The legacy `safe-merge-gate` CLI remains available during migration."
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        _help()
        return 0
    if args[0] == "--version" or args[0] in RELEASE_COMMANDS:
        return release_gate_main(args)
    return merge_gate_main(args)


__all__ = ["main", "RELEASE_COMMANDS"]
