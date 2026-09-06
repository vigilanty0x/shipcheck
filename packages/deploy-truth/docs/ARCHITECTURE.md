# Architecture

## Trust model

The release spec declares the complete artifact path set and canonical component metadata. Source is the intended-byte baseline. Bundle proves what is packaged. Live proves what is served from the local deployment directory.

Deploy Truth hashes bytes independently in every layer. It does not trust filenames, versions, prior reports, or plan claims without recomputing their identities.

## Flow

1. Validate component names, versions, dependency graph, states, and exact paths.
2. Capture bounded non-symlink files from source, bundle, and live.
3. Hash every artifact and canonical inventory.
4. Compare all expected and unexpected paths and bytes.
5. Derive a fail-closed decision and hash the complete evidence document.
6. Optionally plan a bundle-to-live transaction from exact precondition hashes.
7. Snapshot, apply atomically, verify, and retain rollback evidence.

Transactions never execute artifact content. They only copy or delete exact relative file paths recorded in a reviewed plan.

