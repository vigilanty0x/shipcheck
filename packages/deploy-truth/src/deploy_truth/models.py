"""Strict schema-1.0 contracts and canonical identities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "1.0"
MAX_COMPONENTS = 128
MAX_ARTIFACTS = 2048


class ContractError(ValueError):
    """Input or evidence does not satisfy the public schema."""


class Decision(StrEnum):
    VERIFIED = "verified"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class ComponentState(StrEnum):
    READY = "ready"
    DISABLED = "disabled"
    DEGRADED = "degraded"


class LayerName(StrEnum):
    SOURCE = "source"
    BUNDLE = "bundle"
    LIVE = "live"


class CaptureState(StrEnum):
    CAPTURED = "captured"
    BLOCKED = "blocked"


class DifferenceKind(StrEnum):
    MATCH = "match"
    BYTE_DRIFT = "byte_drift"
    MISSING_SOURCE = "missing_source"
    MISSING_BUNDLE = "missing_bundle"
    MISSING_LIVE = "missing_live"
    UNEXPECTED_SOURCE = "unexpected_source"
    UNEXPECTED_BUNDLE = "unexpected_bundle"
    UNEXPECTED_LIVE = "unexpected_live"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or "\\" in value:
        raise ContractError("artifact paths must be non-empty bounded POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ContractError(f"unsafe artifact path: {value!r}")
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class Component:
    name: str
    version: str
    dependencies: tuple[str, ...]
    state: ComponentState
    artifacts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 96:
            raise ContractError("component name must contain 1 to 96 characters")
        if not self.version or len(self.version) > 128:
            raise ContractError("component version must contain 1 to 128 characters")
        if len(self.dependencies) > 64 or any(not item or len(item) > 96 for item in self.dependencies):
            raise ContractError("component dependencies are invalid")
        normalized = tuple(validate_relative_path(path) for path in self.artifacts)
        if not normalized or len(normalized) > MAX_ARTIFACTS or len(set(normalized)) != len(normalized):
            raise ContractError("component artifacts must be a unique non-empty bounded list")
        object.__setattr__(self, "artifacts", normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "version": self.version, "dependencies": list(self.dependencies),
            "state": self.state.value, "artifacts": list(self.artifacts),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Component":
        if set(value) != {"name", "version", "dependencies", "state", "artifacts"}:
            raise ContractError("component fields do not match schema 1.0")
        try:
            return cls(
                value["name"], value["version"], tuple(value["dependencies"]),
                ComponentState(value["state"]), tuple(value["artifacts"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError(f"invalid component: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ReleaseSpec:
    schema_version: str
    release_version: str
    components: tuple[Component, ...]
    spec_sha256: str

    @classmethod
    def create(cls, release_version: str, components: Iterable[Component]) -> "ReleaseSpec":
        if not isinstance(release_version, str) or not release_version or len(release_version) > 128:
            raise ContractError("release_version must contain 1 to 128 characters")
        ordered = tuple(sorted(components, key=lambda item: item.name.casefold()))
        if not 1 <= len(ordered) <= MAX_COMPONENTS:
            raise ContractError(f"a release requires 1 to {MAX_COMPONENTS} components")
        names = [component.name for component in ordered]
        folded = [name.casefold() for name in names]
        if len(folded) != len(set(folded)):
            raise ContractError("component names must be unique")
        artifact_paths = [path for component in ordered for path in component.artifacts]
        if len(artifact_paths) > MAX_ARTIFACTS or len(artifact_paths) != len(set(artifact_paths)):
            raise ContractError("artifact paths must be globally unique and bounded")
        known = set(names)
        for component in ordered:
            if component.name in component.dependencies:
                raise ContractError("a component cannot depend on itself")
            unknown = set(component.dependencies) - known
            if unknown:
                raise ContractError(f"unknown dependencies for {component.name}: {sorted(unknown)}")
        _reject_dependency_cycles(ordered)
        identity = {
            "schema_version": SCHEMA_VERSION,
            "release_version": release_version,
            "components": [component.to_dict() for component in ordered],
        }
        return cls(SCHEMA_VERSION, release_version, ordered, sha256_json(identity))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "release_version": self.release_version,
            "components": [component.to_dict() for component in self.components],
            "spec_sha256": self.spec_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReleaseSpec":
        allowed = {"schema_version", "release_version", "components", "spec_sha256"}
        if set(value) not in ({"schema_version", "release_version", "components"}, allowed):
            raise ContractError("release spec fields do not match schema 1.0")
        if value["schema_version"] != SCHEMA_VERSION or not isinstance(value["components"], list):
            raise ContractError("unsupported release spec schema")
        spec = cls.create(value["release_version"], (Component.from_dict(item) for item in value["components"]))
        supplied = value.get("spec_sha256")
        if supplied is not None and supplied != spec.spec_sha256:
            raise ContractError("spec_sha256 does not match release content")
        return spec

    def artifact_components(self) -> dict[str, str]:
        return {path: component.name for component in self.components for path in component.artifacts}


def _reject_dependency_cycles(components: tuple[Component, ...]) -> None:
    graph = {component.name: component.dependencies for component in components}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            raise ContractError("component dependency graph contains a cycle")
        if name in visited:
            return
        visiting.add(name)
        for dependency in graph[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for name in graph:
        visit(name)


@dataclass(frozen=True, slots=True)
class Artifact:
    path: str
    component: str | None
    sha256: str
    size: int

    def __post_init__(self) -> None:
        validate_relative_path(self.path)
        if self.component is not None and (not self.component or len(self.component) > 96):
            raise ContractError("artifact component is invalid")
        if len(self.sha256) != 64 or any(character not in "0123456789abcdef" for character in self.sha256):
            raise ContractError("artifact sha256 is invalid")
        if not isinstance(self.size, int) or self.size < 0:
            raise ContractError("artifact size is invalid")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LayerInventory:
    layer: LayerName
    state: CaptureState
    artifacts: tuple[Artifact, ...]
    inventory_sha256: str
    error_code: str | None = None
    summary: str = "captured"

    @classmethod
    def captured(cls, layer: LayerName, artifacts: Iterable[Artifact]) -> "LayerInventory":
        ordered = tuple(sorted(artifacts, key=lambda item: item.path))
        if len(ordered) > MAX_ARTIFACTS or len({item.path for item in ordered}) != len(ordered):
            raise ContractError("layer artifacts are duplicated or exceed the limit")
        identity = {"layer": layer.value, "state": CaptureState.CAPTURED.value,
                    "artifacts": [item.to_dict() for item in ordered]}
        return cls(layer, CaptureState.CAPTURED, ordered, sha256_json(identity))

    @classmethod
    def blocked(cls, layer: LayerName, error_code: str, summary: str) -> "LayerInventory":
        if not error_code or len(error_code) > 64 or not summary or len(summary) > 512:
            raise ContractError("blocked layer explanation is invalid")
        identity = {"layer": layer.value, "state": CaptureState.BLOCKED.value,
                    "error_code": error_code, "summary": summary}
        return cls(layer, CaptureState.BLOCKED, (), sha256_json(identity), error_code, summary)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer.value, "state": self.state.value,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "inventory_sha256": self.inventory_sha256,
            "error_code": self.error_code, "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class Difference:
    path: str
    component: str | None
    kind: DifferenceKind
    source_sha256: str | None
    bundle_sha256: str | None
    live_sha256: str | None
    summary: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["kind"] = self.kind.value
        return result


@dataclass(frozen=True, slots=True)
class TruthReport:
    schema_version: str
    release_version: str
    spec_sha256: str
    source: LayerInventory
    bundle: LayerInventory
    live: LayerInventory
    differences: tuple[Difference, ...]
    component_versions: Mapping[str, Mapping[str, str]]
    decision: Decision
    decision_reasons: tuple[str, ...]
    evidence_sha256: str

    @classmethod
    def create(
        cls, spec: ReleaseSpec, source: LayerInventory, bundle: LayerInventory,
        live: LayerInventory, differences: Iterable[Difference],
    ) -> "TruthReport":
        if (source.layer, bundle.layer, live.layer) != (LayerName.SOURCE, LayerName.BUNDLE, LayerName.LIVE):
            raise ContractError("truth report layers are out of order")
        ordered = tuple(sorted(differences, key=lambda item: (item.path, item.kind.value)))
        reasons: list[str] = []
        blocked_layers = [item.layer.value for item in (source, bundle, live) if item.state is CaptureState.BLOCKED]
        kinds = {item.kind for item in ordered}
        component_not_ready = [component.name for component in spec.components if component.state is not ComponentState.READY]
        blocking_kinds = {
            DifferenceKind.MISSING_SOURCE, DifferenceKind.MISSING_BUNDLE, DifferenceKind.MISSING_LIVE,
            DifferenceKind.UNEXPECTED_SOURCE,
        }
        if blocked_layers:
            reasons.append("layer capture blocked: " + ", ".join(blocked_layers))
        if kinds & blocking_kinds:
            reasons.append("required artifact inventory is incomplete or the source baseline is invalid")
        if blocked_layers or kinds & blocking_kinds:
            decision = Decision.BLOCKED
        elif kinds - {DifferenceKind.MATCH} or component_not_ready:
            decision = Decision.DEGRADED
            if kinds - {DifferenceKind.MATCH}:
                reasons.append("bundle/live bytes or inventories drift from source")
            if component_not_ready:
                reasons.append("components not ready: " + ", ".join(component_not_ready))
        else:
            decision = Decision.VERIFIED
            reasons.append("source, bundle, and live contain the exact expected artifacts and bytes")
        versions = {
            component.name: {
                "version": component.version,
                "state": component.state.value,
                "dependencies": ",".join(component.dependencies),
            }
            for component in spec.components
        }
        identity = {
            "schema_version": SCHEMA_VERSION, "release_version": spec.release_version,
            "spec_sha256": spec.spec_sha256, "source": source.to_dict(), "bundle": bundle.to_dict(),
            "live": live.to_dict(), "differences": [item.to_dict() for item in ordered],
            "component_versions": versions, "decision": decision.value, "decision_reasons": reasons,
        }
        return cls(
            SCHEMA_VERSION, spec.release_version, spec.spec_sha256, source, bundle, live, ordered,
            versions, decision, tuple(reasons), sha256_json(identity),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "release_version": self.release_version,
            "spec_sha256": self.spec_sha256, "source": self.source.to_dict(),
            "bundle": self.bundle.to_dict(), "live": self.live.to_dict(),
            "differences": [item.to_dict() for item in self.differences],
            "component_versions": dict(self.component_versions), "decision": self.decision.value,
            "decision_reasons": list(self.decision_reasons), "evidence_sha256": self.evidence_sha256,
        }

