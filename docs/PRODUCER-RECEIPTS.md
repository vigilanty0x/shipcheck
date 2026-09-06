# Producer receipt bundles

The integrated workflow accepts an optional `producer_bundle`. It checks supplied
CC receipts and the physical bytes of their declared public artifacts before
running the existing release and merge gates. A failure blocks the workflow.
A coherent bundle cannot override a native gate, authenticate a producer, or
authorize publication. No producer is executed or imported by the checker.

This first adapter accepts `skyom.business.run.v1`, the CC wrapper used by
`ai-software-factory`, `promptops`, `repo-doctor-ai`, `rag-lab`, and
`local-ai-stack`. It does not replay their native engine receipts or Proofgate
contracts. The producer code, snapshots and databases are not inspected.

## Closed bundle contract

Add this object to the existing `shipcheck/workflow-v1` request. The command
remains `shipcheck workflow REQUEST --root INPUTS --output NEW_RUN`.

| Field | Required value |
|---|---|
| `schema_version` | `shipcheck/producer-bundle-v1` |
| `candidate` | The exact native Candidate object: repository, base_commit, head_commit, tree_digest, ref |
| `max_age_seconds` | Integer 1 through 604800; booleans are rejected |
| `require_quality` | Explicit boolean |
| `receipts` | 1 through 16 receipt entries |

Each entry contains exactly:

| Field | Required value |
|---|---|
| `producer_id` | One of the five IDs above |
| `candidate` | Exactly the bundle and release candidate |
| `receipt_path` | Canonical relative path beneath INPUTS |
| `receipt_sha256` | Lowercase SHA-256 of the raw receipt file |
| `artifacts` | Complete list of `{id, path}` bindings for the receipt's declared public artifact inventory |

Paths never accept absolute names, `..`, alternate separators, symlinks,
junctions, hardlinks, duplicate paths or duplicate physical files. No path is
interpreted as a command. Each receipt's artifact ID must appear exactly once;
missing, additional or unknown IDs are refused. Actual bytes and SHA-256 must
match every receipt artifact row. Its `input` artifact must match
`request_sha256`. Distinct receipts cannot reuse a run ID or receipt digest.

Bounds are 1 MiB per receipt, 4 MiB per artifact, 128 files and 64 MiB total,
including receipts. JSON also uses the native strict parser's depth, node and
string bounds. Duplicate keys and non-finite numbers are rejected. Reads verify
regular file type, single link count and unchanged metadata before and after
reading. All checked files are read again before workflow completion. This is
bounded consistency verification, not an atomic filesystem snapshot or a
guarantee that files cannot change after verification.

## Receipt contract and quality

Required receipt fields are `schema`, `product_id`, `run_id`, `started_at`,
`finished_at`, `request_sha256`, `pins_sha256`, `durable`, `input_origin`,
`provider_called`, `target_code_executed`, `state`, `execution_ok`,
`gate_quality`, `artifacts`, `engine`, and `scope`. Optional fields are
`source_selection`, `replay_of`, `reserved_bytes`, `worker_sha256`,
`recipe_sha256`, `quality_state`, `reason_code`, `exit_code`, `timed_out`,
`source_manifest_sha256`, `source_snapshot_created`, and `storage`.
Unknown fields are refused. Engine/source/storage objects remain declared
metadata; their embedded claims are not independently verified.

Booleans are strict, except `provider_called` and `gate_quality`, which also
accept null. Execution must have completed successfully; a timeout, nonzero
exit or unfinished state is refused. `quality_state`, when present, must agree
with `gate_quality`. A completed run with false quality has `state=quality_failed`.
The timestamp values must be finite, nonnegative, and satisfy
`started_at <= finished_at <= verification time`. Freshness is based on the
receipt's finish time, never its file modification time, and is checked again
at completion. Clock rollback cannot keep a future receipt usable.

When `require_quality=true`, false quality yields `producer_quality_failed`
and null yields `producer_quality_not_measured`. When it is false, both values
remain explicit in the result. Passing this consistency check does not assert
that quality was measured or sufficient for release.

## What is proved and retained

`producer-receipts.json` records the checked paths, byte counts, digests,
receipt IDs, declared quality/provider/scope, verification time and result.
The workflow includes this verification digest in its first stage and records
`producer_files_rechecked=true` only after successful final checks. On refusal,
the workflow is blocked and retains its diagnostics; it does not reuse or purge
an existing output directory. Output retention across invocations is managed
by the caller, as for the original workflow.

The Git candidate binding is **declared_only**: CC receipts currently do not
carry the assessed repository/base/head themselves. Matching a supplied digest
does not establish an authenticated checkpoint. The verification therefore
always says `authenticity_established=false`, `publication_authorized=false`,
and `native_engine_receipts_replayed=false`. The native release trust policy,
JUnit testcase checks, ledger and rollback-on-copy behavior remain unchanged.

The inventory is complete only relative to the public artifact rows declared
in each supplied receipt. Omitting any such row is refused. This does not prove
that a producer truthfully listed every file it retained: source snapshots and
databases are outside this adapter's verification scope. Adapters for native
producer schemas, authenticated CI binding, full Proofgate policies and real
deployment or restoration evidence remain separate work.
