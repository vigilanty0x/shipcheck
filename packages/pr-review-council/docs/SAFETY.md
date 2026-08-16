# Safety and limits

## Safety properties

- Input sizes, path forms, file counts, and patch sizes are bounded.
- Bundled reviewers are deterministic and offline.
- Reviewer exceptions remain visible and cannot yield `approved`.
- Reports identify the exact reviewed commit SHA.
- Publication is atomic within one filesystem and verified from served bytes.
- Rollback requires an explicit acknowledgement and an exact SHA match.
- Existing backups are never overwritten.
- Secret-shaped findings describe the category without reproducing the value.

## Limits

The council analyzes only the supplied diff snapshot. It does not parse a complete language grammar, execute changed code, inspect repository history, verify dependency provenance, or prove absence of vulnerabilities. Heuristics can produce false positives and false negatives. A green decision supports review; it does not replace tests, domain experts, security review, or repository policy.

The publisher is a local file transaction, not a deployment system. Cross-filesystem atomicity and distributed rollback are outside version 0.1.0.
