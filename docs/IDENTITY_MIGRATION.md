# Shipcheck identity migration

## Decision

`shipcheck` is the canonical repository, distribution name, Python import and CLI.
The previous `safe-merge-gate` identity is retained as a compatibility alias for
a transition window. The separate `shipcheck-release-gate` repository is an
absorption candidate for the future `shipcheck.release_gate` module; it is not a
second canonical product.

## Compatibility contract

Current canonical paths:

- distribution: `shipcheck`;
- import: `import shipcheck`;
- module CLI: `python -m shipcheck`;
- installed CLI: `shipcheck`.

Legacy paths intentionally retained:

- import: `import safe_merge_gate`;
- module CLI: `python -m safe_merge_gate`;
- installed CLI: `safe-merge-gate`.

The canonical API and CLI currently delegate to the legacy implementation. Tests
must prove object/entrypoint parity so the identity migration cannot change gate
semantics accidentally.

## Release-gate absorption boundary

Audited source repository: `vigilanty0x/shipcheck-release-gate`.
Observed source commit for the next migration step:
`8d5813d3ec492abefccc704ba16467f894d71863`.

This identity commit does **not** claim that source history or the richer release
engine has already been imported. That remains a separate, reviewable migration
with source-tree verification, source tests, target tests, consumer inventory and
rollback evidence.

## Consumer migration

1. Move new documentation and integrations to `shipcheck`.
2. Run canonical and legacy smoke commands against the same fixture.
3. Record remaining legacy imports/CLI references before removing any alias.
4. Do not redirect or archive a source repository until the consumer count is
   zero or each remaining consumer has an explicit migration decision.

## Rollback

Before a release or redirect, rollback is the exact inverse of the identity step:

1. restore the previous `safe-merge-gate` distribution metadata;
2. keep the `safe_merge_gate` package and CLI untouched;
3. remove only the `shipcheck` compatibility package/entrypoint introduced by
   this migration;
4. run the legacy functional counter-proof and full unit suite;
5. verify the repository/tree SHA expected by the rollback receipt.

No release, redirect, archive, deletion or remote mutation is performed by this
document or by the compatibility wrappers.

## Status vocabulary

This migration may be described as `PREPARED` only after CI passes at the exact
head SHA. It is not `MERGED`, `TAGGED`, `RELEASED`, post-release `VERIFIED`,
`REDIRECTED` or `ARCHIVED` until those distinct gates occur.
