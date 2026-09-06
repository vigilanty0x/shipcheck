"""Public Python API."""

from __future__ import annotations

from pathlib import Path

from .inventory import CaptureLimits, capture_directory
from .models import LayerInventory, LayerName, ReleaseSpec, TruthReport
from .verification import verify_inventories as _verify


def verify_inventories(
    spec: ReleaseSpec, source: LayerInventory, bundle: LayerInventory, live: LayerInventory,
) -> TruthReport:
    return _verify(spec, source, bundle, live)


def capture_and_verify(
    spec: ReleaseSpec, source_root: Path, bundle_root: Path, live_root: Path,
    *, limits: CaptureLimits = CaptureLimits(),
) -> TruthReport:
    source = capture_directory(LayerName.SOURCE, source_root, spec, limits)
    bundle = capture_directory(LayerName.BUNDLE, bundle_root, spec, limits)
    live = capture_directory(LayerName.LIVE, live_root, spec, limits)
    return _verify(spec, source, bundle, live)

