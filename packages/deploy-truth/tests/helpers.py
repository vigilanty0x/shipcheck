from __future__ import annotations

from pathlib import Path

from deploy_truth.inventory import inventory_from_bytes
from deploy_truth.models import Component, ComponentState, LayerName, ReleaseSpec


def spec(state: ComponentState = ComponentState.READY) -> ReleaseSpec:
    return ReleaseSpec.create("1.0.0", [
        Component("core", "1.0.0", (), state, ("bin/app", "config/app.json")),
    ])


def three_inventories(content: bytes = b"v1"):
    release = spec()
    files = {"bin/app": content, "config/app.json": b"{}\n"}
    return (
        release,
        inventory_from_bytes(LayerName.SOURCE, files, release),
        inventory_from_bytes(LayerName.BUNDLE, files, release),
        inventory_from_bytes(LayerName.LIVE, files, release),
    )


def write_layer(root: Path, files: dict[str, bytes]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

