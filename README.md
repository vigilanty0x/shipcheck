# Test Evidence Pack

Bundle test outcomes and commit provenance into verifiable evidence.

## Quick start

```bash
python -m pip install -e .
test-evidence-pack record.json
```

The CLI emits deterministic JSON with a fail-closed status and a SHA-256 evidence identifier. Required fields: `suite`, `commit_sha`, `passed`, `failed`. Rule: failed must be zero.

## Development

```bash
python -m unittest discover -s tests -v
python scripts/check.py
```

Apache-2.0 licensed. No runtime dependencies.

