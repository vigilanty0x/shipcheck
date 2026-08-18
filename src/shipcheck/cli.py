"""Canonical Shipcheck CLI entrypoint.

This transition shim preserves the exact behavior of the legacy
``safe-merge-gate`` CLI while package/import consumers migrate to ``shipcheck``.
"""

from safe_merge_gate.cli import main

__all__ = ["main"]
