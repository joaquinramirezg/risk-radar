"""Deterministic retrieval metrics. No LLM, no network, no dependencies.

Every number this module produces is checkable by hand, which is the point:
the generation-quality numbers later in the harness rest on an LLM judge, so
the retrieval numbers must not.

Convention throughout: `ranked` is a list of chunk_ids in descending score
order; `relevant` is the set of chunk_ids a human labelled as containing the
answer. Graded relevance is not used - labels are binary, because a
hand-labelled set of this size cannot support reliable graded judgements.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence


def _check(ranked: Sequence[str], k: int) -> None:
    if k <= 0:
        raise ValueError("k must be positive")
    if len(set(ranked)) != len(ranked):
        raise ValueError("ranked list contains duplicate chunk_ids")


def recall_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Fraction of the relevant chunks that appear in the top k.

    Undefined when there are no relevant chunks; callers must exclude
    unanswerable questions from recall, not score them as 0.0.
    """
    rel = set(relevant)
    _check(ranked, k)
    if not rel:
        raise ValueError("recall is undefined with no relevant chunks")
    return len(rel & set(ranked[:k])) / len(rel)


def precision_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Fraction of the top k that are relevant. Denominator is k, not len(ranked),
    so a system that returns fewer than k results is penalised for it."""
    rel = set(relevant)
    _check(ranked, k)
    return len(rel & set(ranked[:k])) / k


def reciprocal_rank(ranked: Sequence[str], relevant: Iterable[str]) -> float:
    """1/rank of the first relevant chunk, or 0.0 if none is retrieved."""
    rel = set(relevant)
    for i, cid in enumerate(ranked, start=1):
        if cid in rel:
            return 1.0 / i
    return 0.0


def dcg_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    rel = set(relevant)
    _check(ranked, k)
    return sum(
        1.0 / math.log2(i + 1)
        for i, cid in enumerate(ranked[:k], start=1)
        if cid in rel
    )


def ndcg_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Binary-relevance nDCG. Ideal ranking puts min(k, |relevant|) hits first."""
    rel = set(relevant)
    _check(ranked, k)
    if not rel:
        raise ValueError("ndcg is undefined with no relevant chunks")
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(k, len(rel)) + 1))
    return dcg_at_k(ranked, rel, k) / ideal


def mean(values: Iterable[float]) -> float:
    vals = list(values)
    if not vals:
        raise ValueError("mean of an empty sequence")
    return sum(vals) / len(vals)


def bootstrap_ci(
    values: Sequence[float],
    confidence: float = 0.95,
    iterations: int = 10_000,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean.

    Used instead of a normal-approximation interval because this harness runs
    at n well under 100, where the Central Limit Theorem is not a safe
    assumption and a textbook interval understates the uncertainty.
    """
    import random

    if not values:
        raise ValueError("cannot bootstrap an empty sequence")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be in (0, 1)")
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iterations):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = means[int((1 - confidence) / 2 * iterations)]
    hi = means[min(iterations - 1, int((1 + confidence) / 2 * iterations))]
    return lo, hi
