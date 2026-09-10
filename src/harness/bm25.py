"""Okapi BM25, implemented directly so the lexical baseline has no dependencies.

This is the floor of the baseline ladder. Every fancier configuration in the
harness has to beat it, reported side by side; without that comparison
"agentic retrieval" is an unfalsifiable claim.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

_TOKEN = re.compile(r"[a-z0-9]+")

# Kept deliberately short. An aggressive stopword list is a tuning knob, and a
# tuned baseline that flatters the headline result is the thing to avoid.
_STOP = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the "
    "this to was were will with".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class BM25:
    def __init__(
        self,
        doc_ids: Sequence[str],
        texts: Sequence[str],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if len(doc_ids) != len(texts):
            raise ValueError("doc_ids and texts must be the same length")
        if not doc_ids:
            raise ValueError("cannot index an empty corpus")
        if len(set(doc_ids)) != len(doc_ids):
            raise ValueError("doc_ids must be unique")
        self.doc_ids = list(doc_ids)
        self.k1 = k1
        self.b = b
        self.tfs: list[Counter[str]] = [Counter(tokenize(t)) for t in texts]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avgdl = sum(self.lens) / len(self.lens)
        df: Counter[str] = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        n = len(self.tfs)
        # Robertson/Sparck-Jones idf with the +0.5 smoothing, floored at zero so
        # a term present in every chunk cannot contribute a negative score.
        self.idf = {
            term: max(0.0, math.log((n - d + 0.5) / (d + 0.5) + 1.0))
            for term, d in df.items()
        }

    def score(self, query: str) -> list[tuple[str, float]]:
        q = tokenize(query)
        out: list[tuple[str, float]] = []
        for i, tf in enumerate(self.tfs):
            dl = self.lens[i] or 1
            s = 0.0
            for term in q:
                f = tf.get(term)
                if not f:
                    continue
                idf = self.idf.get(term, 0.0)
                denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                s += idf * (f * (self.k1 + 1)) / denom
            out.append((self.doc_ids[i], s))
        return out

    def search(self, query: str, k: int = 10) -> list[str]:
        """Top-k chunk_ids. Ties break on chunk_id so runs are reproducible."""
        scored = self.score(query)
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        return [cid for cid, s in scored[:k] if s > 0.0]
