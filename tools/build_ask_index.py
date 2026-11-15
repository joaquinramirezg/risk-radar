#!/usr/bin/env python3
"""Build the corpus the "Ask the filings" agent searches.

  python3 tools/build_ask_index.py     # reads site/data/*.json, writes api/_data/corpus.json

One record per risk factor in this year's filing, split into sentences with
stable ids (TICKER.riskid.n), plus last year's text for the risks that have
one. Retrieval works over passages (a heading plus a run of sentences, about
1,000 characters); the agent cites sentences, and the golden set is labelled
at the risk-factor level so a change in passage size never invalidates a label.

Embeddings are added by api/tools/embed.mjs, which uses the same quantized
model the serverless function loads, so offline and online vectors match.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
OUT = ROOT / "api" / "_data" / "corpus.json"
PASSAGE_CHARS = 1000

# Split after . ? ! or ; followed by space and a capital, quote or digit.
# Abbreviations common in 10-Ks are protected first.
ABBREV = re.compile(r"\b(U\.S|U\.K|E\.U|Inc|Corp|Co|Ltd|No|vs|e\.g|i\.e|etc|Mr|Ms|Dr|St|Jr)\.")
SPLIT = re.compile(r"(?<=[.?!])\s+(?=[A-Z0-9“\"(])")


def sentences(text: str) -> list[str]:
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = " ".join(para.split())
        if not para:
            continue
        guarded = ABBREV.sub(lambda m: m.group(0).replace(".", "\x00"), para)
        for s in SPLIT.split(guarded):
            s = s.replace("\x00", ".").strip()
            if s:
                out.append(s)
    return out


def texts(r: dict) -> tuple[str, str]:
    """(this year's text, last year's text) for one risk record."""
    if "diff" in r:
        cur = "".join(t for op, t in r["diff"] if op != "-")
        prev = "".join(t for op, t in r["diff"] if op != "+")
        return cur, prev
    body = r.get("body", "")
    if r["status"] in ("removed", "merged"):
        return "", body
    if r["status"] in ("new", "split"):
        return body, ""
    return body, body  # unchanged


def main() -> int:
    index = json.loads((DATA / "index.json").read_text())
    companies, risks, passages = {}, [], []
    for c in index["companies"]:
        t = c["ticker"]
        d = json.loads((DATA / f"{t}.json").read_text())
        companies[t] = {
            "name": d["company"],
            "current": {k: d["current"][k] for k in ("period_end", "filed", "url")},
            "previous": {k: d["previous"][k] for k in ("period_end", "filed", "url")},
            "counts": d["counts"],
        }
        for r in d["risks"]:
            cur, prev = texts(r)
            rid = f"{t}.{r['id']}"
            sents = sentences(cur)
            rec = {
                "id": rid, "ticker": t, "status": r["status"], "title": r["title"],
                "category": r.get("category", ""),
                "change": (r.get("change") or {}).get("label"),
                "change_reason": (r.get("change") or {}).get("reason"),
                "old_title": r.get("old_title") or (r["title"] if prev else None),
                "link_title": r.get("link_title"),
                "sentences": sents,
                "previous": prev.strip() or None,
            }
            risks.append(rec)
            if not sents:
                continue  # removed or merged: only reachable through compare_years
            start, buf = 0, 0
            for i, s in enumerate(sents):
                buf += len(s) + 1
                last = i == len(sents) - 1
                if buf >= PASSAGE_CHARS or last:
                    passages.append({"id": f"{rid}#{len(passages)}", "risk": rid,
                                     "s0": start, "s1": i + 1})
                    start, buf = i + 1, 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"companies": companies, "risks": risks, "passages": passages},
                              ensure_ascii=False, separators=(",", ":")))
    n_sent = sum(len(r["sentences"]) for r in risks)
    print(f"{len(companies)} companies, {len(risks)} risks, {n_sent} sentences, "
          f"{len(passages)} passages, {OUT.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
