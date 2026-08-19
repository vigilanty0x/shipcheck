# Shipcheck

Shipcheck is the canonical offline evidence gate for merge and release readiness.
It is intentionally fail-closed: missing, stale, contradictory, or unauthenticated
evidence does not become a green decision.

The consolidation keeps two bounded engines behind one product identity:

- **release readiness** — the absorbed evidence-first release engine under
  `shipcheck.release_gate`, including strict contracts, normalized CI artifacts,
  ledger/receipts, rollback observations, reports, and a read-only local UI;
- **merge readiness** — the original deterministic merge gate retained as
  `safe_merge_gate` and `shipcheck.merge_gate` for compatibility.

No command performs a remote merge, deploy, release, redirect, or archive.

## Install and prove the package

```bash
python -m pip install .
shipcheck --help
shipcheck selftest
shipcheck probe functional
safe-merge-gate probe functional
```

`shipcheck selftest` is handled by the release engine. `shipcheck probe
functional` is intentionally routed to the merge-compatibility engine. Existing
merge commands continue to work through the canonical dispatcher:

```bash
shipcheck inventory --snapshot examples/ready-snapshot.json
shipcheck evaluate \
  --snapshot examples/ready-snapshot.json \
  --policy examples/policy.json \
  --evidence /tmp/shipcheck-merge-evidence.json \
  --generated-at 2026-01-01T00:00:00Z
```

Release-readiness commands include `capabilities`, `selftest`, `demo`, `validate`,
`decide`, `artifact`, `normalize`, `ledger`, `promotion`, `receipt`, and `serve`.
The absorbed engine remains offline and treats normalized external artifacts as
supplied evidence rather than trusted truth.

## Python API

The canonical root API is the release-readiness API:

```python
import shipcheck
from shipcheck import release_gate

assert shipcheck.DecisionEngine is release_gate.DecisionEngine
```

Merge-gate consumers retain explicit compatibility paths:

```python
import safe_merge_gate
from shipcheck import merge_gate

assert merge_gate.evaluate is safe_merge_gate.evaluate
```

## Source-history provenance

The release engine is sourced from the exact audited commit
`8d5813d3ec492abefccc704ba16467f894d71863` of
`vigilanty0x/shipcheck-release-gate`. The consolidation commit is created with
that commit as a second parent, making the original source history reachable
without rewriting its SHA. The exact imported package tree is
`f6c15f54f350b5283075f3ee3df26ee7e49ed70c`.

The migration remains reversible: the `safe_merge_gate` package and legacy CLI
are not deleted, and source repositories are not modified by this PR.

## Development and counter-proofs

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/check.py
PYTHONPATH=src python -m shipcheck selftest
PYTHONPATH=src python -m shipcheck probe functional
PYTHONPATH=src python -m safe_merge_gate probe functional
python -m pip wheel . --no-deps --no-build-isolation -w dist
```

CI additionally proves that the exact second-parent source commit is an ancestor
of the target HEAD, that its repository/package tree SHAs match the audited
values, and that its own source test gate passes from an extracted exact commit.

## Status

This branch is a consolidation rehearsal. A green CI run can establish
`PREPARED` at an exact SHA; it does not imply `MERGED`, `TAGGED`, `RELEASED`,
post-release `VERIFIED`, `REDIRECTED`, or `ARCHIVED`.

Consumer inventory, rollback rehearsal, release artifacts/provenance, redirect
window, archive gates, and explicit human approval remain separate gates.

Licensed under Apache-2.0.
