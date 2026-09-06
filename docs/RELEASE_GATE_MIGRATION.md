# Release gate migration contract

Shipcheck is the canonical repository and product identity. `shipcheck-release-gate` is a source repository to be absorbed, not a second long-term product.

## Preserved compatibility

During the migration window the following existing surfaces remain valid:

- Python package `safe_merge_gate`
- CLI `safe-merge-gate`
- `python -m safe_merge_gate`

New integrations should prefer:

- Python package `shipcheck`
- CLI `shipcheck`
- `python -m shipcheck`

No source repository may be archived until all consumer, compatibility, release, redirect, rollback and human gates are satisfied.

## Source inventory

The source `shipcheck-release-gate` contains a distinct evidence-first release engine with adapters, API helpers, artifacts, a ledger, receipts, redaction, risk/trust logic, public JSON schemas and a static dashboard. Those components must be ported as explicit Shipcheck modules instead of overwriting the existing Safe Merge Gate transaction engine.

Planned target boundaries:

- `shipcheck.release_gate` — release-readiness API and orchestration facade
- `shipcheck.release_gate.*` — evidence, ledger, receipt, adapters, risk/trust and schemas
- `safe_merge_gate.*` — retained legacy merge-snapshot engine until its deprecation window closes

The first migration step intentionally adds only identity aliases and compatibility tests. Functional release-gate modules are ported in bounded batches after source/target contract comparison.

## Consumer inventory gate

Before any source archive, search the public portfolio for all of the following and record repository + path + ref:

- `shipcheck-release-gate`
- `from shipcheck`
- `import shipcheck`
- `shipcheck ` CLI invocations
- `safe-merge-gate`
- `safe_merge_gate`
- copied JSON schemas or compatibility manifests from the source repository

Every discovered consumer must be classified as `MIGRATED`, `LEGACY_SUPPORTED`, `NO_CHANGE_REQUIRED`, or `BLOCKED`.

## Rollback

Rollback is additive and does not require destructive history rewriting:

1. restore the previous Shipcheck release or commit;
2. keep `safe_merge_gate` and `safe-merge-gate` available;
3. remove only newly introduced canonical aliases if they are the failure source;
4. continue using `shipcheck-release-gate` as the temporary release-gate implementation while the target is repaired;
5. do not archive or delete the source repository during the rollback window.

A rollback is successful only when legacy import/CLI smoke tests pass and the pre-migration functional test suite is green.

## Exit criteria

The absorption is complete only when:

- source and target test suites pass against the target implementation;
- old and new import/CLI surfaces pass compatibility smoke tests;
- public schemas have explicit version mappings;
- consumer inventory contains no unresolved consumer;
- wheel/sdist install outside checkout succeeds;
- a negative fail-closed fixture is preserved;
- rollback is rehearsed;
- a human approves source deprecation/archive.
