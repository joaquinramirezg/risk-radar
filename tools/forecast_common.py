"""Shared pieces of the v3 forecast: themes, labels, sectors, paths.

The forecast question, for each company and theme: will the next 10-K add or
escalate risk language on this theme? "Added or escalated" means exactly what
the v2 findings page counts (tools/findings.py): a new or split risk factor, or
an edit the change classifier tagged new_exposure or escalated, whose added
text matches the theme's pattern.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SITE = ROOT / "site" / "data"
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "src")]

from build_radar import THEMES  # noqa: E402
from findings import UP, hit, inserted  # noqa: E402

# Two themes added for the forecast (chosen Nov 17 2026). The six v2 themes keep
# their patterns unchanged, so their labels match the findings page exactly.
EXTRA_THEMES = {
    "Interest rates and credit": (
        r"\binterest rates?\b|\bborrowing costs?\b|\bcredit (spreads?|markets?|ratings?)\b"
    ),
    "Government shutdown and spending": (
        r"\bgovernment shutdowns?\b|\bshutdowns? of the (u\.s\. |federal )?government\b"
        r"|\bdebt ceiling\b|\bgovernment spending\b|\bfederal (budget|spending|funding)\b"
        r"|\bappropriations?\b|\bcontinuing resolutions?\b"
    ),
}
FORECAST_THEMES: dict[str, str] = {**THEMES, **EXTRA_THEMES}

# Raw downloads (gitignored, like data/raw): 10-Qs per window, and the 10-K
# before data/raw_prev for the backtest's "last year" feature.
RAW_10Q = DATA / "raw_10q"
RAW_PREV2 = DATA / "raw_prev2"
SUBMISSIONS = DATA / "edgar"
# Committed outputs.
EVENTS = DATA / "events.json"
Q_RISK = DATA / "q_risk.json"
COUNTS = DATA / "theme_counts.json"
FEATURES = DATA / "forecast_features.json"
BACKTEST = ROOT / "reports" / "forecast_backtest.json"
FORECAST = SITE / "forecast.json"
SCORE = SITE / "forecast_score.json"

# The two windows. "back": signals between the previous 10-K and the latest one,
# outcome = what the latest 10-K added (known). "next": signals since the latest
# 10-K, outcome = what the next 10-K adds (unknown until it is filed).
WINDOWS = ("back", "next")


def theme_counts(text: str) -> dict[str, int]:
    return {
        name: len(re.findall(pat, text, re.I if pat.islower() else 0))
        for name, pat in FORECAST_THEMES.items()
    }


def mentions(text: str) -> dict[str, bool]:
    return {k: v > 0 for k, v in theme_counts(text).items()}


def index() -> dict:
    out: dict = json.loads((SITE / "index.json").read_text())
    return out


def company_doc(ticker: str) -> dict:
    out: dict = json.loads((SITE / f"{ticker}.json").read_text())
    return out


def up_themes(doc: dict) -> set[str]:
    """Themes this company's latest 10-K added or escalated, by findings.py's rule."""
    found = set()
    for r in doc["risks"]:
        label = (r.get("change") or {}).get("label")
        if not (r["status"] in ("new", "split") or label in UP):
            continue
        text, spans = inserted(r)
        for name, pat in FORECAST_THEMES.items():
            if name not in found and hit(pat, text, spans):
                found.add(name)
    return found


def labels() -> dict[str, dict[str, int]]:
    """{ticker: {theme: 0/1}} for the latest 10-K against the one before."""
    out = {}
    for c in index()["companies"]:
        ups = up_themes(company_doc(c["ticker"]))
        out[c["ticker"]] = {t: int(t in ups) for t in FORECAST_THEMES}
    return out


def sector(sic: str | int | None) -> str:
    """A coarse sector from the SIC code EDGAR files under: few enough groups
    that each has several companies, so a sector share means something."""
    try:
        s = int(sic or 0)
    except ValueError:
        return "Other"
    if 2830 <= s <= 2836 or 3840 <= s <= 3851 or 8000 <= s <= 8099 or s == 5912 or s == 6324:
        return "Health"
    if 3570 <= s <= 3579 or 3660 <= s <= 3679 or 7370 <= s <= 7379 or s == 3825:
        return "Technology"
    if 6000 <= s <= 6799:
        return "Finance"
    if 1000 <= s <= 1499 or 2900 <= s <= 2999 or 4900 <= s <= 4999:
        return "Energy and utilities"
    if 4800 <= s <= 4899 or 7800 <= s <= 7899:
        return "Media and telecom"
    if 5000 <= s <= 5999 or 5800 <= s <= 5899 or 2000 <= s <= 2199 or 2800 <= s <= 2899:
        return "Consumer"
    if 3000 <= s <= 3999 or 4000 <= s <= 4799:
        return "Industrials"
    return "Other"
