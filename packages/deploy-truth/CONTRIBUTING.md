# Contributing

Contributions must preserve the central invariant: release failure, drift, missing evidence, and partial apply can never be represented as success.

1. Use synthetic fixtures and temporary local directories only.
2. Add public-contract tests for every decision or transaction change.
3. Keep paths, artifact counts, file sizes, and transaction roots bounded.
4. Keep shell execution and runtime dependencies out of the project.
5. Run the test suite, public-boundary check, functional counter-proof, demo, and offline wheel build.

Pull requests should state the observable contract change, failure modes, rollback behavior, and fresh verification evidence. Never include credentials, host inventories, production paths, account data, or private release artifacts.

