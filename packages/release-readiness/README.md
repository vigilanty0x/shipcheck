# Release Readiness

Gate releases on exact commit and completed checks.

## Quick start

```bash
python -m pip install -e .
release-readiness record.json
```

The CLI emits deterministic JSON with a fail-closed status and a SHA-256 evidence identifier. Required fields: `version`, `commit_sha`, `checks_passed`, `checks_total`. Rule: all release checks must pass.

## Development

```bash
python -m unittest discover -s tests -v
python scripts/check.py
```

Apache-2.0 licensed. No runtime dependencies.

