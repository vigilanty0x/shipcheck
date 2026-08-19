# Contributing

Contributions are welcome through focused pull requests.

1. Describe the reviewer rule or transaction invariant being changed.
2. Add a counter-example that fails for the intended reason.
3. Implement the smallest deterministic fix.
4. Run `python scripts/check.py` and the full unit suite.
5. Document false-positive boundaries and compatibility changes.

New reviewer rules must have stable identifiers, avoid leaking matched secrets, operate only on bounded inputs, and include both triggering and non-triggering tests. Do not add network calls or model APIs to the default review path.
