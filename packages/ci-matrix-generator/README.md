# CI Matrix Generator

Generate deterministic operating-system and runtime test matrices.

## Quick start

```bash
python -m pip install -e .
ci-matrix-generator record.json
```

The CLI emits deterministic JSON with a fail-closed status and a SHA-256 evidence identifier. Required fields: `target`, `python_versions`, `operating_systems`. Rule: matrix dimensions must be non-empty lists.

## Development

```bash
python -m unittest discover -s tests -v
python scripts/check.py
```

Apache-2.0 licensed. No runtime dependencies.

