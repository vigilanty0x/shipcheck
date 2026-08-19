# Flaky Test Tracker

Measure unstable tests with reproducible pass-rate evidence.

## Quick start

```bash
python -m pip install -e .
flaky-test-tracker record.json
```

The CLI emits deterministic JSON with a fail-closed status and a SHA-256 evidence identifier. Required fields: `test_name`, `passes`, `runs`. Rule: runs must be positive and passes cannot exceed runs.

## Development

```bash
python -m unittest discover -s tests -v
python scripts/check.py
```

Apache-2.0 licensed. No runtime dependencies.

