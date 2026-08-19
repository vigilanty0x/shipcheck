# Diff Risk Scorer

## Purpose

Score bounded declared diff metadata using line volume and explicit sensitive/binary flags.

## Non-goals

It does not parse patches, inspect repository content, detect vulnerabilities, or replace human review.

## Install

Requires Python 3.11 or newer.

```console
python -m pip install .
```

## CLI and API

Run the built-in positive and negative control:

```console
diff-risk probe
```

Process JSON from a file:

```console
diff-risk score --input examples/basic.json
```

The public Python seam is `diff_risk_scorer.score`:

```python
from diff_risk_scorer import score
```

Functions return structured JSON-compatible results and reject malformed input without raising validation exceptions.

## Example

A runnable input is provided at `examples/basic.json`. CLI output is deterministic and includes either a SHA-256 evidence field or an explicit validation failure.

## Security and trust model

Paths, counts, and flags are untrusted. Counts are bounded non-boolean integers, flags are strict booleans, paths are unique safe relatives, and aggregate work is capped. The tool performs no network calls.

## Limitations

At most 1,000 files, one million changed lines per field, and ten million changed lines globally are accepted.

## Tests

Run the same local gates used by CI:

```console
python -m unittest discover -s tests -v
python scripts/check.py
python -m build --no-isolation
diff-risk probe
diff-risk score --input examples/basic.json
```

CI tests Python 3.11 and 3.12, installs the project and rebuilt wheel, imports the installed package, and exercises both the probe and example.

## AI disclosure

AI assistance supported defensive implementation, adversarial test design, and documentation. See [AI_ASSISTANCE.md](AI_ASSISTANCE.md) for scope and review expectations.

## License

Apache-2.0. See [LICENSE](LICENSE).

