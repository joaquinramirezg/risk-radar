#!/usr/bin/env python3
"""One row per company, theme and window: the signals and, for "back", the outcome.

  PYTHONPATH=src:tools python3 tools/forecast_features.py

Signals (all known before the 10-K they predict):
  rose          the theme's mention count went up in the company's last 10-K
                (back: previous 10-K vs the one before; next: latest vs previous)
  level         log(1 + mentions) in that last 10-K
  sector_share  share of the other companies in its sector whose count rose (same window)
  q_theme       a 10-Q since that 10-K has new risk text on the theme
  q_updated     a 10-Q since that 10-K has any new risk text
  k_cyber       an 8-K item 1.05 (cybersecurity incident) since; Cybersecurity theme only
  k_deal        an 8-K item 1.01 (material agreement) or 2.01 (acquisition) since
  k_exec        an 8-K item 5.02 (director or officer change) since
  k_other       8-K item 8.01 (other events) filings since, divided by 5, at most 1

Outcome (back only): did the latest 10-K add or escalate the theme
(forecast_common.labels, the findings page's rule).

Mention counts come from the v2 pipeline's own split of each 10-K
(site/data/index.json) for the six v2 themes; the two forecast-only themes are
counted on the same text rebuilt from the company files; the 10-K before the
previous one is split here with the same reader (build_radar.read_risks).
Writes data/theme_counts.json and data/forecast_features.json.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date

from build_radar import THEMES, read_risks
from extract_10q import filing_text
from forecast_common import (
    COUNTS,
    EVENTS,
    FEATURES,
    FORECAST_THEMES,
    Q_RISK,
    RAW_PREV2,
    company_doc,
    index,
    labels,
    theme_counts,
)

FEATURE_NAMES = (
    "rose",
    "level",
    "sector_share",
    "q_theme",
    "q_updated",
    "k_cyber",
    "k_deal",
    "k_exec",
    "k_other",
)


def counts_by_year() -> dict[str, dict[str, dict[str, int] | None]]:
    """{ticker: {current, previous, prev2: {theme: mentions}}}; prev2 None if unreadable."""
    out: dict[str, dict[str, dict[str, int] | None]] = {}
    events = json.loads(EVENTS.read_text())["companies"]
    for c in index()["companies"]:
        t = c["ticker"]
        doc = company_doc(t)
        row: dict[str, dict[str, int] | None] = {}
        for which in ("current", "previous"):
            extra = theme_counts(filing_text(doc, which))
            row[which] = {
                k: (c["themes"][which][k] if k in THEMES else extra[k]) for k in FORECAST_THEMES
            }
        p2 = events.get(t, {}).get("prev2_10k")
        row["prev2"] = None
        if p2 and (RAW_PREV2 / p2["file"]).exists():
            try:
                risks = read_risks(RAW_PREV2 / p2["file"])
                row["prev2"] = theme_counts("\n".join(f"{r.title}\n{r.text}" for r in risks))
            except ValueError as e:
                print(f"prev2 {t}: {e}")
        out[t] = row
    return out


def build(counts: dict, events: dict, q: dict, y: dict[str, dict[str, int]] | None) -> list[dict]:
    """Pure function of its inputs, so tests can feed it small cases."""
    rows = []
    for window in ("back", "next"):
        # back: the year before = previous vs prev2; next: latest vs previous.
        new_k, old_k = ("previous", "prev2") if window == "back" else ("current", "previous")
        rose: dict[tuple[str, str], int | None] = {}
        for t, c in counts.items():
            for th in FORECAST_THEMES:
                rose[(t, th)] = None if c.get(old_k) is None else int(c[new_k][th] > c[old_k][th])
        for t, c in counts.items():
            ev = events.get(t, {})
            if window == "next" and ev.get("next_10k"):
                continue  # already filed: nothing left to forecast
            sec = ev.get("sector", "Other")
            peers = [
                p for p in counts if p != t and events.get(p, {}).get("sector", "Other") == sec
            ]
            k8 = [i for f in ev.get(window, []) if f["form"] == "8-K" for i in f["items"]]
            qw = q.get(t, {}).get(window, {})
            for th in FORECAST_THEMES:
                r = rose[(t, th)]
                if r is None:
                    continue  # no older 10-K to compare with
                vals = [rose[(p, th)] for p in peers if rose[(p, th)] is not None]
                row = {
                    "ticker": t,
                    "theme": th,
                    "window": window,
                    "sector": sec,
                    "rose": r,
                    "level": round(math.log1p(c[new_k][th]), 4),
                    "sector_share": round(sum(vals) / len(vals), 4) if vals else 0.0,
                    "q_theme": int(th in qw.get("themes", [])),
                    "q_updated": int(bool(qw.get("updated"))),
                    "k_cyber": int(th == "Cybersecurity" and "1.05" in k8),
                    "k_deal": int("1.01" in k8 or "2.01" in k8),
                    "k_exec": int("5.02" in k8),
                    "k_other": min(1.0, k8.count("8.01") / 5),
                    "n_10q": sum(1 for f in ev.get(window, []) if f["form"] == "10-Q"),
                }
                if window == "back" and y is not None:
                    row["y"] = y[t][th]
                rows.append(row)
    return rows


def main() -> int:
    counts = counts_by_year()
    COUNTS.write_text(json.dumps(counts, indent=1))
    events = json.loads(EVENTS.read_text())["companies"]
    q = json.loads(Q_RISK.read_text())
    rows = build(counts, events, q, labels())
    FEATURES.write_text(
        json.dumps(
            {"made": date.today().isoformat(), "features": FEATURE_NAMES, "rows": rows}, indent=0
        )
    )
    for w in ("back", "next"):
        rs = [r for r in rows if r["window"] == w]
        print(
            f"{w}: {len(rs)} rows, {len({r['ticker'] for r in rs})} companies"
            + (f", {sum(r['y'] for r in rs)} positives" if w == "back" else "")
        )
    missing = sorted(t for t, c in counts.items() if c["prev2"] is None)
    print(
        f"no readable 10-K before the previous one (left out of the backtest): {len(missing)} {' '.join(missing)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
