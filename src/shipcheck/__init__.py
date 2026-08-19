"""Canonical Shipcheck API.

The legacy ``safe_merge_gate`` package remains supported for backwards
compatibility. New consumers should import from ``shipcheck``.
"""

from safe_merge_gate import *  # noqa: F401,F403
from safe_merge_gate import __all__ as _legacy_all
from safe_merge_gate import __version__

__all__ = list(_legacy_all)
