#!/usr/bin/env python3
"""CI guard: a frozen forecast is never edited.

  python3 tools/check_forecast.py

If site/data/forecast.json has been committed with status "frozen", the file in
the working tree and in every later commit must be byte-identical to that
commit's version. A draft passes. A new forecast version is a new file.
"""

from __future__ import annotations

import subprocess
import sys

from forecast_common import FORECAST, ROOT
from score_forecast import freeze_commit


def main() -> int:
    if not FORECAST.exists():
        print("no forecast.json yet")
        return 0
    fc = freeze_commit()
    if fc is None:
        print("forecast.json is a draft (not frozen): ok")
        return 0
    sha, when = fc
    rel = str(FORECAST.relative_to(ROOT))
    frozen = subprocess.run(
        ["git", "show", f"{sha}:{rel}"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    later = subprocess.run(
        ["git", "log", "--format=%h %s", f"{sha}..HEAD", "--", rel],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if FORECAST.read_bytes() != frozen or later:
        print(f"FAIL: forecast.json was frozen in {sha[:7]} ({when.date()}) and has changed since.")
        print(later or "(uncommitted change in the working tree)")
        return 1
    print(f"forecast.json unchanged since it was frozen in {sha[:7]} on {when.date()}: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
