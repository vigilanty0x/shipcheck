"""Dependency-free syntax and public-boundary checks."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".toml", ".json", ".yml", ".yaml"}
FORBIDDEN = ("sk" + "yom", "private" + "_token", "api" + "_key=", "authorization:" + " bearer")
# Public CC wire identifier only; this does not exempt its line or other text.
PUBLIC_WIRE_SCHEMA = "skyom.business.run.v1"
_WIRE_LITERAL = re.compile(r"(['\"`])" + re.escape(PUBLIC_WIRE_SCHEMA) + r"\1")
_PERSONAL_PATH = re.compile(r"(?:[a-z]:[\\/]+Users[\\/]+|/(?:home|Users)/)", re.IGNORECASE)


def boundary_violations(text: str) -> list[str]:
    checked = _WIRE_LITERAL.sub('', text)
    problems = ['forbidden boundary marker' for marker in FORBIDDEN if marker in checked.lower()]
    if _PERSONAL_PATH.search(checked): problems.append('personal home path')
    return problems


def main() -> int:
    failures: list[str] = []
    inspected = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part in {"dist", "build", "__pycache__"} for part in path.parts):
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name not in {"LICENSE", ".gitignore"}:
            continue
        inspected += 1
        text = path.read_text(encoding="utf-8")
        for problem in boundary_violations(text):
            failures.append(f"{path.relative_to(ROOT)} contains {problem}")
        if path.suffix == ".py":
            try: ast.parse(text, filename=str(path))
            except SyntaxError as exc: failures.append(f"{path.relative_to(ROOT)}: {exc}")
    for required in ("README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "AI_ASSISTANCE.md", "CHANGELOG.md", "pyproject.toml", ".github/workflows/ci.yml"):
        if not (ROOT / required).is_file(): failures.append(f"missing required file: {required}")
    if failures:
        print("\n".join(failures), file=sys.stderr); return 1
    print(f"public-boundary: ok ({inspected} files inspected)"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
