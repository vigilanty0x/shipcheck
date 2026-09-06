# Architecture

PR Review Council is a local pipeline with explicit trust boundaries.

1. `PullRequestSnapshot` validates and bounds external JSON.
2. `ReviewCouncil` invokes each selected reviewer independently and captures failures as outcomes.
3. The synthesizer sorts findings, checks quorum, and derives one decision.
4. `ReportPublisher` creates a dry-run plan, atomically applies a report, verifies its exact bytes, and returns a rollback receipt.
5. Probes distinguish process availability, configuration readiness, and functional proof.

The canonical inventory is returned by `pr-review-council inventory`. Runtime behavior has no network dependency and no hidden model invocation.

## Decision order

The gate evaluates in this order:

1. insufficient successful reviewers -> `blocked`;
2. any configured blocking severity -> `blocked`;
3. partial reviewer failure with quorum -> `degraded`;
4. high or medium findings -> `changes_requested`;
5. otherwise -> `approved`.

This order prevents partial execution from being presented as success.

## Transaction states

`planned -> applied -> verified` is the normal path. An exact receipt can move a verified output to `rolled_back`. Drift, missing backups, mismatched SHAs, or verification failure produce `blocked` errors instead of optimistic success.
