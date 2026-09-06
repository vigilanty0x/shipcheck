"""Liveness, readiness, and functional truth counter-probes."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from .fixtures import SyntheticFixture
from .models import Decision, ReleaseSpec


@dataclass(frozen=True, slots=True)
class ProbeResult:
    mode: str
    healthy: bool
    checks: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": "1.0", "mode": self.mode, "healthy": self.healthy, "checks": list(self.checks)}


def liveness_probe() -> ProbeResult:
    return ProbeResult("liveness", True, ({"name": "process", "passed": True},))


def readiness_probe() -> ProbeResult:
    try:
        ReleaseSpec.from_dict({
            "schema_version": "1.0", "release_version": "synthetic-1",
            "components": [{
                "name": "app", "version": "1.0", "dependencies": [], "state": "ready",
                "artifacts": ["app.bin"],
            }],
        })
        passed, detail = True, "schema and hashing contracts initialized"
    except Exception as exc:
        passed, detail = False, f"contract initialization failed: {type(exc).__name__}"
    return ProbeResult("readiness", passed, ({"name": "contracts", "passed": passed, "detail": detail},))


def _fixture(live_content: bytes | None) -> SyntheticFixture:
    encoded = base64.b64encode(b"release-bytes-v1").decode("ascii")
    live: dict[str, str] = {}
    if live_content is not None:
        live["app.bin"] = base64.b64encode(live_content).decode("ascii")
    return SyntheticFixture.from_dict({
        "schema_version": "1.0",
        "spec": {
            "schema_version": "1.0", "release_version": "synthetic-1",
            "components": [{
                "name": "app", "version": "1.0", "dependencies": [], "state": "ready",
                "artifacts": ["app.bin"],
            }],
        },
        "layers": {
            "source": {"app.bin": encoded}, "bundle": {"app.bin": encoded},
            "live": live,
        },
    })


def functional_probe() -> ProbeResult:
    control = _fixture(b"release-bytes-v1").verify()
    drift = _fixture(b"tampered-live-bytes").verify()
    partial = _fixture(None).verify()
    replay = _fixture(b"release-bytes-v1").verify()
    checks = (
        {"name": "exact_control_verified", "passed": control.decision is Decision.VERIFIED},
        {"name": "byte_drift_not_success", "passed": drift.decision is Decision.DEGRADED},
        {"name": "partial_release_blocked", "passed": partial.decision is Decision.BLOCKED},
        {"name": "evidence_replay_stable", "passed": control.evidence_sha256 == replay.evidence_sha256},
    )
    return ProbeResult("functional", all(check["passed"] for check in checks), checks)

