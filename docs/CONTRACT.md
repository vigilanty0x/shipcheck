# Contract

Snapshot schema `1.0` includes repository label, expected/observed/merge SHAs,
timezone-aware capture time, CI states, test and secret-scan completion, fingerprinted
secret findings, clean-tree state, and canonical changes. Inputs are limited to 1 MB,
500 changes, 100 CI checks, and 100 secret findings.

Changes are normalized relative POSIX paths, unique, and sorted. Inventory SHA covers
paths, additions, deletions, binary flags, and totals. Artifact SHA covers tool/schema
versions, snapshot and inventory hashes, policy, every check/output, and decision.

`ready` means all required checks succeeded. `degraded` means required checks passed
but at least one optional check did not. `blocked` means at least one required check
failed, is pending, or is missing. Only `ready` may be applied.

