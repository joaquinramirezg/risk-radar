#!/usr/bin/env python3
"""Ablation of the year-over-year matcher against the labelled sample.

  python3 tools/ablate_matcher.py      # needs the `ladder` extra and data/raw*

Varies the similarity model, what text it sees and the match threshold, reruns
the whole pipeline (one-to-one match, then split/merge detection) on the ten
labelled companies, and scores every labelled item:
  matched pair   right if the same old/new pair is matched again
  truly new/rem  right if it stays new/removed
  split/merged   right if linked to the predecessor the labeller picked
Gold labels are labels/ai_labels.json (all 257 items). The sample was drawn
from the default configuration's output, so a configuration that finds pairs
the default missed among unsampled risks gets no credit for them; the default
is favoured, if anything.
"""
from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harness import yoy  # noqa: E402
from harness.risks import RiskFactor, split_risk_factors  # noqa: E402

MODELS = {
    "bge-small": "BAAI/bge-small-en-v1.5",
    "bge-base": "BAAI/bge-base-en-v1.5",
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",
}
VIEWS: dict[str, Callable[[RiskFactor], str]] = {
    "title+600": lambda r: f"{r.title}\n{r.text[:600]}",
    "title": lambda r: r.title,
    "opening-600": lambda r: r.text[:600],
    "title+2000": lambda r: f"{r.title}\n{r.text[:2000]}",
}
THRESHOLDS = [0.70, 0.75, 0.80, 0.85, 0.90]
TFIDF_THRESHOLDS = [0.20, 0.30, 0.40, 0.50, 0.60]


def load_pairs(tickers: Sequence[str]) -> dict[str, tuple[list[RiskFactor], list[RiskFactor]]]:
    out = {}
    for t in tickers:
        new = next((ROOT / "data" / "raw").glob(f"{t}_*.htm"))
        old = next((ROOT / "data" / "raw_prev").glob(f"{t}_*.htm"))
        out[t] = (split_risk_factors(old.read_text(errors="replace")),
                  split_risk_factors(new.read_text(errors="replace")))
    return out


def score(changes: dict[str, list[yoy.Change]], items: list[dict], gold: dict) -> dict:
    right = {"matched": 0, "truly": 0, "linked": 0}
    total = {"matched": 0, "truly": 0, "linked": 0}
    for it in items:
        q1 = gold[it["id"]]["q1"]
        ch = changes[it["ticker"]]
        if it["kind"] == "matched":
            total["matched"] += 1
            ok = any(c.old and c.new and c.status not in ("split", "merged")
                     and c.old.title == it["old"]["title"] and c.new.title == it["new"]["title"]
                     for c in ch)
            right["matched"] += ok and q1 == "same"
            continue
        side = "new" if it["kind"] == "new" else "old"
        title = it[side]["title"]
        c = next(c for c in ch if (c.new if side == "new" else c.old)
                 and (c.new if side == "new" else c.old).title == title  # type: ignore[union-attr]
                 and (side == "old" or c.status != "merged"))
        if q1.startswith("truly"):
            total["truly"] += 1
            right["truly"] += c.status in ("new", "removed")
        else:
            total["linked"] += 1
            want = it["candidates"][int(q1[-1])]["title"]
            other = c.old if side == "new" else c.new
            right["linked"] += (c.status in ("split", "merged", "rewritten", "edited",
                                             "unchanged") and other is not None
                                and other.title == want)
    n = sum(total.values())
    return {"accuracy": round(sum(right.values()) / n, 4),
            **{f"{k}_ok": f"{right[k]}/{total[k]}" for k in total}}


def main() -> int:
    items = json.loads((ROOT / "labels" / "items.json").read_text())["items"]
    gold = json.loads((ROOT / "labels" / "ai_labels.json").read_text())["labels"]
    tickers = sorted({i["ticker"] for i in items})
    data = load_pairs(tickers)
    rows = []

    def run(name: str, view: str, sim_for: Callable[[list[str], list[str]], list[list[float]]],
            thresholds: Sequence[float], secs: float) -> None:
        cache = {t: sim_for([VIEWS[view](r) for r in o], [VIEWS[view](r) for r in n])
                 for t, (o, n) in data.items()}
        for th in thresholds:
            yoy.MATCH_MIN = th
            changes = {}
            for t, (o, n) in data.items():
                s = cache[t]
                changes[t] = yoy.match(o, n, lambda a, b, s=s: s)
            row = {"model": name, "view": view, "threshold": th,
                   "encode_s": round(secs, 1), **score(changes, items, gold)}
            rows.append(row)
            print(json.dumps(row), flush=True)

    from sentence_transformers import SentenceTransformer
    for name, path in MODELS.items():
        model = SentenceTransformer(path)
        for view in VIEWS if name == "bge-small" else ["title+600"]:
            t0 = time.perf_counter()

            def sim(a: list[str], b: list[str], model: SentenceTransformer = model) -> list:
                ea = model.encode(a, normalize_embeddings=True, show_progress_bar=False)
                eb = model.encode(b, normalize_embeddings=True, show_progress_bar=False)
                return (ea @ eb.T).tolist()
            for o, n in data.values():  # time one full pass
                sim([VIEWS[view](r) for r in o], [VIEWS[view](r) for r in n])
            run(name, view, sim, THRESHOLDS, time.perf_counter() - t0)

    from sklearn.feature_extraction.text import TfidfVectorizer

    def tfidf(a: list[str], b: list[str]) -> list:
        v = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2)).fit(a + b)
        return (v.transform(a) @ v.transform(b).T).toarray().tolist()
    run("tfidf", "title+600", tfidf, TFIDF_THRESHOLDS, 0.0)

    yoy.MATCH_MIN = 0.80
    out = ROOT / "reports" / "matcher_ablation.json"
    out.write_text(json.dumps(rows, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
