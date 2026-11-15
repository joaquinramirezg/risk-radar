"""Reciprocal rank fusion: the hybrid rung of the baseline ladder.

Stdlib only. RRF fuses ranked lists without looking at their raw scores, which
matters here because BM25 scores and cosine similarities live on different
scales and any weighted sum of the two is a tuning knob in disguise.
"""
from __future__ import annotations

from collections.abc import Sequence

RRF_K = 60  # the constant from Cormack et al. (2009); not tuned on this set


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], k: int = 10, rrf_k: int = RRF_K
) -> list[str]:
    """Fuse several ranked chunk_id lists into one. Ties break on chunk_id."""
    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive")
    scores: dict[str, float] = {}
    for ranking in rankings:
        if len(set(ranking)) != len(ranking):
            raise ValueError("a ranking lists the same chunk twice")
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
    fused = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [cid for cid, _ in fused[:k]]
