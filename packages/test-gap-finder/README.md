# Test Gap Finder

Detect untested surfaces with deterministic coverage evidence.

## Quick start

```bash
python -m pip install -e .
test-gap-finder record.json
```

The CLI emits deterministic JSON with a fail-closed status and a SHA-256 evidence identifier. Required fields: `surface`, `tested`, `total`. Rule: tested must cover total.

## Development

```bash
python -m unittest discover -s tests -v
python scripts/check.py
```

Apache-2.0 licensed. No runtime dependencies.

