from safe_merge_gate.contract import Change, CheckState, GatePolicy, MergeSnapshot, SecretFinding

BASE = "1" * 40
MERGE = "2" * 40
NOW = "2026-01-01T00:00:00Z"


def snapshot(**changes):
    values = dict(
        repository="synthetic/example", expected_sha=BASE, observed_sha=BASE,
        merge_sha=MERGE, captured_at=NOW,
        ci={"build": CheckState.SUCCESS, "test": CheckState.SUCCESS, "style": CheckState.SUCCESS},
        required_ci=("build", "test"), optional_ci=("style",),
        tests_complete=True, tests_passed=True, secret_scan_complete=True,
        secret_findings=(), clean_tree=True,
        changes=(Change("src/example.py", 8, 2), Change("tests/test_example.py", 12, 0)),
    )
    values.update(changes)
    return MergeSnapshot(**values)


def policy(**changes):
    values = dict(max_changed_files=100, max_changed_lines=5000, max_binary_files=5)
    values.update(changes)
    return GatePolicy(**values)


def finding():
    return SecretFinding("a" * 40, "src/example.py", "synthetic-token")

