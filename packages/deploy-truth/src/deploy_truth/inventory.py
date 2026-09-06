"""Bounded local and synthetic artifact inventory capture."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Mapping

from .models import Artifact, LayerInventory, LayerName, ReleaseSpec, validate_relative_path


@dataclass(frozen=True, slots=True)
class CaptureLimits:
    max_files: int = 2048
    max_file_bytes: int = 64 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024

    def __post_init__(self) -> None:
        if not 1 <= self.max_files <= 10000:
            raise ValueError("max_files must be between 1 and 10000")
        if not 1 <= self.max_file_bytes <= 1024 * 1024 * 1024:
            raise ValueError("max_file_bytes is out of bounds")
        if not self.max_file_bytes <= self.max_total_bytes <= 4 * 1024 * 1024 * 1024:
            raise ValueError("max_total_bytes is out of bounds")


def hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def inventory_from_bytes(
    layer: LayerName, files: Mapping[str, bytes], spec: ReleaseSpec,
    limits: CaptureLimits = CaptureLimits(),
) -> LayerInventory:
    if len(files) > limits.max_files:
        return LayerInventory.blocked(layer, "file_limit", "artifact count exceeds the configured limit")
    components = spec.artifact_components()
    artifacts: list[Artifact] = []
    total = 0
    try:
        for raw_path, content in files.items():
            path = validate_relative_path(raw_path)
            if not isinstance(content, bytes):
                return LayerInventory.blocked(layer, "invalid_bytes", f"artifact {path} is not bytes")
            if len(content) > limits.max_file_bytes:
                return LayerInventory.blocked(layer, "file_size_limit", f"artifact {path} exceeds the file limit")
            total += len(content)
            if total > limits.max_total_bytes:
                return LayerInventory.blocked(layer, "total_size_limit", "artifact bytes exceed the total limit")
            artifacts.append(Artifact(path, components.get(path), hash_bytes(content), len(content)))
    except Exception as exc:
        return LayerInventory.blocked(layer, "invalid_inventory", f"inventory rejected: {type(exc).__name__}")
    return LayerInventory.captured(layer, artifacts)


def capture_directory(
    layer: LayerName, root: Path, spec: ReleaseSpec,
    limits: CaptureLimits = CaptureLimits(),
) -> LayerInventory:
    if not root.exists():
        return LayerInventory.blocked(layer, "root_missing", "layer root does not exist")
    if root.is_symlink():
        return LayerInventory.blocked(layer, "root_symlink", "layer root must not be a symlink")
    if not root.is_dir():
        return LayerInventory.blocked(layer, "root_not_directory", "layer root is not a directory")
    components = spec.artifact_components()
    artifacts: list[Artifact] = []
    total = 0
    try:
        for directory, directory_names, file_names in os.walk(root, followlinks=False):
            directory_names.sort()
            file_names.sort()
            current = Path(directory)
            for name in tuple(directory_names):
                if (current / name).is_symlink():
                    return LayerInventory.blocked(layer, "symlink_forbidden", "symlinked directories are not captured")
            for name in file_names:
                path = current / name
                if path.is_symlink():
                    return LayerInventory.blocked(layer, "symlink_forbidden", "symlinked files are not captured")
                relative = path.relative_to(root).as_posix()
                size = path.stat().st_size
                if size > limits.max_file_bytes:
                    return LayerInventory.blocked(layer, "file_size_limit", f"artifact {relative} exceeds the file limit")
                total += size
                if len(artifacts) + 1 > limits.max_files or total > limits.max_total_bytes:
                    return LayerInventory.blocked(layer, "inventory_limit", "layer exceeds configured capture limits")
                digest = hashlib.sha256()
                with path.open("rb") as handle:
                    while chunk := handle.read(1024 * 1024):
                        digest.update(chunk)
                artifacts.append(Artifact(relative, components.get(relative), digest.hexdigest(), size))
    except (OSError, ValueError) as exc:
        return LayerInventory.blocked(layer, "capture_error", f"layer capture failed: {type(exc).__name__}")
    return LayerInventory.captured(layer, artifacts)

