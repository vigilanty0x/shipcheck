# Operator runbook

## Inspect

Run `verify` and retain the JSON report. A non-zero exit is actionable evidence: code 2 is degraded, code 3 is blocked, code 4 is invalid input, and code 5 is local I/O failure.

## Plan

Generate `plan.json`, review every operation, record its `plan_id`, and ensure the rollback root is separate from bundle and live. A plan is invalidated automatically if either bundle or live bytes change.

## Apply and verify

Pass the exact plan ID to `apply`. Do not retry a blocked transaction by editing its evidence. Investigate the outputs and create a new dry-run after correcting the cause. Run `verify-transaction` after apply even though apply already performs an internal postcondition check.

## Roll back

Use the same plan, release spec, rollback root, and confirmation ID. The command refuses missing, corrupt, already rolled-back, or non-applied state. A verified rollback means the pre-apply content SHA was restored exactly; it does not claim that the old release was healthy.

## Counter-proof

Run `python -m deploy_truth probe functional`. Healthy means the exact control verified while byte drift and partial release were rejected.

