# Integrated workflow

`shipcheck workflow REQUEST --root INPUTS --output NEW_RUN [--trust-store FILE]`
is one execution path over the current APIs, not a menu of independently
invoked commands. It keeps both historical command families compatible.

The request is a closed JSON object with these required fields:

| Field | Contract |
|---|---|
| `schema_version` | `shipcheck/workflow-v1` |
| `release_evidence` | existing `ReleaseEvidence.to_dict()` contract |
| `release_policy` | existing `ReleasePolicy.to_dict()` contract |
| `merge_snapshot` | existing `MergeSnapshot.to_dict()` contract |
| `merge_policy` | existing `GatePolicy.to_dict()` contract |
| `artifacts` | 1–100 unique `{name,path}` bindings, exactly the required artifact names |
| `junit` | 1–100 unique relative report paths, exactly the required suite names |
| `state_path` | relative existing JSON state containing the same repository/base SHA |
| `allow_lab` | explicit boolean; false refuses a non-production decision |

The only optional field is `producer_bundle`, described in
[Producer receipt bundles](PRODUCER-RECEIPTS.md). It inserts a consistency veto
before the evidence stage. Its absence keeps the original workflow unchanged.

Relative paths use the existing path contract and reject symlinks/junctions.
Inputs are bounded and no source is imported or executed. An optional trust
store uses the existing restrictive secret-file reader; no key is generated or
published by the workflow. Without configured trust, missing assurance remains
missing. HMAC verification is local trust, not a public signature.

The public Python API is
`shipcheck.workflow.run_workflow(request, root=..., output=..., trust_store=...)`.
The trust store object can be supplied directly by trusted application code.

Stages are evidence, risk, tests, release gate and rollback. Both gate decisions
are retained. The report sets `tests_executed_here=false`; JUnit's physical
bytes and counts are recorded and compared to the release evidence. Matching
counts alone do not prove provenance, so the existing release trust checks also
remain mandatory. File content, evidence and policy digests are linked to the
single request. A source file changed during the run blocks completion.

The new run directory contains release/merge decisions, the copied drill state,
a rollback receipt and the final workflow receipt. A successful drill changes
only that copy and restores its exact prior bytes, including formatting. This
does not prove a deployment rollback on some other infrastructure. A conflict
is a blocked run; diagnostics and already-created artifacts are retained.

Result states are `ready`, `ready_lab`, or `blocked`. `publication` is always
false. The CLI returns 0 for either completed readiness workflow and 2 for a
refusal or invalid input. Consumers authorizing production must separately
require `production_ready=true`; process exit 0 is not publication permission.

`tests/test_workflow.py` constructs a full signed synthetic request, actual
artifacts and an 88-case JUnit report, then proves the single CLI/API path and
counterexamples: wrong bytes/SHA, contradictory tests/diffs, rejected risk,
LAB/production mismatch, blocked merge, duplicate/path inputs, retained output,
and a concurrently changed drill copy. These fixtures are not production proof.
