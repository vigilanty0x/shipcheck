# PR Review Council

PR Review Council is a deterministic, offline Python tool that asks specialized reviewers to analyze a bounded pull-request snapshot and then emits one machine-readable decision. It is designed for reproducible demonstrations, local CI gates, and evidence-aware review workflows without requiring a Git hosting account or model API.

The bundled council separates four concerns:

- **security** detects secret-shaped additions and unsafe dynamic execution;
- **reliability** flags unbounded network calls and over-broad exception handling;
- **testing** checks whether source changes carry test evidence and whether coverage is only removed;
- **maintainability** highlights oversized changes and untracked debt markers.

Reviewer failure is never reported as success. If quorum is lost, the decision is `blocked`; if quorum remains but part of the council fails, the decision is `degraded`.

## Quick start

```bash
python -m pip install -e .
pr-review-council review --input examples/pr.json
pr-review-council review --input examples/counter-proof.json --fail-on-gate
```

Run the complete local transaction demo:

```bash
pr-review-council demo --workspace /tmp/pr-review-council-demo
```

The demo analyzes a synthetic PR, plans an output update, atomically applies it, verifies the bytes actually served, rolls back to a known-good file, verifies that restoration, and safely replays the transaction.

## Transactional publication

Dry-run first:

```bash
pr-review-council plan \
  --input examples/pr.json \
  --output /tmp/review-report.json
```

Apply and verify while writing a rollback receipt:

```bash
pr-review-council publish \
  --input examples/pr.json \
  --output /tmp/review-report.json \
  --receipt /tmp/receipt.json

pr-review-council verify --receipt /tmp/receipt.json
pr-review-council rollback --receipt /tmp/receipt.json --yes
```

Rollback is fail-safe: it refuses to overwrite a report that no longer matches the exact applied SHA recorded in the receipt.

## Probes

```bash
pr-review-council probe --level liveness
pr-review-council probe --level readiness
pr-review-council probe --level functional
```

- liveness proves the process and version are available;
- readiness proves the configured reviewer inventory can satisfy quorum;
- functional proof runs a synthetic counter-example and requires the gate to block it.

## Input contract

Inputs are JSON objects capped at 1 MiB. A snapshot contains a PR identifier, an exact 40-character commit SHA, a title, optional body, and up to 500 unique relative file changes. Every patch is capped at 256 KiB. See [the schema guide](docs/SCHEMA.md) and [the executable fixture](examples/pr.json).

No network access is performed. The tool reviews the supplied snapshot only; it does not fetch a PR, post comments, merge code, or replace expert review.

## Development

```bash
python scripts/check.py
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m pr_review_council probe --level functional
python -m compileall -q src tests scripts
```

CI repeats the checks on Python 3.11 and 3.12, exercises the transaction demo, and builds a wheel.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Schemas and decisions](docs/SCHEMA.md)
- [Safety and limits](docs/SAFETY.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [AI assistance disclosure](AI_ASSISTANCE.md)

## License

Apache License 2.0.
