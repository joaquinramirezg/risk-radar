"""Loading the corpus and the hand-labelled golden set."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .chunking import Chunk, chunk_document


@dataclass(frozen=True)
class GoldItem:
    qid: str
    question: str
    gold_chunk_ids: tuple[str, ...]   # empty tuple == deliberately unanswerable
    note: str = ""

    @property
    def answerable(self) -> bool:
        return bool(self.gold_chunk_ids)


def load_corpus(
    corpus_dir: Path, target_chars: int = 1200, overlap_chars: int = 150
) -> list[Chunk]:
    files = sorted(Path(corpus_dir).glob("*.txt"))
    if not files:
        raise FileNotFoundError(
            f"no .txt files in {corpus_dir}. Run tools/extract_item1a.py first."
        )
    chunks: list[Chunk] = []
    for f in files:
        chunks.extend(
            chunk_document(f.stem, f.read_text(), target_chars, overlap_chars)
        )
    return chunks


def load_golden(path: Path) -> list[GoldItem]:
    items: list[GoldItem] = []
    seen: set[str] = set()
    for line_no, line in enumerate(Path(path).read_text().splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        d = json.loads(line)
        qid = d["qid"]
        if qid in seen:
            raise ValueError(f"{path}:{line_no}: duplicate qid {qid!r}")
        seen.add(qid)
        items.append(
            GoldItem(
                qid=qid,
                question=d["question"],
                gold_chunk_ids=tuple(d.get("gold_chunk_ids", ())),
                note=d.get("note", ""),
            )
        )
    return items


def validate_golden(items: list[GoldItem], chunks: list[Chunk]) -> list[str]:
    """Return a list of problems. An empty list means the set is usable.

    Catches the two failure modes that would quietly corrupt every number:
    a gold chunk_id that no longer exists after a chunking parameter change,
    and a set with too few unanswerable questions to measure abstention.
    """
    known = {c.chunk_id for c in chunks}
    problems: list[str] = []
    for it in items:
        for cid in it.gold_chunk_ids:
            if cid not in known:
                problems.append(
                    f"{it.qid}: gold chunk {cid} does not exist. Chunking "
                    f"parameters changed since labelling; re-label or revert."
                )
        if not it.question.strip():
            problems.append(f"{it.qid}: empty question")
    n = len(items)
    unans = sum(1 for it in items if not it.answerable)
    if n and unans / n < 0.08:
        problems.append(
            f"only {unans}/{n} questions are unanswerable. Below ~10% the "
            f"abstention rate is not measurable."
        )
    if n < 50:
        problems.append(
            f"golden set has {n} items. Below 50 no claim about a difference "
            f"between configurations is defensible."
        )
    return problems
