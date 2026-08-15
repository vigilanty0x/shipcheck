# Failure model

Mismatch, missing and pending are explicit failure states. No failed, partial, or
degraded decision can be applied. Invalid evidence and receipts are rejected before
state mutation. Apply refuses an unexpected local SHA; rollback refuses any state
changed after apply.

Atomic replacement is scoped to one local filesystem path. The tool does not perform
a real remote forge merge, coordinate distributed writers, sign evidence, or provide
cross-filesystem transactions. Callers needing those properties must add external
locking, signatures, and orchestration.

