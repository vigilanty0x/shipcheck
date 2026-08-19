"""Canonical Shipcheck CLI dispatcher.

Both historical command families remain addressable during consolidation:

* merge-snapshot commands from ``safe_merge_gate``;
* evidence-first release commands from ``shipcheck.release_gate``.

The command sets do not overlap today, so existing direct invocations remain
compatible. Explicit ``merge-gate`` and ``release-gate`` prefixes are also
accepted for scripts that want an unambiguous long-term boundary.
"""

from __future__ import annotations

import sys

from safe_merge_gate.cli import main as _merge_main
from .release_gate.cli import main as _release_main

_RELEASE_COMMANDS = frozenset(
    {
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
    }
)
_MERGE_COMMANDS = frozenset({"inventory", "evaluate", "dry-run", "apply", "verify", "rollback", "probe"})


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "release-gate":
        return _release_main(args[1:])
    if args and args[0] == "merge-gate":
        return _merge_main(args[1:])
    if args and args[0] in _RELEASE_COMMANDS:
        return _release_main(args)
    return _merge_main(args)


__all__ = ["main"]
