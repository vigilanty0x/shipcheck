"""Pure fail-closed gate evaluation."""

from __future__ import annotations

from .contract import (
    Check, CheckState, Decision, GateArtifact, GatePolicy, MergeSnapshot, utc_now,
)


def evaluate(
    snapshot: MergeSnapshot, policy: GatePolicy | None = None, *, generated_at: str | None = None,
) -> GateArtifact:
    selected = policy or GatePolicy()
    checks: list[Check] = []

    def add(name: str, passed: bool, required: bool, message: str, evidence: dict[str, object]) -> None:
        checks.append(Check(name, CheckState.SUCCESS if passed else CheckState.FAILURE, required, message, evidence))

    add(
        "sha-match", snapshot.expected_sha == snapshot.observed_sha, True,
        "Observed SHA matches the expected immutable base." if snapshot.expected_sha == snapshot.observed_sha else "Observed SHA differs from the expected immutable base.",
        {"expected_sha": snapshot.expected_sha, "observed_sha": snapshot.observed_sha},
    )
    for name in snapshot.required_ci:
        state = snapshot.ci.get(name, CheckState.MISSING)
        checks.append(Check(
            f"ci:{name}", state, True,
            "Required CI check succeeded." if state is CheckState.SUCCESS else f"Required CI check is {state.value}.",
            {"check": name, "observed_state": state.value},
        ))
    for name in snapshot.optional_ci:
        state = snapshot.ci.get(name, CheckState.MISSING)
        checks.append(Check(
            f"ci:{name}", state, False,
            "Optional CI check succeeded." if state is CheckState.SUCCESS else f"Optional CI check is {state.value}.",
            {"check": name, "observed_state": state.value},
        ))
    tests_ok = snapshot.tests_complete and snapshot.tests_passed
    add(
        "tests", tests_ok, selected.require_tests,
        "Required tests completed successfully." if tests_ok else "Tests are incomplete or failed.",
        {"complete": snapshot.tests_complete, "passed": snapshot.tests_passed},
    )
    secrets_ok = snapshot.secret_scan_complete and not snapshot.secret_findings
    add(
        "secrets", secrets_ok, selected.require_secret_scan,
        "Secret scan completed without findings." if secrets_ok else "Secret scan is incomplete or contains findings.",
        {"complete": snapshot.secret_scan_complete, "finding_count": len(snapshot.secret_findings)},
    )
    add(
        "clean-tree", snapshot.clean_tree, selected.require_clean_tree,
        "Working tree is clean." if snapshot.clean_tree else "Working tree contains uncommitted changes.",
        {"clean": snapshot.clean_tree},
    )
    inventory = snapshot.inventory
    add(
        "changed-files-limit", inventory["files"] <= selected.max_changed_files, True,
        "Changed file count is within policy." if inventory["files"] <= selected.max_changed_files else "Changed file count exceeds policy.",
        {"observed": inventory["files"], "maximum": selected.max_changed_files},
    )
    add(
        "changed-lines-limit", inventory["changed_lines"] <= selected.max_changed_lines, True,
        "Changed line count is within policy." if inventory["changed_lines"] <= selected.max_changed_lines else "Changed line count exceeds policy.",
        {"observed": inventory["changed_lines"], "maximum": selected.max_changed_lines},
    )
    add(
        "binary-files-limit", inventory["binary_files"] <= selected.max_binary_files, True,
        "Binary file count is within policy." if inventory["binary_files"] <= selected.max_binary_files else "Binary file count exceeds policy.",
        {"observed": inventory["binary_files"], "maximum": selected.max_binary_files},
    )

    required_failed = any(check.required and not check.success for check in checks)
    optional_failed = any(not check.required and not check.success for check in checks)
    decision = Decision.BLOCKED if required_failed else Decision.DEGRADED if optional_failed else Decision.READY
    outputs = {
        "check_count": len(checks),
        "required_failures": sum(check.required and not check.success for check in checks),
        "optional_failures": sum(not check.required and not check.success for check in checks),
    }
    return GateArtifact(decision, snapshot, selected, tuple(checks), generated_at or utc_now(), outputs)
