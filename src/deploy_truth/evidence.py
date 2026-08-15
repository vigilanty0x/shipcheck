"""Independent content-address verification for serialized truth reports."""

from __future__ import annotations

from typing import Any, Mapping

from .models import ContractError, Decision, sha256_json


REPORT_FIELDS = {
    "schema_version", "release_version", "spec_sha256", "source", "bundle", "live",
    "differences", "component_versions", "decision", "decision_reasons", "evidence_sha256",
}


def verify_evidence_document(value: Mapping[str, Any]) -> str:
    if set(value) != REPORT_FIELDS or value.get("schema_version") != "1.0":
        raise ContractError("truth report fields do not match schema 1.0")
    try:
        Decision(value["decision"])
    except (TypeError, ValueError) as exc:
        raise ContractError("truth report decision is invalid") from exc
    if not isinstance(value["differences"], list) or not isinstance(value["decision_reasons"], list):
        raise ContractError("truth report differences and reasons must be lists")
    for layer in ("source", "bundle", "live"):
        layer_value = value[layer]
        if not isinstance(layer_value, dict) or layer_value.get("layer") != layer:
            raise ContractError(f"truth report {layer} inventory is invalid")
        inventory_identity = (
            {"layer": layer, "state": "captured", "artifacts": layer_value.get("artifacts")}
            if layer_value.get("state") == "captured"
            else {
                "layer": layer, "state": "blocked", "error_code": layer_value.get("error_code"),
                "summary": layer_value.get("summary"),
            }
        )
        if layer_value.get("inventory_sha256") != sha256_json(inventory_identity):
            raise ContractError(f"truth report {layer} inventory hash does not match content")
    identity = {key: value[key] for key in REPORT_FIELDS - {"evidence_sha256"}}
    expected = sha256_json(identity)
    if value["evidence_sha256"] != expected:
        raise ContractError("evidence_sha256 does not match truth report content")
    return expected

