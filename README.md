# Reproducible Demo Harness

## Purpose

Hash a real local artifact beneath an operator-selected allowed root and compare its bytes with a separately trusted expected SHA-256 digest.

## Non-goals

This package does not execute demo commands, accept shell strings, download artifacts, or establish the expected digest's trustworthiness.

## Install

Requires Python 3.11 or newer: `python -m pip install .`

## API

`evaluate(record, allowed_root=...)` accepts only relative `artifact_path` and `expected_sha256`. Omitting `allowed_root` uses the current directory.

## CLI

From the repository root, run `reproducible-demo-harness examples/valid.json`. The CLI hashes the checked-in example artifact and never executes code.

## Example

`examples/demo-output.txt` has the digest declared in `examples/valid.json`.

## Security

Absolute paths, traversal outside the resolved root, symlink files, non-files, malformed digests, extra assertion fields such as `actual_sha256`, and artifacts over 16 MiB fail closed.

## Limits

The comparison proves byte equality only. It does not prove who produced the expected digest or that the artifact is safe to execute.

## Tests

Run `python -m unittest discover -s tests -v` and `python scripts/check.py`.

## AI assistance

See `AI_ASSISTANCE.md`; trusted digest distribution remains a human/release-system responsibility.

## License

Apache-2.0; see `LICENSE`.
