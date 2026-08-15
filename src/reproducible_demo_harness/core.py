from __future__ import annotations
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any

PROJECT = "reproducible-demo-harness"
REQUIRED_FIELDS = ["command","expected_sha256","actual_sha256"]

def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())

def _string_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_text(item) for item in value)

def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)

def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)

def verify_demo(record: dict[str, Any]) -> dict[str, Any]:
    if not _text(record["command"]):
        raise ValueError("command is required")
    digest = re.compile(r"[0-9a-f]{64}")
    if not all(isinstance(record[key], str) and digest.fullmatch(record[key]) for key in ("expected_sha256", "actual_sha256")):
        raise ValueError("digests must be lowercase SHA-256")
    if record["expected_sha256"] != record["actual_sha256"]:
        raise ValueError("demo output differs from release evidence")
    return {"command": record["command"], "matched": True, "sha256": record["actual_sha256"]}

def evaluate(record: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    artifact: Any = None
    if missing:
        status = "blocked"
        reason = "missing required fields: " + ", ".join(missing)
    else:
        try:
            artifact = verify_demo(record)
            status = "passed"
            reason = "verify_demo completed"
        except (TypeError, ValueError, KeyError) as exc:
            status = "failed"
            reason = str(exc)
    receipt = {"project": PROJECT, "status": status, "reason": reason, "record": record, "verification": artifact}
    receipt["evidence_sha256"] = sha256(_canonical(receipt).encode()).hexdigest()
    return receipt

