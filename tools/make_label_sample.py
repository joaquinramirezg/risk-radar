#!/usr/bin/env python3
"""Draw the hand-labelling sample that measures the splitter and the matcher.

  python3 tools/make_label_sample.py      # writes labels/items.json

For a fixed set of companies chosen to cover every filing style, every "new"
and "removed" call is included (they are few and they are the claims the site
makes loudest), plus a seeded random sample of matched pairs. New and removed
items carry last year's (or this year's) three nearest risks, so a missed
match can be named, which gives the matcher's recall as well as its precision.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from harness.risks import split_risk_factors
from harness.yoy import match, signature

COMPANIES = ["AAPL", "JPM", "V", "PFE", "MSFT", "XOM", "TSLA", "JNJ", "NVDA", "KO"]
MATCHED_PER_COMPANY = 26
SEED = 20261115
OPENING = 600


def main() -> int:
    from sentence_transformers import SentenceTransformer

    from harness.neural import DENSE_MODEL

    model = SentenceTransformer(DENSE_MODEL)
    rng = random.Random(SEED)
    items = []
    for tk in COMPANIES:
        new_f = next(Path("data/raw").glob(f"{tk}_*.htm"))
        old_f = next(Path("data/raw_prev").glob(f"{tk}_*.htm"))
        new = split_risk_factors(new_f.read_text(errors="replace"))
        old = split_risk_factors(old_f.read_text(errors="replace"))
        eo = model.encode([signature(r) for r in old], normalize_embeddings=True,
                          show_progress_bar=False)
        en = model.encode([signature(r) for r in new], normalize_embeddings=True,
                          show_progress_bar=False)
        sims = (eo @ en.T).tolist()
        changes = match(old, new, lambda a, b, s=sims: s)

        def view(r):
            return {"title": r.title, "opening": r.text[:OPENING], "chars": len(r.text)}

        matched = [c for c in changes if c.old and c.new]
        for c in rng.sample(matched, min(MATCHED_PER_COMPANY, len(matched))):
            items.append({"kind": "matched", "ticker": tk, "status": c.status,
                          "score": c.match_score, "old": view(c.old), "new": view(c.new)})
        for c in changes:
            if c.status == "new" and c.new:
                j = new.index(c.new)
                near = sorted(range(len(old)), key=lambda i: -sims[i][j])[:3]
                items.append({"kind": "new", "ticker": tk, "status": "new", "new": view(c.new),
                              "candidates": [{**view(old[i]), "score": round(sims[i][j], 3)}
                                             for i in near]})
            if c.status == "removed" and c.old:
                i = old.index(c.old)
                near = sorted(range(len(new)), key=lambda j: -sims[i][j])[:3]
                items.append({"kind": "removed", "ticker": tk, "status": "removed",
                              "old": view(c.old),
                              "candidates": [{**view(new[j]), "score": round(sims[i][j], 3)}
                                             for j in near]})
        print(f"{tk:5} {sum(1 for x in items if x['ticker'] == tk)} items")
    rng.shuffle(items)
    for n, it in enumerate(items, start=1):
        it["id"] = f"i{n:03d}"
    out = Path("labels/items.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"seed": SEED, "companies": COMPANIES, "items": items},
                              ensure_ascii=False))
    print(f"{len(items)} items -> {out}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    raise SystemExit(main())
