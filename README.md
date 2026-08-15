# Deploy Truth

Deploy Truth proves whether a release contains the exact expected artifacts and bytes across three distinct layers: **source**, **bundle**, and **live**. It produces deterministic SHA-256 evidence, exposes every difference, and returns `degraded` or `blocked` for drift and partial failure—never a synthetic success.

The CLI and Python API are offline, bounded, and have zero runtime dependencies. Tests, demos, and fixtures are purely synthetic.

## Quick start

```bash
python -m deploy_truth fixture examples/exact-release.json --output truth.json
python -m deploy_truth verify-evidence truth.json
python -m deploy_truth probe functional
python -m deploy_truth demo demo-output
```

To inspect real local directories without modifying them:

```bash
python -m deploy_truth verify \
  --spec examples/release.json \
  --source ./source --bundle ./bundle --live ./live \
  --output truth.json
```

## Decisions

| Decision | Meaning |
| --- | --- |
| `verified` | Every expected path and byte matches in source, bundle, and live; every component is ready. |
| `degraded` | All required artifacts exist, but bytes, unexpected bundle/live files, or component state drift. |
| `blocked` | A layer cannot be captured, source is not a valid baseline, or a required artifact is missing. |

The report preserves source, bundle, and live inventory hashes, artifact hashes and sizes, component versions/dependencies/states, differences, decision reasons, and a content-addressed evidence SHA.

## Transactional local deployment

Create a dry-run plan first:

```bash
python -m deploy_truth plan \
  --spec release.json --bundle ./bundle --live ./live --output plan.json
```

Review the operations and `plan_id`, then apply with an exact confirmation:

```bash
python -m deploy_truth apply \
  --plan plan.json --spec release.json --bundle ./bundle --live ./live \
  --rollback-root ./rollback-evidence --confirm-plan-id PLAN_ID

python -m deploy_truth verify-transaction \
  --plan plan.json --spec release.json --live ./live

python -m deploy_truth rollback \
  --plan plan.json --spec release.json --live ./live \
  --rollback-root ./rollback-evidence --confirm-plan-id PLAN_ID
```

Apply is preconditioned on the exact bundle and live hashes captured during dry-run. It snapshots live, atomically replaces files, verifies the resulting content hash, and automatically restores the snapshot on any partial failure. Rollback retains its state evidence and restores the exact pre-apply inventory.

## Python API

```python
from pathlib import Path
from deploy_truth import capture_and_verify
from deploy_truth.io import load_spec

report = capture_and_verify(
    load_spec(Path("release.json")),
    Path("source"), Path("bundle"), Path("live"),
)
print(report.decision)
print(report.evidence_sha256)
```

## Development

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/check.py
PYTHONPATH=src python -m deploy_truth probe functional
PIP_NO_INDEX=1 python -m pip wheel . --no-deps --no-build-isolation
```

See `docs/` for the architecture, evidence schema, methodology, and operator runbook.

## License

Apache License 2.0. See [LICENSE](LICENSE).

