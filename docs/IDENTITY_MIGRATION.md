# Shipcheck identity migration

## Decision

`shipcheck` is the canonical repository, distribution name, Python import and CLI.
The previous `safe-merge-gate` identity is retained as a compatibility alias for
a transition window. The separate `shipcheck-release-gate` repository is
absorbed as the `shipcheck.release_gate` module; it is not a second canonical
product.

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
Observed source commit:
`8d5813d3ec492abefccc704ba16467f894d71863`.

The source repository tree is
`3dcce371575565d698d10fbd549ae3e774ff379c`, and the source package tree at
`src/shipcheck` is `f6c15f54f350b5283075f3ee3df26ee7e49ed70c`.
The target subtree at `src/shipcheck/release_gate` has the exact same package tree
SHA, proving byte-for-byte preservation of the reviewed package tree.

Source history is also reachable from the target branch. The source commit
resolves inside `vigilanty0x/shipcheck`, and comparison against the current
consolidation lineage uses that exact source commit as the merge base. CI run
`32154064500` independently passed the source-history gate on Ubuntu 24.04 and
Windows 2025 with Python 3.11 and 3.13. That gate executes
`git merge-base --is-ancestor`, verifies the exact repository and package trees,
then archives and tests the exact source commit.

An earlier Git-data import attempt returned HTTP 422. That historical failed
attempt is retained as counter-evidence, but it is no longer the current state:
subsequent consolidation made the exact source history reachable without
fabricating ancestry.

Therefore the code-tree and history gates are verified separately. This still
does **not** authorize redirect, release or source archival; consumer, rollback,
release and human gates remain independent.

## Consumer migration

1. Move new documentation and integrations to `shipcheck`.
2. Run canonical and legacy smoke commands against the same fixture.
3. Record remaining legacy imports/CLI references before removing any alias.
4. Inventory manifests, workflows, docs, package references, forks and explicit
   pilots; code-search alone is only partial evidence.
5. Do not redirect or archive a source repository until the consumer count is
   zero or each remaining consumer has an explicit migration decision.

## Rollback

Before a release or redirect, rollback is the exact inverse of the identity and
release-gate steps:

1. restore the previous `safe-merge-gate` distribution metadata if canonical
   identity must be reverted;
2. keep the `safe_merge_gate` package and CLI untouched;
3. disable/remove only the new `shipcheck` compatibility entrypoints if required;
4. stop routing callers to `shipcheck.release_gate` and retain the source
   repository as the supported release-gate implementation;
5. run the legacy functional counter-proof, exact release-gate source tests and
   full target unit suite;
6. verify the source commit, source package tree and target rollback SHA recorded
   by the rollback receipt.

No release, redirect, archive, deletion or remote source mutation is performed by
this document or by the compatibility wrappers.

## Status vocabulary

This migration may be described as `PREPARED` only after CI passes at the exact
head SHA. Verified source history and exact subtree preservation do not imply
`MERGED`, `TAGGED`, `RELEASED`, post-release `VERIFIED`, `REDIRECTED` or
`ARCHIVED`; those remain distinct gates.
