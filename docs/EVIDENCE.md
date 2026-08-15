# Evidence schema 1.0

## Release spec

A release has a version, canonical component inventory, and `spec_sha256`. Each component has a name, version, dependencies, operational state, and exact artifact paths. Dependencies must exist and be acyclic; artifact paths are globally unique.

## Layer inventory

Each source, bundle, or live inventory contains capture state, ordered artifacts, inventory SHA, and visible blockage information. Every artifact records path, component, size, and SHA-256.

## Truth report

The report includes the three complete inventories, per-path differences, component versions/dependencies/states, decision reasons, and `evidence_sha256`. The evidence verifier recomputes each inventory identity and the entire report identity.

## Transaction evidence

A plan hashes the release spec, pre-apply live inventory, desired bundle inventory, and ordered write/delete operations. Apply and rollback results preserve outputs, before/after/rollback hashes, outcome, decision, and their own evidence SHA.

