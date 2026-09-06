from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from deploy_truth.api import capture_and_verify
from deploy_truth.inventory import CaptureLimits, capture_directory, hash_bytes, inventory_from_bytes
from deploy_truth.models import (
    ComponentState, Decision, DifferenceKind, LayerName,
)
from deploy_truth.verification import verify_inventories

from helpers import spec, three_inventories, write_layer


class SyntheticInventoryTests(unittest.TestCase):
    def test_known_hash(self) -> None:
        self.assertEqual(hash_bytes(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_component_assigned(self) -> None:
        release = spec()
        inventory = inventory_from_bytes(LayerName.SOURCE, {"bin/app": b"x"}, release)
        self.assertEqual(inventory.artifacts[0].component, "core")

    def test_unexpected_artifact_unassigned(self) -> None:
        release = spec()
        inventory = inventory_from_bytes(LayerName.SOURCE, {"extra": b"x"}, release)
        self.assertIsNone(inventory.artifacts[0].component)

    def test_file_count_limit_blocks(self) -> None:
        release = spec()
        inventory = inventory_from_bytes(
            LayerName.SOURCE, {"a": b"1", "b": b"2"}, release, CaptureLimits(max_files=1)
        )
        self.assertEqual(inventory.state.value, "blocked")

    def test_file_size_limit_blocks(self) -> None:
        release = spec()
        inventory = inventory_from_bytes(
            LayerName.SOURCE, {"bin/app": b"12"}, release,
            CaptureLimits(max_file_bytes=1, max_total_bytes=1),
        )
        self.assertEqual(inventory.error_code, "file_size_limit")

    def test_non_bytes_blocks(self) -> None:
        release = spec()
        inventory = inventory_from_bytes(LayerName.SOURCE, {"bin/app": "text"}, release)  # type: ignore[dict-item]
        self.assertEqual(inventory.error_code, "invalid_bytes")


class DirectoryCaptureTests(unittest.TestCase):
    def test_missing_root_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inventory = capture_directory(LayerName.LIVE, Path(directory) / "missing", spec())
            self.assertEqual(inventory.error_code, "root_missing")

    def test_file_root_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "file"
            path.write_bytes(b"x")
            self.assertEqual(capture_directory(LayerName.LIVE, path, spec()).error_code, "root_not_directory")

    def test_symlink_file_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            root.mkdir()
            target = Path(directory) / "target"
            target.write_bytes(b"x")
            (root / "link").symlink_to(target)
            self.assertEqual(capture_directory(LayerName.LIVE, root, spec()).error_code, "symlink_forbidden")

    def test_real_capture_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            write_layer(root, {"bin/app": b"v1", "config/app.json": b"{}\n"})
            first = capture_directory(LayerName.SOURCE, root, spec())
            second = capture_directory(LayerName.SOURCE, root, spec())
            self.assertEqual(first.inventory_sha256, second.inventory_sha256)


class VerificationTests(unittest.TestCase):
    def test_exact_release_verified(self) -> None:
        release, source, bundle, live = three_inventories()
        report = verify_inventories(release, source, bundle, live)
        self.assertEqual(report.decision, Decision.VERIFIED)
        self.assertTrue(all(item.kind is DifferenceKind.MATCH for item in report.differences))

    def test_live_byte_drift_degraded(self) -> None:
        release, source, bundle, _ = three_inventories()
        live = inventory_from_bytes(
            LayerName.LIVE, {"bin/app": b"tampered", "config/app.json": b"{}\n"}, release
        )
        report = verify_inventories(release, source, bundle, live)
        self.assertEqual(report.decision, Decision.DEGRADED)
        self.assertIn(DifferenceKind.BYTE_DRIFT, {item.kind for item in report.differences})

    def test_bundle_byte_drift_degraded(self) -> None:
        release, source, _, live = three_inventories()
        bundle = inventory_from_bytes(
            LayerName.BUNDLE, {"bin/app": b"tampered", "config/app.json": b"{}\n"}, release
        )
        self.assertEqual(verify_inventories(release, source, bundle, live).decision, Decision.DEGRADED)

    def test_missing_live_blocks(self) -> None:
        release, source, bundle, _ = three_inventories()
        live = inventory_from_bytes(LayerName.LIVE, {"bin/app": b"v1"}, release)
        report = verify_inventories(release, source, bundle, live)
        self.assertEqual(report.decision, Decision.BLOCKED)
        self.assertIn(DifferenceKind.MISSING_LIVE, {item.kind for item in report.differences})

    def test_missing_bundle_blocks(self) -> None:
        release, source, _, live = three_inventories()
        bundle = inventory_from_bytes(LayerName.BUNDLE, {"bin/app": b"v1"}, release)
        self.assertEqual(verify_inventories(release, source, bundle, live).decision, Decision.BLOCKED)

    def test_missing_source_blocks(self) -> None:
        release, _, bundle, live = three_inventories()
        source = inventory_from_bytes(LayerName.SOURCE, {"bin/app": b"v1"}, release)
        self.assertEqual(verify_inventories(release, source, bundle, live).decision, Decision.BLOCKED)

    def test_unexpected_source_blocks(self) -> None:
        release, _, bundle, live = three_inventories()
        source = inventory_from_bytes(
            LayerName.SOURCE, {"bin/app": b"v1", "config/app.json": b"{}\n", "extra": b"x"}, release
        )
        self.assertEqual(verify_inventories(release, source, bundle, live).decision, Decision.BLOCKED)

    def test_unexpected_live_degrades(self) -> None:
        release, source, bundle, _ = three_inventories()
        live = inventory_from_bytes(
            LayerName.LIVE, {"bin/app": b"v1", "config/app.json": b"{}\n", "extra": b"x"}, release
        )
        report = verify_inventories(release, source, bundle, live)
        self.assertEqual(report.decision, Decision.DEGRADED)
        self.assertIn(DifferenceKind.UNEXPECTED_LIVE, {item.kind for item in report.differences})

    def test_blocked_capture_blocks_report(self) -> None:
        release, source, bundle, _ = three_inventories()
        live = capture_directory(LayerName.LIVE, Path("/definitely/not/present"), release)
        self.assertEqual(verify_inventories(release, source, bundle, live).decision, Decision.BLOCKED)

    def test_degraded_component_never_verifies(self) -> None:
        release = spec(ComponentState.DEGRADED)
        files = {"bin/app": b"v1", "config/app.json": b"{}\n"}
        inventories = [inventory_from_bytes(layer, files, release) for layer in LayerName]
        self.assertEqual(verify_inventories(release, *inventories).decision, Decision.DEGRADED)

    def test_report_evidence_is_reproducible(self) -> None:
        release, source, bundle, live = three_inventories()
        self.assertEqual(
            verify_inventories(release, source, bundle, live).evidence_sha256,
            verify_inventories(release, source, bundle, live).evidence_sha256,
        )

    def test_api_capture_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            roots = [Path(directory) / name for name in ("source", "bundle", "live")]
            for root in roots:
                write_layer(root, {"bin/app": b"v1", "config/app.json": b"{}\n"})
            self.assertEqual(capture_and_verify(spec(), *roots).decision, Decision.VERIFIED)


if __name__ == "__main__":
    unittest.main()

