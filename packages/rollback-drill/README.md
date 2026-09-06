# Rollback Drill

Record rollback targets and recovery-time evidence.

## Quick start

```bash
python -m pip install -e .
rollback-drill record.json
```

The CLI emits deterministic JSON with a fail-closed status and a SHA-256 evidence identifier. Required fields: `release`, `rollback_target`, `recovery_seconds`. Rule: recovery must complete within five minutes.

## Development

```bash
python -m unittest discover -s tests -v
python scripts/check.py
```

Apache-2.0 licensed. No runtime dependencies.

