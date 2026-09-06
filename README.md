# Shipcheck

## Integrated evidence-to-rollback workflow (working-tree candidate)

```bash
shipcheck workflow request.json --root ./inputs --output ./new-run --trust-store ./reviewed-local-trust.json
```

This entry chains the two existing gate engines. It hashes the real artifact
files, binds the merge and release candidates and change inventories, computes
risk, normalizes real JUnit files and cross-checks their results, evaluates the
release and merge policies, then performs apply → verify → exact rollback on a
**new private copy** of the supplied state. It retains every stage and receipt.
The supplied state and artifacts are rechecked and never changed by the workflow.

It verifies supplied test reports; it does not execute repository commands or
claim the reports were produced during this run. It does not merge Git, deploy,
publish or modify a live application. LAB readiness remains `ready_lab` with
`production_ready=false`, even when its local rollback drill passes. A blocked
gate cannot reach the drill. Existing output directories are refused.

See [the workflow request and result contract](docs/INTEGRATED-WORKFLOW.md).
An optional [producer receipt bundle](docs/PRODUCER-RECEIPTS.md) cross-checks CC
receipts and their complete declared public artifact inventory. It can veto a
run; supplied hashes and candidate bindings never become authenticated evidence.
All historical commands below remain supported. This working-tree addition is
not a release or authorization to archive source repositories.

Shipcheck is a zero-runtime-dependency Python CLI and library for offline,
fail-closed release and merge readiness checks over immutable snapshots. It keeps
the original Safe Merge Gate engine and transaction model while making `shipcheck`
the canonical product identity.

## Compatibility

New consumers should use:

```bash
python -m shipcheck --help
shipcheck --help
```

Existing consumers remain supported during the migration window:

```bash
python -m safe_merge_gate --help
safe-merge-gate --help
```

The legacy `safe_merge_gate` Python package remains importable and is the current
implementation behind the canonical `shipcheck` compatibility layer. No existing
CLI command is removed by this migration.

`ready` is the only applicable decision. Required failures produce `blocked`.
Optional failures produce `degraded`, which is still not applicable.

The gate verifies:

- expected SHA equals observed SHA;
- every required CI check succeeded;
- tests completed and passed;
- secret scanning completed with no fingerprinted finding;
- the local tree is clean;
- changed file, changed line, and binary-file limits;
- a canonical, sorted and uniquely addressed change inventory.

## Offline walkthrough

```bash
PYTHONPATH=src python -m shipcheck inventory --snapshot examples/ready-snapshot.json
PYTHONPATH=src python -m shipcheck evaluate \
  --snapshot examples/ready-snapshot.json \
  --policy examples/policy.json \
  --evidence /tmp/shipcheck-evidence.json \
  --generated-at 2026-01-01T00:00:00Z
cp examples/local-state.json /tmp/shipcheck-state.json
PYTHONPATH=src python -m shipcheck dry-run \
  --evidence /tmp/shipcheck-evidence.json --state /tmp/shipcheck-state.json
PYTHONPATH=src python -m shipcheck apply \
  --evidence /tmp/shipcheck-evidence.json --state /tmp/shipcheck-state.json \
  --receipt /tmp/shipcheck-receipt.json --created-at 2026-01-01T00:00:00Z
PYTHONPATH=src python -m shipcheck verify \
  --receipt /tmp/shipcheck-receipt.json --state /tmp/shipcheck-state.json
PYTHONPATH=src python -m shipcheck rollback \
  --receipt /tmp/shipcheck-receipt.json --state /tmp/shipcheck-state.json
```

Blocked/degraded evaluation and inapplicable dry-runs return exit code `2`.
Malformed input, a transaction conflict, or failed verification returns `1`.

## Transaction guarantees

Dry-run performs no write. Apply verifies the artifact digest and local base SHA,
writes a durable receipt before atomically replacing the local state, then verifies
the exact resulting bytes. Rollback restores the precise prior bytes (including
formatting) or removes a state that did not previously exist. Rollback refuses to
overwrite state changed by another actor after apply.

See `docs/CONTRACT.md`, `docs/TRANSACTIONS.md`, `docs/FAILURE_MODEL.md`, and
`docs/SAFETY.md` for the public contract and limitations.

## Development

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/check.py
PYTHONPATH=src python -m shipcheck probe functional
PYTHONPATH=src python -m safe_merge_gate probe functional
PIP_NO_INDEX=1 python -m pip wheel . --no-deps --no-build-isolation -w dist
```

Licensed under Apache-2.0.
