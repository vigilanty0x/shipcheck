from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

PROJECT = "reproducible-demo-harness"
REQUIRED_FIELDS = ("artifact_path", "expected_sha256")
MAX_INPUT_BYTES = 8_192
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def verify_demo(record: dict[str, Any], *, allowed_root: Path) -> dict[str, Any]:
    if set(record) != set(REQUIRED_FIELDS):
        raise ValueError("record accepts only artifact_path and expected_sha256")
    relative = record.get("artifact_path")
    expected = record.get("expected_sha256")
    if not isinstance(relative, str) or not 1 <= len(relative) <= 500 or Path(relative).is_absolute() or any(ord(c) < 32 for c in relative):
        raise ValueError("artifact_path must be a bounded relative path")
    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
        raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
    root = allowed_root.resolve(strict=True)
    joined = root / relative
    if joined.is_symlink():
        raise ValueError("artifact must be a regular non-symlink file beneath allowed_root")
    candidate = joined.resolve(strict=True)
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError("artifact must be a regular non-symlink file beneath allowed_root")
    size = candidate.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise ValueError("artifact exceeds 16777216 bytes")
    digest = sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise ValueError("artifact digest differs from the separately trusted expected digest")
    return {"artifact_path": candidate.relative_to(root).as_posix(), "matched": True, "sha256": actual, "bytes": size, "executed": False}


def evaluate(record: Any, *, allowed_root: str | Path | None = None) -> dict[str, Any]:
    artifact: Any = None
    safe_record = None
    try:
        if not isinstance(record, dict):
            raise ValueError("record must be a JSON object")
        if len(_canonical(record).encode()) > MAX_INPUT_BYTES:
            raise ValueError("record exceeds 8192 bytes")
        safe_record = record
        missing = [field for field in REQUIRED_FIELDS if field not in record]
        if missing:
            status, reason = "blocked", "missing required fields: " + ", ".join(missing)
        else:
            artifact = verify_demo(record, allowed_root=Path.cwd() if allowed_root is None else Path(allowed_root))
            status, reason = "passed", "local artifact bytes matched the separately trusted expected digest; no command was executed"
    except (TypeError, ValueError, KeyError, OSError, OverflowError) as exc:
        status, reason = "failed", str(exc)
    receipt = {"project": PROJECT, "status": status, "reason": reason, "record": safe_record, "verification": artifact}
    receipt["evidence_sha256"] = sha256(_canonical(receipt).encode()).hexdigest()
    return receipt
