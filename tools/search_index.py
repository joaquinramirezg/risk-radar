#!/usr/bin/env python3
"""Build the full-text search file the site loads when someone searches.

  python3 tools/search_index.py      # reads site/data/*.json, writes site/data/search.json

One row per risk factor: this year's text, the character spans that were
added this year, and the passages that were cut. That is enough for the page
to answer three questions with exact quotes and no server: which risk factors
mention a phrase, which added it this year, and which dropped it.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "site" / "data"


def row(ticker: str, r: dict) -> dict:
    out: dict = {"t": ticker, "i": r["id"], "s": r["status"], "h": r["title"]}
    if r.get("change"):
        out["c"] = r["change"]["label"]
    if "diff" in r:
        text, added, cut = "", [], []
        for op, t in r["diff"]:
            if op == "-":
                if t.strip():
                    cut.append(t.strip())
                continue
            if op == "+":
                added.append([len(text), len(text) + len(t)])
            text += t
        out["x"] = text
        if added:
            out["a"] = added
        if cut:
            out["d"] = cut
        return out
    body = r.get("body", "")
    if r["status"] in ("removed", "merged"):
        out["x"], out["d"] = "", [body]
    else:
        out["x"] = body
        if r["status"] in ("new", "split"):
            out["a"] = [[0, len(body)]]
    return out


def main() -> int:
    index = json.loads((DATA / "index.json").read_text())
    rows, names = [], {}
    for c in index["companies"]:
        d = json.loads((DATA / f"{c['ticker']}.json").read_text())
        names[c["ticker"]] = c["company"]
        rows += [row(c["ticker"], r) for r in d["risks"]]
    out = {"companies": names, "risks": rows}
    path = DATA / "search.json"
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(rows)} risks, {path.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
