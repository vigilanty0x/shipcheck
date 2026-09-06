from __future__ import annotations

import unittest

from deploy_truth.models import (
    Artifact, Component, ComponentState, ContractError, Decision, LayerInventory, LayerName,
    ReleaseSpec, canonical_json, sha256_json, validate_relative_path,
)


class PathTests(unittest.TestCase):
    def test_normal_path(self) -> None:
        self.assertEqual(validate_relative_path("web/app.bin"), "web/app.bin")

    def test_absolute_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_relative_path("/etc/passwd")

    def test_parent_traversal_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_relative_path("../secret")

    def test_backslash_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_relative_path("web\\app")

    def test_empty_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_relative_path("")


class ComponentTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        component = Component("api", "1.2", ("db",), ComponentState.READY, ("api.bin",))
        self.assertEqual(Component.from_dict(component.to_dict()), component)

    def test_empty_artifacts_rejected(self) -> None:
        with self.assertRaises(ContractError):
            Component("api", "1", (), ComponentState.READY, ())

    def test_duplicate_artifacts_rejected(self) -> None:
        with self.assertRaises(ContractError):
            Component("api", "1", (), ComponentState.READY, ("app", "app"))

    def test_unknown_field_rejected(self) -> None:
        value = Component("api", "1", (), ComponentState.READY, ("app",)).to_dict()
        value["extra"] = True
        with self.assertRaises(ContractError):
            Component.from_dict(value)


class ReleaseSpecTests(unittest.TestCase):
    def test_canonical_component_order(self) -> None:
        a = Component("a", "1", (), ComponentState.READY, ("a",))
        b = Component("b", "1", ("a",), ComponentState.READY, ("b",))
        first = ReleaseSpec.create("1", [b, a])
        second = ReleaseSpec.create("1", [a, b])
        self.assertEqual(first.spec_sha256, second.spec_sha256)
        self.assertEqual([item.name for item in first.components], ["a", "b"])

    def test_unknown_dependency_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "unknown dependencies"):
            ReleaseSpec.create("1", [Component("a", "1", ("missing",), ComponentState.READY, ("a",))])

    def test_self_dependency_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "itself"):
            ReleaseSpec.create("1", [Component("a", "1", ("a",), ComponentState.READY, ("a",))])

    def test_cycle_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "cycle"):
            ReleaseSpec.create("1", [
                Component("a", "1", ("b",), ComponentState.READY, ("a",)),
                Component("b", "1", ("a",), ComponentState.READY, ("b",)),
            ])

    def test_global_duplicate_artifact_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "globally unique"):
            ReleaseSpec.create("1", [
                Component("a", "1", (), ComponentState.READY, ("same",)),
                Component("b", "1", (), ComponentState.READY, ("same",)),
            ])

    def test_case_insensitive_duplicate_component_rejected(self) -> None:
        with self.assertRaises(ContractError):
            ReleaseSpec.create("1", [
                Component("API", "1", (), ComponentState.READY, ("a",)),
                Component("api", "1", (), ComponentState.READY, ("b",)),
            ])

    def test_round_trip_with_hash(self) -> None:
        original = ReleaseSpec.create("1", [Component("a", "1", (), ComponentState.READY, ("a",))])
        self.assertEqual(ReleaseSpec.from_dict(original.to_dict()), original)

    def test_tampered_spec_hash_rejected(self) -> None:
        original = ReleaseSpec.create("1", [Component("a", "1", (), ComponentState.READY, ("a",))]).to_dict()
        original["spec_sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "spec_sha256"):
            ReleaseSpec.from_dict(original)

    def test_artifact_component_mapping(self) -> None:
        release = ReleaseSpec.create("1", [Component("a", "1", (), ComponentState.READY, ("path",))])
        self.assertEqual(release.artifact_components(), {"path": "a"})


class InventoryModelTests(unittest.TestCase):
    def test_artifact_invalid_hash_rejected(self) -> None:
        with self.assertRaises(ContractError):
            Artifact("app", "a", "bad", 1)

    def test_captured_order_and_hash_stable(self) -> None:
        a = Artifact("a", "core", "1" * 64, 1)
        b = Artifact("b", "core", "2" * 64, 2)
        first = LayerInventory.captured(LayerName.SOURCE, [b, a])
        second = LayerInventory.captured(LayerName.SOURCE, [a, b])
        self.assertEqual(first.inventory_sha256, second.inventory_sha256)
        self.assertEqual([item.path for item in first.artifacts], ["a", "b"])

    def test_blocked_inventory_has_visible_error(self) -> None:
        blocked = LayerInventory.blocked(LayerName.LIVE, "permission", "cannot read")
        self.assertEqual(blocked.state.value, "blocked")
        self.assertEqual(blocked.error_code, "permission")

    def test_canonical_json(self) -> None:
        self.assertEqual(canonical_json({"z": 1, "a": 2}), '{"a":2,"z":1}')
        self.assertEqual(sha256_json({"a": 1}), sha256_json({"a": 1}))


if __name__ == "__main__":
    unittest.main()

