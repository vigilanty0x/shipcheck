# Safe Merge Gate

Safe Merge Gate is a zero-runtime-dependency Python CLI and library that decides
whether an immutable merge snapshot is safe to apply. It runs entirely offline on
bounded JSON snapshots and synthetic fixtures; it does not call a forge, mutate a
remote branch, or require an account.

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
PYTHONPATH=src python -m safe_merge_gate inventory --snapshot examples/ready-snapshot.json
PYTHONPATH=src python -m safe_merge_gate evaluate \
  --snapshot examples/ready-snapshot.json \
  --policy examples/policy.json \
  --evidence /tmp/safe-merge-evidence.json \
  --generated-at 2026-01-01T00:00:00Z
cp examples/local-state.json /tmp/safe-merge-state.json
PYTHONPATH=src python -m safe_merge_gate dry-run \
  --evidence /tmp/safe-merge-evidence.json --state /tmp/safe-merge-state.json
PYTHONPATH=src python -m safe_merge_gate apply \
  --evidence /tmp/safe-merge-evidence.json --state /tmp/safe-merge-state.json \
  --receipt /tmp/safe-merge-receipt.json --created-at 2026-01-01T00:00:00Z
PYTHONPATH=src python -m safe_merge_gate verify \
  --receipt /tmp/safe-merge-receipt.json --state /tmp/safe-merge-state.json
PYTHONPATH=src python -m safe_merge_gate rollback \
  --receipt /tmp/safe-merge-receipt.json --state /tmp/safe-merge-state.json
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
PYTHONPATH=src python -m safe_merge_gate probe functional
PIP_NO_INDEX=1 python -m pip wheel . --no-deps --no-build-isolation -w dist
```

Licensed under Apache-2.0.

