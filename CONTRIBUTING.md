# Contributing

Keep contributions public, offline, deterministic, and narrowly scoped. Never add
credentials, private endpoints, real production snapshots, customer data, or raw
secret values. Secret fixtures must contain fingerprints only.

Changes to decision semantics require contract tests for ready, degraded, blocked,
partial failure, transaction verification, and rollback. Run:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/check.py
PYTHONPATH=src python -m safe_merge_gate probe functional
```

Contributions are licensed under Apache-2.0.

