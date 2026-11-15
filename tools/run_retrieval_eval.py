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
import time
from collections.abc import Callable
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
POOL = 50     # candidates each first-stage retriever hands to fusion
RERANK_POOL = 30  # fused candidates the cross-encoder rescores

Retriever = Callable[[str, int], list[str]]


def build_ladder(chunks, with_neural: bool) -> dict[str, Retriever]:
    """The baseline ladder, cheapest rung first. Every rung is reported."""
    ids = [c.chunk_id for c in chunks]
    texts = [f"{c.heading}\n{c.text}" for c in chunks]
    bm25 = BM25(ids, texts)
    ladder: dict[str, Retriever] = {"bm25": bm25.search}
    if not with_neural:
        return ladder

    from harness.fusion import reciprocal_rank_fusion
    from harness.neural import DenseIndex, Reranker

    dense = DenseIndex(ids, texts)
    reranker = Reranker(dict(zip(ids, texts, strict=True)))

    def hybrid(q: str, k: int) -> list[str]:
        return reciprocal_rank_fusion([bm25.search(q, POOL), dense.search(q, POOL)], k=k)

    def hybrid_rerank(q: str, k: int) -> list[str]:
        return reranker.rerank(q, hybrid(q, RERANK_POOL), k=k)

    ladder["dense"] = dense.search
    ladder["hybrid_rrf"] = hybrid
    ladder["hybrid_rrf_rerank"] = hybrid_rerank
    return ladder


def time_retriever(golden, retrieve: Retriever) -> dict:
    """Per-query wall clock on this machine. Reported, never gated in CI."""
    ms = []
    for g in golden:
        t0 = time.perf_counter()
        retrieve(g.question, max(KS))
        ms.append((time.perf_counter() - t0) * 1000)
    ms.sort()

    def pct(p: float) -> float:
        return round(ms[min(len(ms) - 1, int(p * len(ms)))], 1)

    return {"n": len(ms), "p50_ms": pct(0.50), "p95_ms": pct(0.95)}


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
    ap.add_argument("--ladder", action="store_true",
                    help="also run dense, hybrid and hybrid+rerank "
                         "(needs the optional 'ladder' extra)")
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

    ladder = build_ladder(chunks, args.ladder)
    report = {
        "golden_set_warnings": problems,
        "corpus": {"documents": len({c.doc_id for c in chunks}), "chunks": len(chunks)},
        "configs": {name: evaluate(chunks, golden, r) for name, r in ladder.items()},
        "latency": {name: time_retriever(golden, r) for name, r in ladder.items()},
    }

    if args.check:
        if not OUT.exists():
            print(f"{OUT} is missing; run without --check first.")
            return 1
        old = json.loads(OUT.read_text())
        # Only the rungs run here are compared, so CI can gate the stdlib BM25
        # numbers without installing the neural extra.
        old_cfg = {k: v for k, v in old.get("configs", {}).items() if k in report["configs"]}
        if old_cfg != report["configs"]:
            print("FAIL: retrieval numbers no longer reproduce the committed results.")
            return 1
        print("ok: committed retrieval results reproduce exactly.")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"corpus: {report['corpus']['documents']} docs, {report['corpus']['chunks']} chunks")
    print(f"{'config':<20}{'recall@5':>10}{'95% CI':>18}{'MRR':>8}{'p50 ms':>9}")
    for name, cfg in report["configs"].items():
        r = cfg["metrics"]["recall@5"]
        ci = f"[{r['ci95_low']:.2f}, {r['ci95_high']:.2f}]"
        mrr = cfg["metrics"]["reciprocal_rank"]["mean"]
        lat = report["latency"][name]["p50_ms"]
        print(f"{name:<20}{r['mean']:>10.3f}{ci:>18}{mrr:>8.3f}{lat:>9.1f}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
