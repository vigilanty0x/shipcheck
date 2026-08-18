"""Canonical Shipcheck compatibility API.

The initial consolidation step intentionally re-exports the proven
``safe_merge_gate`` core. The richer release-gate engine is absorbed in a
separate migration step so identity changes cannot silently change behavior.
"""

from safe_merge_gate import *  # noqa: F401,F403
from safe_merge_gate import __all__, __version__
