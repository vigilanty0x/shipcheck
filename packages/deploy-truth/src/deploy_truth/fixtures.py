"""Pure synthetic, account-free release fixtures."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .inventory import CaptureLimits, inventory_from_bytes
from .io import load_object
from .models import ContractError, LayerName, ReleaseSpec, TruthReport
from .verification import verify_inventories


@dataclass(frozen=True, slots=True)
class SyntheticFixture:
    spec: ReleaseSpec
    source: Mapping[str, bytes]
    bundle: Mapping[str, bytes]
    live: Mapping[str, bytes]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SyntheticFixture":
        if set(value) != {"schema_version", "spec", "layers"} or value["schema_version"] != "1.0":
            raise ContractError("fixture fields do not match schema 1.0")
        if not isinstance(value["spec"], dict) or not isinstance(value["layers"], dict):
            raise ContractError("fixture spec and layers must be objects")
        if set(value["layers"]) != {"source", "bundle", "live"}:
            raise ContractError("fixture requires source, bundle, and live layers")
        spec = ReleaseSpec.from_dict(value["spec"])

        def decode(layer: str) -> dict[str, bytes]:
            entries = value["layers"][layer]
            if not isinstance(entries, dict) or len(entries) > 2048:
                raise ContractError("fixture layer must be a bounded object")
            result: dict[str, bytes] = {}
            for path, encoded in entries.items():
                if not isinstance(encoded, str) or len(encoded) > 16 * 1024 * 1024:
                    raise ContractError("fixture content must be bounded base64 text")
                try:
                    result[path] = base64.b64decode(encoded, validate=True)
                except (ValueError, TypeError) as exc:
                    raise ContractError(f"fixture content for {path!r} is invalid base64") from exc
            return result

        return cls(spec, decode("source"), decode("bundle"), decode("live"))

    @classmethod
    def load(cls, path: Path) -> "SyntheticFixture":
        return cls.from_dict(load_object(path))

    def verify(self, limits: CaptureLimits = CaptureLimits()) -> TruthReport:
        return verify_inventories(
            self.spec,
            inventory_from_bytes(LayerName.SOURCE, self.source, self.spec, limits),
            inventory_from_bytes(LayerName.BUNDLE, self.bundle, self.spec, limits),
            inventory_from_bytes(LayerName.LIVE, self.live, self.spec, limits),
        )

