"""Smoke an installed Shipcheck wheel in a fresh virtual environment."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        parser.error("wheel must point to an existing .whl file")

    with tempfile.TemporaryDirectory(prefix="shipcheck-wheel-") as tmp:
        env_dir = Path(tmp) / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
        python = env_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        scripts = python.parent
        executable_suffix = ".exe" if sys.platform == "win32" else ""

        run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-index", "--no-deps", str(wheel)])
        run([str(python), "-m", "pip", "check"])
        run([str(python), "-m", "shipcheck", "selftest"])
        run([str(python), "-m", "shipcheck", "probe", "functional"])
        run([str(python), "-m", "safe_merge_gate", "probe", "functional"])
        run([str(scripts / f"shipcheck{executable_suffix}"), "release-gate", "capabilities"])
        run([str(scripts / f"shipcheck-release-gate{executable_suffix}"), "capabilities"])
        run([str(scripts / f"safe-merge-gate{executable_suffix}"), "probe", "functional"])
        run([
            str(python), "-c",
            "import shipcheck, safe_merge_gate; "
            "from shipcheck import merge_gate, release_gate; "
            "assert shipcheck.Decision is safe_merge_gate.Decision; "
            "assert shipcheck.evaluate is safe_merge_gate.evaluate; "
            "assert shipcheck.Decision is not release_gate.Decision; "
            "assert merge_gate.evaluate is safe_merge_gate.evaluate; "
            "assert callable(release_gate.DecisionEngine)",
        ])

    print("installed-wheel-smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
