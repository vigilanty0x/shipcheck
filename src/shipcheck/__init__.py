"""Canonical Shipcheck API.

The legacy ``safe_merge_gate`` package remains supported for backwards
compatibility. New consumers should import from ``shipcheck``.

The absorbed evidence-first release engine is deliberately exposed as the
``shipcheck.release_gate`` namespace so its ``Decision``/policy types do not
silently replace the legacy merge-gate types at the package root.

Historical release-gate module imports such as ``shipcheck.engine`` and
``shipcheck.models`` are registered as compatibility aliases to the absorbed
namespace. The canonical root API itself stays bound to the merge-gate types.
"""

from importlib import import_module as _import_module
import sys as _sys

from safe_merge_gate import *  # noqa: F401,F403
from safe_merge_gate import __all__ as _legacy_all
from safe_merge_gate import __version__

from . import release_gate

_RELEASE_MODULE_ALIASES = (
    "adapters",
    "api",
    "artifacts",
    "canonical",
    "demo",
    "engine",
    "errors",
    "ledger",
    "limits",
    "models",
    "receipt",
    "redaction",
    "report",
    "risk",
    "secureio",
    "selftest",
    "trust",
)
for _name in _RELEASE_MODULE_ALIASES:
    _sys.modules.setdefault(
        f"{__name__}.{_name}",
        _import_module(f"{__name__}.release_gate.{_name}"),
    )

del _name, _import_module, _sys

__all__ = [*_legacy_all, "release_gate"]
