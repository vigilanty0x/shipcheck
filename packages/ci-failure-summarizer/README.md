# CI Failure Summarizer

Create stable, redacted summaries from CI failures.

## Quick start

```bash
python -m pip install -e .
ci-failure-summarizer record.json
```

The CLI emits deterministic JSON with a fail-closed status and a SHA-256 evidence identifier. Required fields: `job`, `failure`, `log_excerpt`. Rule: failure and log excerpt must be present.

## Development

```bash
python -m unittest discover -s tests -v
python scripts/check.py
```

Apache-2.0 licensed. No runtime dependencies.

