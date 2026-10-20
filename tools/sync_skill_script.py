#!/usr/bin/env python3
"""Keep the skill's bundled script identical to the repository root script.

The converter is maintained as a single self-contained file at the repository
root so it can be run directly, while the Codex skill needs its own copy under
``skills/ovkml2csv/scripts/`` to stay portable when installed on its own. This
tool copies the root file into the skill and can verify that the two copies
have not drifted.

Usage::

    python3 tools/sync_skill_script.py          # copy root -> skill
    python3 tools/sync_skill_script.py --check  # exit 1 when out of sync
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "ovkml2csv.py"
TARGET = REPO_ROOT / "skills" / "ovkml2csv" / "scripts" / "ovkml2csv.py"


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="only verify that the two copies match",
    )
    args = parser.parse_args(argv)

    if not SOURCE.is_file():
        print(f"error: missing source script {SOURCE}", file=sys.stderr)
        return 1

    if args.check:
        if not TARGET.is_file():
            print(f"error: missing skill script {TARGET}", file=sys.stderr)
            return 1
        if SOURCE.read_bytes() != TARGET.read_bytes():
            print(
                "error: skill script is out of sync; "
                "run python3 tools/sync_skill_script.py",
                file=sys.stderr,
            )
            return 1
        print(f"ok: {TARGET.relative_to(REPO_ROOT)} matches {SOURCE.name}")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, TARGET)
    TARGET.chmod(0o755)
    print(f"copied {SOURCE.name} -> {TARGET.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
