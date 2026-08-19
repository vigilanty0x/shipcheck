"""Canonical Shipcheck API.

The legacy ``safe_merge_gate`` package remains supported for backwards
compatibility. New consumers should import from ``shipcheck``.

The absorbed evidence-first release engine is deliberately exposed as the
``shipcheck.release_gate`` namespace so its ``Decision``/policy types do not
silently replace the legacy merge-gate types at the package root.
"""

from safe_merge_gate import *  # noqa: F401,F403
from safe_merge_gate import __all__ as _legacy_all
from safe_merge_gate import __version__

from . import release_gate

__all__ = [*_legacy_all, "release_gate"]
