#!/usr/bin/env python3
"""Build Risk Radar's data: one JSON per company plus an index, for the static site.

  python3 tools/build_radar.py            # reads data/raw/ and data/raw_prev/
                                          # writes site/data/*.json
  python3 tools/build_radar.py --relabel  # only re-attach classifier verdicts

For each company it splits both years' Item 1A into risk factors, matches them
(neural similarity on title + opening, see harness.yoy) and classifies every
risk as new, split, removed, merged, rewritten, edited or unchanged. Needs the `ladder` extra.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

from harness.risks import split_risk_factors
from harness.yoy import match, word_diff

RAW, PREV, OUT = Path("data/raw"), Path("data/raw_prev"), Path("site/data")

# Themes tracked across every company, as whole-word patterns. Counting phrases
# is crude on purpose: anyone can check it with Ctrl+F in the filing.
THEMES = {
    "Artificial intelligence": (
        r"\bartificial intelligence\b|\bAI\b|\bgenerative\b|\bmachine learning\b"),
    "Tariffs and trade": r"\btariffs?\b|\btrade (war|polic|restriction|barrier)",
    "Cybersecurity": r"\bcyber",
    "China": r"\bChina\b|\bChinese\b",
    "Climate": r"\bclimate\b",
    "Export controls": r"\bexport control",
}


CHANGE_TYPES = Path("reports/change_types.v2.jsonl")
MIN_RISKS = 8  # fewer than this in either year means the splitter misread the layout

# Companies whose 10-K does not carry the risk factors itself, or whose layout
# the splitter cannot read. They are listed on the site rather than shown wrong.
EXCLUDED = {
    "BK": "risk factors are incorporated by reference from the annual report exhibit",
    "USB": "risk factors are incorporated by reference from the annual report exhibit",
    "WFC": "risk factors are incorporated by reference from the annual report exhibit",
    "INTC": "risk titles are marked only by colour and font size, which the splitter ignores",
}


def change_types() -> dict[str, dict[str, str]]:
    """Verdicts from tools/classify_changes.py, keyed like it keys them."""
    if not CHANGE_TYPES.exists():
        return {}
    rows = [json.loads(x) for x in CHANGE_TYPES.read_text().splitlines() if x]
    return {r["key"]: {k: r[k] for k in ("label", "reason", "evidence")}
            for r in rows if r.get("label")}


def manifest(path: Path) -> dict[str, dict[str, str]]:
    with path.open() as f:
        return {r["file"]: r for r in csv.DictReader(f, delimiter="\t")}


def theme_counts(text: str) -> dict[str, int]:
    return {name: len(re.findall(pat, text)) for name, pat in THEMES.items()}


def relabel() -> int:
    """Attach the latest change-type verdicts to already built company files,
    without splitting or matching again."""
    verdicts = change_types()
    for f in sorted(OUT.glob("*.json")):
        if f.name in ("index.json", "findings.json"):
            continue
        doc = json.loads(f.read_text())
        for r in doc["risks"]:
            key = f"{doc['ticker']}|{r['title']}".encode()
            r.setdefault("id", hashlib.sha1(key).hexdigest()[:12])
            if "diff" in r and r["id"] in verdicts:
                r["change"] = verdicts[r["id"]]
        f.write_text(json.dumps(doc, ensure_ascii=False))
    return 0


def main() -> int:
    if "--relabel" in sys.argv:
        return relabel()
    from sentence_transformers import SentenceTransformer

    from harness.neural import DENSE_MODEL

    model = SentenceTransformer(DENSE_MODEL)

    def similarity(a: list[str], b: list[str]) -> list[list[float]]:
        ea = model.encode(a, normalize_embeddings=True, show_progress_bar=False)
        eb = model.encode(b, normalize_embeddings=True, show_progress_bar=False)
        return (ea @ eb.T).tolist()

    verdicts = change_types()
    cur_m, prev_m = manifest(RAW / "MANIFEST.tsv"), manifest(PREV / "MANIFEST.tsv")
    OUT.mkdir(parents=True, exist_ok=True)
    index, skipped = [], []
    for new_file in sorted(RAW.glob("*.htm")):
        ticker = new_file.name.split("_")[0]
        old_files = sorted(PREV.glob(f"{ticker}_*.htm"))
        cm = cur_m[new_file.name]

        def skip(reason: str, ticker: str = ticker, company: str = cm["company"]) -> None:
            skipped.append({"ticker": ticker, "company": company, "reason": reason})
            print(f"SKIP {ticker}: {reason}")
            (OUT / f"{ticker}.json").unlink(missing_ok=True)

        if ticker in EXCLUDED:
            skip(EXCLUDED[ticker])
            continue
        if not old_files:
            skip("no prior-year 10-K")
            continue
        pm = prev_m[old_files[0].name]
        try:
            new = split_risk_factors(new_file.read_text(errors="replace"))
            old = split_risk_factors(old_files[0].read_text(errors="replace"))
        except ValueError as e:
            skip(str(e))
            continue
        if min(len(new), len(old)) < MIN_RISKS:
            skip(f"only {min(len(new), len(old))} risk factors found; layout not understood")
            continue
        changes = match(old, new, similarity)

        risks = []
        for c in changes:
            r = c.old if c.status == "merged" else (c.new or c.old)
            assert r is not None
            key = hashlib.sha1(f"{ticker}|{r.title}".encode()).hexdigest()[:12]
            item: dict[str, object] = {
                "id": key, "status": c.status, "category": r.category, "title": r.title,
                "match": c.match_score, "ratio": c.text_ratio,
            }
            if c.status in ("edited", "rewritten") and c.old and c.new:
                item["old_title"] = c.old.title
                item["diff"] = word_diff(c.old.text, c.new.text)
                if key in verdicts:
                    item["change"] = verdicts[key]
            else:
                item["body"] = r.text
            if c.status == "split" and c.old:
                item["link_title"], item["reuse"] = c.old.title, c.reuse
            if c.status == "merged" and c.new:
                item["link_title"], item["reuse"] = c.new.title, c.reuse
            risks.append(item)

        counts = {s: sum(1 for c in changes if c.status == s)
                  for s in ("new", "split", "removed", "merged", "rewritten", "edited",
                            "unchanged")}
        new_text = "\n".join(f"{r.title}\n{r.text}" for r in new)
        old_text = "\n".join(f"{r.title}\n{r.text}" for r in old)
        doc = {
            "ticker": ticker, "company": cm["company"],
            "current": {"period_end": cm["period_end"], "filed": cm["filing_date"],
                        "url": cm["url"], "risks": len(new), "words": len(new_text.split())},
            "previous": {"period_end": pm["period_end"], "filed": pm["filing_date"],
                         "url": pm["url"], "risks": len(old), "words": len(old_text.split())},
            "counts": counts,
            "themes": {"current": theme_counts(new_text), "previous": theme_counts(old_text)},
            "risks": risks,
        }
        (OUT / f"{ticker}.json").write_text(json.dumps(doc, ensure_ascii=False))
        index.append({k: doc[k] for k in ("ticker", "company", "current", "previous",
                                           "counts", "themes")})
        index[-1]["new_titles"] = [c.new.title for c in changes if c.status == "new" and c.new]
        index[-1]["removed_titles"] = [c.old.title for c in changes
                                       if c.status == "removed" and c.old]
        print(f"ok   {ticker:5} {counts}")
    (OUT / "index.json").write_text(json.dumps(
        {"themes": list(THEMES), "companies": index, "skipped": skipped},
        ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    raise SystemExit(main())
