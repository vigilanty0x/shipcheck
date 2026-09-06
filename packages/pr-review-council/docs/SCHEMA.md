# Schemas and decisions

## Pull-request snapshot

Required fields:

- `pr_id`: non-empty string, up to 128 bytes;
- `commit_sha`: exactly 40 hexadecimal characters;
- `title`: non-empty string, up to 300 bytes;
- `body`: string, up to 200,000 bytes;
- `files`: 1 to 500 unique relative file objects.

Each file has `path`, `patch`, `additions`, and `deletions`. Absolute paths, parent traversal, `.git` paths, Windows separators, negative counters, duplicate paths, and patches over 256 KiB are rejected.

## Report

The report contains schema and tool versions, source identity, decision, a degraded flag, every reviewer outcome, sorted findings, severity/reviewer counts, and a deterministic `report_sha`. Finding fingerprints are stable and never include the matched secret-like value.

Decisions are `approved`, `changes_requested`, `degraded`, or `blocked`.

## Publication receipt

A verified receipt binds:

- transaction identifier;
- resolved output path;
- applied payload SHA;
- previous payload SHA, if any;
- exact rollback backup path, if any;
- verification state.

Receipts with unknown schema versions or non-verified states are rejected by the rollback CLI.
