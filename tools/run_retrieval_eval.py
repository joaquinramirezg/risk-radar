#!/usr/bin/env python3
"""Run the deterministic retrieval eval and write results/retrieval.json.

  python3 tools/run_retrieval_eval.py            # run and write results
  python3 tools/run_retrieval_eval.py --check    # fail if results moved

No LLM, no network, no API key. This is the half of the harness whose numbers
a reviewer can verify by hand, so it must stay that way.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness.bm25 import BM25
from harness.corpus import load_corpus, load_golden, validate_golden
from harness.ir_metrics import (
    bootstrap_ci,
    mean,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

KS = (1, 3, 5, 10)
OUT = Path("results/retrieval.json")


def evaluate(chunks, golden, retrieve) -> dict:
    answerable = [g for g in golden if g.answerable]
    if not answerable:
        raise ValueError("no answerable questions in the golden set")

    per_q: dict[str, dict] = {}
    for g in answerable:
        ranked = retrieve(g.question, max(KS))
        row = {"reciprocal_rank": reciprocal_rank(ranked, g.gold_chunk_ids)}
        for k in KS:
            row[f"recall@{k}"] = recall_at_k(ranked, g.gold_chunk_ids, k)
            row[f"precision@{k}"] = precision_at_k(ranked, g.gold_chunk_ids, k)
            row[f"ndcg@{k}"] = ndcg_at_k(ranked, g.gold_chunk_ids, k)
        per_q[g.qid] = row

    metrics = {}
    for name in next(iter(per_q.values())):
        vals = [per_q[q][name] for q in per_q]
        lo, hi = bootstrap_ci(vals)
        metrics[name] = {
            "mean": round(mean(vals), 4),
            "ci95_low": round(lo, 4),
            "ci95_high": round(hi, 4),
        }

    # Abstention is measured separately: a retriever that returns nothing for
    # an unanswerable question is behaving correctly, and folding those into
    # recall would misreport both numbers.
    unanswerable = [g for g in golden if not g.answerable]
    abstain = {
        "n_unanswerable": len(unanswerable),
        "returned_nothing": sum(
            1 for g in unanswerable if not retrieve(g.question, max(KS))
        ),
    }
    return {
        "n_answerable": len(answerable),
        "n_unanswerable": len(unanswerable),
        "metrics": metrics,
        "abstention": abstain,
        "per_question": per_q,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="compare against committed results and fail on drift")
    ap.add_argument("--corpus", default="data/corpus")
    ap.add_argument("--golden", default="data/golden/golden.jsonl")
    ap.add_argument("--allow-small", action="store_true",
                    help="run anyway on an undersized golden set (dev loop only; "
                         "the warning is written into the results file)")
    args = ap.parse_args()

    chunks = load_corpus(Path(args.corpus))
    golden = load_golden(Path(args.golden))
    problems = validate_golden(golden, chunks)
    if problems and not args.allow_small:
        print("golden set is not usable yet:")
        for p in problems:
            print("  -", p)
        print("\nPass --allow-small to run anyway while still labelling.")
        return 1
    if problems:
        print("WARNING: running on an incomplete golden set. Numbers are not citable.")
        for p in problems:
            print("  -", p)

    index = BM25([c.chunk_id for c in chunks], [f"{c.heading}\n{c.text}" for c in chunks])
    report = {
        "golden_set_warnings": problems,
        "corpus": {"documents": len({c.doc_id for c in chunks}), "chunks": len(chunks)},
        "configs": {"bm25": evaluate(chunks, golden, index.search)},
    }

    if args.check:
        if not OUT.exists():
            print(f"{OUT} is missing; run without --check first.")
            return 1
        old = json.loads(OUT.read_text())
        if old.get("configs") != report["configs"]:
            print("FAIL: retrieval numbers no longer reproduce the committed results.")
            return 1
        print("ok: committed retrieval results reproduce exactly.")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    m = report["configs"]["bm25"]["metrics"]
    print(f"corpus: {report['corpus']['documents']} docs, {report['corpus']['chunks']} chunks")
    for k in KS:
        r = m[f"recall@{k}"]
        print(
            f"  recall@{k:<2} {r['mean']:.3f}  "
            f"95% CI [{r['ci95_low']:.3f}, {r['ci95_high']:.3f}]"
        )
    print(f"  MRR      {m['reciprocal_rank']['mean']:.3f}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
