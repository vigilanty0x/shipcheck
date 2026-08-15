# Security policy

Report vulnerabilities through GitHub private vulnerability reporting when
available. Do not disclose exploit details or sensitive material in a public issue.

Safe Merge Gate is an offline decision and local-state transaction tool. It does not
authenticate snapshot producers. Consumers must obtain snapshots from a trusted
source and externally sign or anchor evidence when authenticity is required. The
tool stores secret fingerprints and counts, never raw secret values.

The local transaction refuses divergent state and rollback refuses post-apply
changes. Protect evidence, receipt, and state files with filesystem permissions.

