# Transactions

Dry-run reads the local JSON state and proves whether its `current_sha` matches the
artifact base. It performs no write.

Apply writes a durable receipt containing the exact prior bytes, their SHA, expected
base, target SHA, artifact SHA, and expected post-apply byte SHA. It then atomically
replaces the local state and verifies exact bytes plus the target SHA. If apply-time
verification raises, the implementation restores the prior state.

Rollback accepts only the exact post-apply bytes (or an already restored state). It
refuses divergence, then restores the exact prior bytes or removes a previously absent
file. Receipt paths cannot be reused, preventing accidental loss of recovery data.

