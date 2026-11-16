#!/usr/bin/env python3
"""What faded: themes companies talk about less this year than last.

  python3 tools/faded.py     # reads api/_data/corpus.json, writes site/data/faded.json

Counts mentions of each theme in a company's whole Item 1A this year and last
(last year's text comes from matched, unchanged and removed risks), so it is a
plain word count, not the added-or-expanded test tools/findings.py applies to
rising themes. Each entry keeps one sentence from last year that is gone.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEMES = {
    "ESG": r"\bESG\b|environmental, social(?:,)? and governance",
    "COVID-19": r"covid|pandemic",
}


def main() -> int:
    c = json.loads((ROOT / "api" / "_data" / "corpus.json").read_text())
    out = []
    for name, pat in THEMES.items():
        rx = re.compile(pat, re.I)
        cur: dict[str, int] = {}
        prev: dict[str, int] = {}
        quote: dict[str, str] = {}
        for r in c["risks"]:
            t = r["ticker"]
            cur[t] = cur.get(t, 0) + sum(len(rx.findall(s)) for s in r["sentences"])
            old = r["previous"] or ""
            prev[t] = prev.get(t, 0) + len(rx.findall(old))
            if t not in quote and rx.search(old) and not any(rx.search(s) for s in r["sentences"]):
                hit = next((s for s in re.split(r"(?<=[.?!])\s+", " ".join(old.split())) if rx.search(s)), "")
                if 40 < len(hit) < 320:
                    quote[t] = hit
        had = [t for t in prev if prev[t] > 0]
        gone = sorted(t for t in had if cur[t] == 0)
        down = sorted(t for t in had if cur[t] < prev[t])
        ex = [{"ticker": t, "company": c["companies"][t]["name"], "sentence": quote[t]}
              for t in gone if t in quote][:3]
        out.append({"theme": name, "had": len(had), "gone": len(gone), "down": len(down),
                    "up": sum(1 for t in cur if cur[t] > prev[t]), "tickers_gone": gone, "examples": ex})
        print(f"{name}: {len(had)} used it last year, {len(down)} use it less, {len(gone)} dropped it")
    (ROOT / "site" / "data" / "faded.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
