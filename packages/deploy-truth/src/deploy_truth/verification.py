"""Visible source/bundle/live comparison and fail-closed release decisions."""

from __future__ import annotations

from .models import (
    Artifact, Difference, DifferenceKind, LayerInventory, ReleaseSpec, TruthReport,
)


def _index(inventory: LayerInventory) -> dict[str, Artifact]:
    return {artifact.path: artifact for artifact in inventory.artifacts}


def verify_inventories(
    spec: ReleaseSpec, source: LayerInventory, bundle: LayerInventory, live: LayerInventory,
) -> TruthReport:
    source_index, bundle_index, live_index = _index(source), _index(bundle), _index(live)
    expected = spec.artifact_components()
    differences: list[Difference] = []
    for path, component in sorted(expected.items()):
        source_artifact = source_index.get(path)
        bundle_artifact = bundle_index.get(path)
        live_artifact = live_index.get(path)
        hashes = (
            source_artifact.sha256 if source_artifact else None,
            bundle_artifact.sha256 if bundle_artifact else None,
            live_artifact.sha256 if live_artifact else None,
        )
        if source_artifact is None:
            kind, summary = DifferenceKind.MISSING_SOURCE, "required artifact is absent from source"
        elif bundle_artifact is None:
            kind, summary = DifferenceKind.MISSING_BUNDLE, "required artifact is absent from bundle"
        elif live_artifact is None:
            kind, summary = DifferenceKind.MISSING_LIVE, "required artifact is absent from live"
        elif len(set(hashes)) != 1 or len({source_artifact.size, bundle_artifact.size, live_artifact.size}) != 1:
            kind, summary = DifferenceKind.BYTE_DRIFT, "source, bundle, and live bytes are not identical"
        else:
            kind, summary = DifferenceKind.MATCH, "source, bundle, and live bytes match"
        differences.append(Difference(path, component, kind, *hashes, summary))

    for layer_name, index, kind in (
        ("source", source_index, DifferenceKind.UNEXPECTED_SOURCE),
        ("bundle", bundle_index, DifferenceKind.UNEXPECTED_BUNDLE),
        ("live", live_index, DifferenceKind.UNEXPECTED_LIVE),
    ):
        for path in sorted(set(index) - set(expected)):
            artifact = index[path]
            hashes = {
                "source": (artifact.sha256, None, None),
                "bundle": (None, artifact.sha256, None),
                "live": (None, None, artifact.sha256),
            }[layer_name]
            differences.append(Difference(
                path, None, kind, *hashes, f"unexpected artifact exists only in {layer_name} inventory",
            ))
    return TruthReport.create(spec, source, bundle, live, differences)

