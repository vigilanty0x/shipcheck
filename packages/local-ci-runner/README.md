# Local CI Runner

Normalize local CI command results before remote execution.

## Quick start

```bash
python -m pip install -e .
local-ci-runner record.json
```

The CLI emits deterministic JSON with a fail-closed status and a SHA-256 evidence identifier. Required fields: `command`, `exit_code`, `duration_ms`. Rule: exit_code must be zero.

## Development

```bash
python -m unittest discover -s tests -v
python scripts/check.py
```

Apache-2.0 licensed. No runtime dependencies.

