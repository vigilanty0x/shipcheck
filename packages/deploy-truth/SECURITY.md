# Security policy

## Reporting

Use the repository's private vulnerability reporting feature. Do not publish sensitive deployment details in an issue.

## Security properties

- Verification is offline and does not execute release artifacts.
- Paths must be bounded, relative POSIX paths without traversal.
- Directory capture rejects symlinks and applies file/count/total-byte limits.
- Source, bundle, live, plan, transaction, and report evidence is content-addressed.
- Apply requires the exact reviewed `plan_id` and rechecks bundle/live preconditions.
- File writes use same-directory temporary files and atomic replacement.
- Pre-apply live bytes are snapshotted; partial apply triggers automatic restoration.
- Missing, corrupt, drifting, or blocked evidence never returns a verified decision.

Deploy Truth performs local filesystem changes only when the explicit `apply` or `rollback` commands are used. It never deploys remotely, logs into an account, manages credentials, or bypasses filesystem permissions.

