# Shipcheck

Shipcheck is the canonical package and CLI for this repository. It provides an
offline, zero-runtime-dependency readiness gate over bounded JSON snapshots and
synthetic fixtures. It does not call a forge, mutate a remote branch, or require
an account.

This consolidation branch is intentionally transitional. The original
`safe-merge-gate` implementation remains available as a compatibility namespace
and CLI alias while consumers move to `shipcheck`. The separate
`shipcheck-release-gate` repository is an absorption candidate for the
`release_gate` module; its richer release engine is **not** claimed as merged by
this identity-only step.

`ready` is the only applicable merge decision. Required failures produce
`blocked`. Optional failures produce `degraded`, which is still not applicable.

The current core verifies:

- expected SHA equals observed SHA;
- every required CI check succeeded;
- tests completed and passed;
- secret scanning completed with no fingerprinted finding;
- the local tree is clean;
- changed file, changed line, and binary-file limits;
- a canonical, sorted and uniquely addressed change inventory.

## Canonical CLI

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

## Legacy compatibility

During the transition window these remain supported and are expected to produce
the same behavior:

```bash
PYTHONPATH=src python -m safe_merge_gate probe functional
safe-merge-gate probe functional
```

New integrations should use `shipcheck` or `python -m shipcheck`. See
`docs/IDENTITY_MIGRATION.md` for the compatibility and rollback contract.

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

## Status

This draft is **PREPARED**, not merged, tagged, released, redirected, or archived.
Source repositories remain unchanged until compatibility, consumer inventory,
rollback, release, and human approval gates are complete.

Licensed under Apache-2.0.
