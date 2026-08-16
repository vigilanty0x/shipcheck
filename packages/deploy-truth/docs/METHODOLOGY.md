# Verification methodology

`verified` requires exact agreement: same expected path set, byte hashes, sizes, and ready component states across source, bundle, and live.

Byte drift, unexpected bundle/live artifacts, or non-ready component state is `degraded`. Missing required artifacts, unexpected source artifacts, or any blocked layer is `blocked`. These rules are intentionally asymmetric: extra source bytes invalidate the baseline, while an extra bundle/live byte proves deployment drift.

The functional probe uses three independent synthetic cases:

- exact control must verify;
- changed live bytes must degrade;
- missing live artifact must block.

It also replays the exact fixture and requires the same evidence SHA.

