#!/usr/bin/env python3
"""Score the frozen forecasts against the 10-Ks that have landed since.

  PYTHONPATH=src:tools python3 tools/score_forecast.py

Reads site/data/forecast.json (must be frozen) and data/outcomes.json:

  {"TICKER": {"filed": "2027-02-14", "accession": "...", "up": ["Cybersecurity", ...]}}

one entry per company whose next 10-K has been filed and run through the v2
pipeline (fetch, extract, match, classify, findings), "up" being the themes
that 10-K added or escalated by the findings page's rule.

The rule that makes this a forecast: a company is scored only if the forecast
was frozen BEFORE its 10-K was filed. The freeze time is the time of the git
commit that first recorded status "frozen", which anyone can check; a filing on
or before that day is refused and listed, never scored.

Writes site/data/forecast_score.json: Brier score of the model and of B0 with
intervals (resampling companies), a calibration table, and what is pending.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime

from forecast_baselines import brier, calibration, cluster_ci
from forecast_common import DATA, FORECAST, ROOT, SCORE

OUTCOMES = DATA / "outcomes.json"


def freeze_commit(path=FORECAST) -> tuple[str, datetime] | None:
    """(sha, commit time) of the first commit in which the file says status "frozen"."""
    rel = str(path.relative_to(ROOT))
    log = subprocess.run(
        ["git", "log", "--reverse", "--format=%H %cI", "--", rel],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\n")
    for line in filter(None, log):
        sha, when = line.split()
        body = subprocess.run(
            ["git", "show", f"{sha}:{rel}"], cwd=ROOT, capture_output=True, text=True
        )
        if body.returncode == 0 and json.loads(body.stdout).get("status") == "frozen":
            return sha, datetime.fromisoformat(when)
    return None


def resolve(forecast: dict, outcomes: dict, frozen_at: datetime) -> dict:
    """Pure scoring step, so tests can run it on a small case."""
    rows, refused, pending = [], [], set()
    for f in forecast["forecasts"]:
        o = outcomes.get(f["ticker"])
        if o is None:
            pending.add(f["ticker"])
            continue
        if date.fromisoformat(o["filed"]) <= frozen_at.date():
            refused.append(f["ticker"])
            continue
        rows.append({**f, "y": int(f["theme"] in o["up"])})
    out: dict = {
        "frozen_at": frozen_at.isoformat(),
        "companies_scored": len({r["ticker"] for r in rows}),
        "companies_pending": len(pending),
        "refused": sorted(set(refused)),
        "n": len(rows),
    }
    if rows:
        y = [r["y"] for r in rows]
        p, q = [r["p"] for r in rows], [r["b0"] for r in rows]
        out |= {
            "added": sum(y),
            "model": {
                "brier": round(brier(p, y), 4),
                "brier_ci": [
                    round(v, 4)
                    for v in cluster_ci(
                        rows, lambda ix: brier([p[i] for i in ix], [y[i] for i in ix])
                    )
                ],
            },
            "B0": {
                "brier": round(brier(q, y), 4),
                "brier_ci": [
                    round(v, 4)
                    for v in cluster_ci(
                        rows, lambda ix: brier([q[i] for i in ix], [y[i] for i in ix])
                    )
                ],
            },
            "calibration": calibration(p, y),
            "resolved": [
                {"ticker": r["ticker"], "theme": r["theme"], "p": r["p"], "y": r["y"]} for r in rows
            ],
        }
    return out


def main() -> int:
    forecast = json.loads(FORECAST.read_text())
    if forecast.get("status") != "frozen":
        print(
            "forecast.json is a draft: there is nothing to score until it is frozen and committed."
        )
        return 1
    fc = freeze_commit()
    if fc is None:
        print("forecast.json says frozen but no commit records it; commit it first.")
        return 1
    outcomes = json.loads(OUTCOMES.read_text()) if OUTCOMES.exists() else {}
    out = resolve(forecast, outcomes, fc[1]) | {"freeze_commit": fc[0]}
    SCORE.write_text(json.dumps(out, indent=1))
    print(
        f"scored {out['companies_scored']} companies, {out['companies_pending']} pending, refused {out['refused']}"
    )
    if out.get("model"):
        print(
            f"model Brier {out['model']['brier']} {out['model']['brier_ci']}  B0 {out['B0']['brier']} {out['B0']['brier_ci']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
