"""Verify imported repository ancestry and exact subtree snapshots."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from typing import NoReturn


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / ".portfolio-rehearsal.json"
SHA = re.compile(r"[0-9a-f]{40}")
PREFIX = re.compile(r"packages/[a-z0-9-]+")
RELEASE_SOURCE = "8d5813d3ec492abefccc704ba16467f894d71863"
RELEASE_REPOSITORY_TREE = "3dcce371575565d698d10fbd549ae3e774ff379c"
RELEASE_PACKAGE_TREE = "f6c15f54f350b5283075f3ee3df26ee7e49ed70c"
RELEASE_IMPORT = "0332482531783984a27878deddc8a19c32e3804b"


def fail(message: str) -> NoReturn:
    raise SystemExit(message)


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode:
        fail(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def require_sha(value: object, field: str) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        fail(f"{field} must be a full lowercase Git SHA")
    return value


def main() -> int:
    try:
        ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read consolidation ledger: {exc}")
    if not isinstance(ledger, dict) or ledger.get("target") != "shipcheck":
        fail("consolidation ledger target must be shipcheck")
    sources = ledger.get("sources")
    if not isinstance(sources, list) or not sources:
        fail("consolidation ledger must contain sources")

    base = require_sha(ledger.get("baseHeadSha"), "baseHeadSha")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=ROOT, check=False
    ).returncode:
        fail(f"base history is not reachable: {base}")

    seen_repositories: set[str] = set()
    seen_prefixes: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            fail(f"sources[{index}] must be an object")
        repository = source.get("repository")
        prefix = source.get("prefix")
        if not isinstance(repository, str) or not repository:
            fail(f"sources[{index}].repository must be non-empty")
        if not isinstance(prefix, str) or PREFIX.fullmatch(prefix) is None:
            fail(f"sources[{index}].prefix is invalid")
        if repository in seen_repositories or prefix in seen_prefixes:
            fail(f"duplicate consolidation source or prefix: {repository}")
        seen_repositories.add(repository)
        seen_prefixes.add(prefix)

        head = require_sha(source.get("headSha"), f"sources[{index}].headSha")
        tree = require_sha(source.get("treeSha"), f"sources[{index}].treeSha")
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", head, "HEAD"],
            cwd=ROOT,
            check=False,
        ).returncode:
            fail(f"{repository}: source history is not reachable")
        if git("rev-parse", f"{head}^{{tree}}") != tree:
            fail(f"{repository}: source commit tree does not match ledger")
        if git("rev-parse", f"HEAD:{prefix}") != tree:
            fail(f"{repository}: imported subtree does not match source tree")

    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", RELEASE_SOURCE, "HEAD"],
        cwd=ROOT,
        check=False,
    ).returncode:
        fail("shipcheck-release-gate source history is not reachable")
    if git("rev-parse", f"{RELEASE_SOURCE}^{{tree}}") != RELEASE_REPOSITORY_TREE:
        fail("shipcheck-release-gate repository tree does not match")
    if git("rev-parse", f"{RELEASE_SOURCE}:src/shipcheck") != RELEASE_PACKAGE_TREE:
        fail("shipcheck-release-gate package tree does not match")
    if (
        git("rev-parse", f"{RELEASE_IMPORT}:src/shipcheck/release_gate")
        != RELEASE_PACKAGE_TREE
    ):
        fail("shipcheck-release-gate import snapshot is not byte-for-byte exact")

    print(
        "consolidation-history: ok "
        f"({len(sources)} imported suites plus release-gate source)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
