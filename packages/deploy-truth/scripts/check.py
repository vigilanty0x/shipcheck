"""Standard-library repository and public-boundary checks."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".py", ".toml", ".json", ".yml", ".yaml", ".txt"}
FORBIDDEN = (
    "BEGIN " + "PRIVATE KEY", "gh" + "p_", "api" + "_key=", "pass" + "word=",
    "/workspace/" + "scratch/",
)


def main() -> int:
    problems: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in {"build", "dist", "__pycache__"} or part.endswith(".egg-info") for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN:
            if marker.casefold() in text.casefold():
                problems.append(f"{path.relative_to(ROOT)}: forbidden public-boundary marker")
        if path.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                problems.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
    for name in (
        "README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "AI_ASSISTANCE.md",
        "CHANGELOG.md", "pyproject.toml", ".github/workflows/ci.yml",
    ):
        if not (ROOT / name).is_file():
            problems.append(f"missing required file: {name}")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("public-boundary and repository checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

