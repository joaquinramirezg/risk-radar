"""Chunking for 10-K risk-factor text.

Deliberately dependency-free: the deterministic half of this harness must run
from a fresh clone with no install step, so a reviewer can reproduce the
numbers in the README without a virtualenv.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Iterator

_WS = re.compile(r"[ \t]+")
_PARA = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    chunk_id: str
    heading: str
    text: str
    char_start: int
    char_end: int

    def as_dict(self) -> dict:
        return asdict(self)


def normalize(raw: str) -> str:
    """Collapse runs of spaces and normalize newlines, preserving paragraphs."""
    s = raw.replace("\r\n", "\n").replace("\r", "\n")
    s = _WS.sub(" ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _iter_paragraphs(text: str) -> Iterator[tuple[int, str]]:
    pos = 0
    for part in _PARA.split(text):
        start = text.find(part, pos)
        if start == -1:  # pragma: no cover - defensive
            start = pos
        pos = start + len(part)
        stripped = part.strip()
        if stripped:
            yield start + part.index(stripped[0]), stripped


def is_heading(paragraph: str, max_chars: int = 120) -> bool:
    """A risk-factor heading is a short, single-line label, not a sentence.

    All three conditions are load-bearing. An earlier version matched headings
    by regex position and treated any paragraph under 140 characters as a
    heading, which silently swallowed a 139-character paragraph of real risk
    prose. Content loss in the corpus is the worst possible bug here, because
    every downstream metric would still look fine.
    """
    p = paragraph.strip()
    if not p or "\n" in p:
        return False
    if len(p) > max_chars:
        return False
    if p.endswith("."):
        return False
    # A heading introduces prose; it does not itself contain sentence breaks.
    # Strip a leading item label first, so "Item 1A. Risk Factors" is not
    # rejected for the period in its own item number.
    body = re.sub(r"^Item\s+\d+[A-Za-z]?\.\s*", "", p)
    if re.search(r"\.\s+[A-Z]", body):
        return False
    return p[:1].isupper()


def chunk_document(
    doc_id: str,
    raw: str,
    target_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[Chunk]:
    """Split on paragraph boundaries, packing up to target_chars per chunk.

    Never splits mid-sentence. Carries the most recent heading onto every chunk
    so a chunk retrieved in isolation still says which risk it belongs to;
    without that, a chunk about "this could materially affect our results" is
    unattributable, which is exactly the retrieval failure worth measuring.
    """
    if target_chars <= 0:
        raise ValueError("target_chars must be positive")
    if not 0 <= overlap_chars < target_chars:
        raise ValueError("overlap_chars must be in [0, target_chars)")

    text = normalize(raw)

    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_start: int | None = None
    buf_len = 0
    heading = ""

    def flush(end: int, carry_overlap: bool = True) -> None:
        """Emit the buffer as a chunk.

        carry_overlap=False at a heading boundary. Carrying the tail across a
        heading would produce a chunk whose heading says one risk while its
        opening sentences describe the previous one, which silently corrupts
        every gold label attached to it.
        """
        nonlocal buf, buf_start, buf_len
        if not buf or buf_start is None:
            return
        body = "\n\n".join(buf)
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}::{len(chunks):04d}",
                heading=heading,
                text=body,
                char_start=buf_start,
                char_end=end,
            )
        )
        if carry_overlap and overlap_chars and len(body) > overlap_chars:
            tail = body[-overlap_chars:]
            buf, buf_len, buf_start = [tail], len(tail), end - len(tail)
        else:
            buf, buf_len, buf_start = [], 0, None

    for start, para in _iter_paragraphs(text):
        if is_heading(para):
            flush(start, carry_overlap=False)
            heading = para
            continue
        if buf_len and buf_len + len(para) > target_chars:
            flush(start)
        if buf_start is None:
            buf_start = start
        buf.append(para)
        buf_len += len(para)

    flush(len(text))
    return [c for c in chunks if c.text.strip()]
