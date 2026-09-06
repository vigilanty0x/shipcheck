# Shipcheck

Shipcheck is the canonical offline, fail-closed project for merge and release
readiness. Missing, stale, contradictory, or unauthenticated evidence never
becomes a green decision. No command performs a remote merge, deploy, release,
redirect, or archive.

The project keeps two bounded engines behind one product identity:

- **merge readiness** — the original deterministic gate, exposed canonically at
  the `shipcheck` package root and retained as `safe_merge_gate`,
  `shipcheck.merge_gate`, and `safe-merge-gate` for compatibility;
- **release readiness** — the absorbed evidence-first engine under
  `shipcheck.release_gate`, with its historical module aliases and
  `shipcheck-release-gate` CLI retained during migration.

## Integrated evidence-to-rollback workflow

```bash
shipcheck workflow request.json --root ./inputs --output ./new-run --trust-store ./reviewed-local-trust.json
```

This entry chains both engines. It hashes real artifact files, binds the merge
and release candidates and change inventories, computes risk, normalizes and
cross-checks supplied JUnit results, evaluates both policies, then performs
apply → verify → exact rollback on a **new private copy** of the supplied state.
The supplied state and artifacts are rechecked and never changed.

It verifies supplied reports; it does not execute repository commands or claim
the reports were produced during this run. LAB readiness remains `ready_lab`
with `production_ready=false`, even when the local rollback drill passes. A
blocked gate cannot reach the drill, and existing output directories are
refused.

See [the workflow contract](docs/INTEGRATED-WORKFLOW.md). An optional
[producer receipt bundle](docs/PRODUCER-RECEIPTS.md) cross-checks CC receipts and
their complete declared public artifact inventory. It can veto a run; supplied
hashes and candidate bindings never become authenticated evidence.

## Compatibility and commands

New consumers should use `shipcheck`:

```bash
python -m pip install .
python -m shipcheck --help
shipcheck probe functional
shipcheck selftest
```

Existing merge-gate consumers remain supported:

```bash
python -m safe_merge_gate probe functional
safe-merge-gate probe functional
shipcheck merge-gate probe functional
```

Release-readiness commands include `capabilities`, `selftest`, `demo`,
`validate`, `decide`, `artifact`, `normalize`, `ledger`, `promotion`, `receipt`,
and `serve`. They can be invoked directly through `shipcheck`, through the
explicit `shipcheck release-gate ...` prefix, or through the retained
`shipcheck-release-gate` CLI.

Merge commands include `inventory`, `evaluate`, `dry-run`, `apply`, `verify`,
`rollback`, and `probe`. Existing unprefixed commands retain their behavior:

```bash
shipcheck evaluate \
  --snapshot examples/ready-snapshot.json \
  --policy examples/policy.json \
  --evidence /tmp/shipcheck-merge-evidence.json \
  --generated-at 2026-01-01T00:00:00Z
```

## Python API

The canonical root preserves the merge-gate API, while the release engine owns
its explicit namespace:

```python
import safe_merge_gate
import shipcheck
from shipcheck import merge_gate, release_gate

assert shipcheck.evaluate is safe_merge_gate.evaluate
assert merge_gate.evaluate is safe_merge_gate.evaluate
assert shipcheck.Decision is safe_merge_gate.Decision
assert shipcheck.Decision is not release_gate.Decision
assert callable(release_gate.DecisionEngine)
```

Historical release-engine module imports such as `shipcheck.engine` and
`shipcheck.models` resolve to the corresponding `shipcheck.release_gate`
modules.

## Multi-tool source suites

The repository also preserves the full Git histories and source trees of these
related tools under `packages/`:

- `pr-review-council`
- `deploy-truth`
- `flaky-test-tracker`
- `test-evidence-pack`
- `test-gap-finder`
- `local-ci-runner`
- `ci-failure-summarizer`
- `ci-matrix-generator`
- `release-readiness`
- `rollback-drill`
- `diff-risk-scorer`
- `reproducible-demo-harness`

`.portfolio-rehearsal.json` records each source commit, destination prefix, and
tree SHA. CI verifies both ancestry and exact subtree preservation, then runs
every imported suite's repository checks and unit tests.

## Release-gate provenance

The release engine was imported from audited commit
`8d5813d3ec492abefccc704ba16467f894d71863` of
`vigilanty0x/shipcheck-release-gate`. Import commit
`0332482531783984a27878deddc8a19c32e3804b` has that source commit as a parent
and preserves its exact package tree
`f6c15f54f350b5283075f3ee3df26ee7e49ed70c` at
`src/shipcheck/release_gate`.

The current subtree contains later, reviewed integration maintenance from
`main`; CI therefore verifies the immutable import snapshot separately from the
maintained current tree. The source history remains reachable without rewriting
its SHA, and the source's own test gate runs from an archive of the exact source
commit.

The migration remains reversible: `safe_merge_gate` and the compatibility CLIs
remain available, and no source repository is changed by this pull request.

## Development and counter-proofs

```bash
PYTHONPATH=src python scripts/check.py
PYTHONPATH=src python -m unittest discover -s tests -v
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -m pytest -q tests
PYTHONPATH=src python -m shipcheck selftest
PYTHONPATH=src python -m shipcheck probe functional
PYTHONPATH=src python -m safe_merge_gate probe functional
python scripts/verify_consolidation_history.py
python -m pip wheel . --no-deps --no-build-isolation -w dist
```

## Status

This branch is a consolidation candidate. Green checks establish only that the
exact head is prepared for review; they do not imply `MERGED`, `TAGGED`,
`RELEASED`, post-release `VERIFIED`, `REDIRECTED`, or `ARCHIVED`.

Consumer inventory, a final-head rollback receipt, release provenance,
redirect/deprecation windows, archive gates, and explicit human approval remain
separate gates.

Licensed under Apache-2.0.
