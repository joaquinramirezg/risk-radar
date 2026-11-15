#!/usr/bin/env python3
"""Cross-company findings for the front page, each tied to exact sentences.

  python3 tools/findings.py        # reads site/data/*.json, writes site/data/findings.json

A theme "moved" in a company when this year's text adds a sentence on it and
the change is material: the risk is new or split off, or the classifier called
the edit a new exposure or an escalation. Only words that were inserted this
year count, so a theme that was already there and merely reworded does not.
Every example carries the sentence it was found in, copied from the filing.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "src")]
from build_radar import THEMES  # noqa: E402

UP = ("new_exposure", "escalated")


def sentence_at(text: str, pos: int) -> str:
    start = max(text.rfind(". ", 0, pos), text.rfind("\n", 0, pos))
    end = text.find(". ", pos)
    s = text[start + 1 if start >= 0 else 0 : end + 1 if end >= 0 else len(text)].strip()
    return s if len(s) <= 320 else s[:317].rsplit(" ", 1)[0] + "…"


def inserted(r: dict) -> tuple[str, list[tuple[int, int]]]:
    """This year's text and the character spans that were added this year."""
    if "diff" not in r:
        body = r.get("body", "")
        return body, [(0, len(body))] if r["status"] in ("new", "split") else []
    text, spans = "", []
    for op, t in r["diff"]:
        if op == "-":
            continue
        if op == "+":
            spans.append((len(text), len(text) + len(t)))
        text += t
    return text, spans


def removed(r: dict) -> tuple[str, list[tuple[int, int]]]:
    if "diff" not in r:
        return "", []
    text, spans = "", []
    for op, t in r["diff"]:
        if op == "+":
            continue
        if op == "-":
            spans.append((len(text), len(text) + len(t)))
        text += t
    return text, spans


def hit(pattern: str, text: str, spans: list[tuple[int, int]]) -> str | None:
    for m in re.finditer(pattern, text, re.I if pattern.islower() else 0):
        if any(a <= m.start() < b for a, b in spans):
            return sentence_at(text, m.start())
    return None


def main() -> int:
    index = json.loads((DATA / "index.json").read_text())
    docs = [json.loads((DATA / f"{c['ticker']}.json").read_text()) for c in index["companies"]]
    labels: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    themes = []
    for name, pat in THEMES.items():
        up, down = [], []
        for d in docs:
            for r in d["risks"]:
                label = (r.get("change") or {}).get("label")
                material = r["status"] in ("new", "split") or label in UP
                if material:
                    text, spans = inserted(r)
                    s = hit(pat, text, spans)
                    if s:
                        up.append({"ticker": d["ticker"], "company": d["company"], "id": r["id"],
                                   "title": r["title"], "status": r["status"], "label": label,
                                   "sentence": s, "added": sum(b - a for a, b in spans)})
                if r["status"] in ("removed", "merged") or label == "de_escalated":
                    text, spans = removed(r) if "diff" in r else (r["body"], [(0, len(r["body"]))])
                    s = hit(pat, text, spans)
                    if s:
                        down.append({"ticker": d["ticker"], "id": r["id"], "title": r["title"],
                                     "status": r["status"], "label": label, "sentence": s})
        companies = sorted({x["ticker"] for x in up})
        # One example per company, the biggest insertion first, so no company dominates.
        best: dict[str, dict] = {}
        for x in sorted(up, key=lambda x: -x["added"]):
            best.setdefault(x["ticker"], x)
        themes.append({
            "theme": name, "companies_up": len(companies), "risks_up": len(up),
            "companies_down": len({x["ticker"] for x in down}), "risks_down": len(down),
            "tickers_up": companies,
            "examples": sorted(best.values(), key=lambda x: -x["added"])[:8],
            "down_examples": down[:4],
        })
    for d in docs:
        for r in d["risks"]:
            statuses[r["status"]] += 1
            if r.get("change"):
                labels[r["change"]["label"]] += 1
    movers = sorted(
        ({"ticker": d["ticker"], "company": d["company"],
          "up": sum(1 for r in d["risks"] if r["status"] in ("new", "split")
                    or (r.get("change") or {}).get("label") in UP),
          "risks": d["current"]["risks"]} for d in docs),
        key=lambda x: -x["up"])
    out = {
        "companies": len(docs),
        "skipped": index.get("skipped", []),
        "risks_current": sum(d["current"]["risks"] for d in docs),
        "statuses": dict(statuses),
        "change_labels": dict(labels),
        "themes": sorted(themes, key=lambda t: -t["companies_up"]),
        "movers": movers[:10],
    }
    (DATA / "findings.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for t in out["themes"]:
        print(f"{t['theme']:24} up in {t['companies_up']:3} companies ({t['risks_up']} risks), "
              f"down in {t['companies_down']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
