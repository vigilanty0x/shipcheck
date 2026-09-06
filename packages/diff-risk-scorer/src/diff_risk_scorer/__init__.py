"""Explainable, bounded scoring for declared diff metadata."""

import argparse
import hashlib
import json
from pathlib import PurePosixPath

MAX_FILES = 1_000
MAX_LINES_PER_FILE = 1_000_000
MAX_TOTAL_LINES = 10_000_000


def _safe_path(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 512 or "\\" in value
            or any(ord(char) < 32 for char in value)):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and value not in {".", ".."} and ".." not in path.parts and path.as_posix() == value


def score(files):
    if not isinstance(files, list) or len(files) > MAX_FILES:
        return {"ok": False, "errors": ["file_bound"]}
    total, total_lines, reasons, paths = 0, 0, [], set()
    for item in files:
        if (not isinstance(item, dict) or not {"path", "additions", "deletions"} <= set(item)
                or not set(item) <= {"path", "additions", "deletions", "sensitive", "binary"}
                or not _safe_path(item.get("path")) or item["path"] in paths):
            return {"ok": False, "errors": ["invalid_path_or_entry"]}
        paths.add(item["path"])
        additions, deletions = item["additions"], item["deletions"]
        if (not isinstance(additions, int) or isinstance(additions, bool)
                or not isinstance(deletions, int) or isinstance(deletions, bool)
                or not 0 <= additions <= MAX_LINES_PER_FILE
                or not 0 <= deletions <= MAX_LINES_PER_FILE):
            return {"ok": False, "errors": ["invalid_lines"]}
        sensitive, binary = item.get("sensitive", False), item.get("binary", False)
        if not isinstance(sensitive, bool) or not isinstance(binary, bool):
            return {"ok": False, "errors": ["invalid_flags"]}
        total_lines += additions + deletions
        if total_lines > MAX_TOTAL_LINES:
            return {"ok": False, "errors": ["global_line_bound"]}
        points = min(30, (additions + deletions) // 20)
        if sensitive:
            points += 30
            reasons.append({"path": item["path"], "reason": "sensitive", "points": 30})
        if binary:
            points += 15
            reasons.append({"path": item["path"], "reason": "binary", "points": 15})
        if item["path"].startswith(("tests/", "test/")):
            points = max(0, points - 5)
        total += points
    total = min(100, total)
    band = "critical" if total >= 75 else "high" if total >= 50 else "medium" if total >= 20 else "low"
    body = {"score": total, "band": band, "reasons": reasons, "files": len(files),
            "total_lines": total_lines}
    return {"ok": True, **body,
            "evidence_sha256": hashlib.sha256(json.dumps(body, sort_keys=True,
                                                           separators=(",", ":")).encode()).hexdigest()}


def probe():
    good = score([{"path": "src/a.py", "additions": 10, "deletions": 0}])
    bad = score([{"path": "../x", "additions": 1, "deletions": 0}])
    return {"ok": good["ok"] and not bad["ok"], "path_counter_proof": not bad["ok"]}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("score", "probe"))
    parser.add_argument("--input")
    args = parser.parse_args(argv)
    try:
        data = json.load(open(args.input, encoding="utf-8")) if args.input else {}
        out = probe() if args.command == "probe" else score(data.get("files") if isinstance(data, dict) else None)
    except (OSError, UnicodeError, json.JSONDecodeError):
        out = {"ok": False, "errors": ["input_unreadable"]}
    print(json.dumps(out, sort_keys=True))
    return 0 if out["ok"] else 2
