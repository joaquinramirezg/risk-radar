"""Dense retrieval and cross-encoder reranking: the neural rungs of the ladder.

These need the optional `ladder` extra (sentence-transformers). They are kept
out of the stdlib half on purpose: the BM25 numbers must stay reproducible from
a fresh clone with no install, and these rungs are reported beside them.

Models are small, open and pinned by name so anyone can rerun them on a laptop
CPU with no API key:
  dense:    BAAI/bge-small-en-v1.5 (384-d)
  reranker: cross-encoder/ms-marco-MiniLM-L-6-v2
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
# bge models are trained to see this prefix on queries, not on passages.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _require() -> Any:
    try:
        import sentence_transformers
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "the dense and rerank rungs need the optional extra: "
            "pip install -e '.[ladder]'"
        ) from e
    return sentence_transformers


class DenseIndex:
    def __init__(self, doc_ids: Sequence[str], texts: Sequence[str],
                 model_name: str = DENSE_MODEL) -> None:
        st = _require()
        import numpy as np

        if len(doc_ids) != len(texts):
            raise ValueError("doc_ids and texts must be the same length")
        self._np = np
        self.doc_ids = list(doc_ids)
        self.model = st.SentenceTransformer(model_name)
        self.vecs = self.model.encode(
            list(texts), batch_size=64, normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")

    def search(self, query: str, k: int = 10) -> list[str]:
        q = self.model.encode([QUERY_PREFIX + query], normalize_embeddings=True,
                              show_progress_bar=False)[0]
        sims = self.vecs @ q
        # Stable sort on (-score, chunk_id) so runs are reproducible.
        order = sorted(range(len(sims)), key=lambda i: (-float(sims[i]), self.doc_ids[i]))
        return [self.doc_ids[i] for i in order[:k]]


class Reranker:
    def __init__(self, texts_by_id: dict[str, str], model_name: str = RERANK_MODEL) -> None:
        st = _require()
        self.model = st.CrossEncoder(model_name)
        self.texts = texts_by_id

    def rerank(self, query: str, candidates: Sequence[str], k: int = 10) -> list[str]:
        if not candidates:
            return []
        scores = self.model.predict([(query, self.texts[c]) for c in candidates],
                                    show_progress_bar=False)
        ranked = sorted(zip(candidates, scores, strict=True),
                        key=lambda kv: (-float(kv[1]), kv[0]))
        return [c for c, _ in ranked[:k]]
