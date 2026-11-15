"""Year-over-year comparison of two lists of risk factors.

Matching is a one-to-one assignment on a similarity matrix: greedy, highest
pair first, so a risk is never matched twice. The similarity function is
injected, so the logic is tested here without any model and the neural
embedding plugs in at the call site.

Each risk in the new filing ends up as exactly one of:
  new        no counterpart last year above MATCH_MIN
  split      no one-to-one counterpart, but carved out of a risk from last year
  rewritten  matched, but the body text changed a lot
  edited     matched, with visible edits
  unchanged  matched, body essentially identical
and each unmatched old risk is "removed", or "merged" when its text was folded
into a risk that is still there.

Splits and merges are found after the one-to-one match, by verbatim reuse: the
share of an unmatched risk's word 5-grams that also appear in a risk on the
other side. Embedding similarity cannot tell "carved out of" from "on a
related topic" (a brand-new AI risk scores 0.94 against an old one that
mentions AI); reused sentences can.
"""
from __future__ import annotations

import difflib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .risks import RiskFactor

MATCH_MIN = 0.80      # cosine on title+opening; below this a pair is not the same risk
UNCHANGED_MIN = 0.98  # body text ratio at or above: unchanged
EDITED_MIN = 0.75     # body text ratio at or above: edited; below: rewritten
SPLIT_MIN = 0.10      # share of 5-grams reused from one risk: split / merged
SHINGLE = 5

Similarity = Callable[[Sequence[str], Sequence[str]], list[list[float]]]


@dataclass
class Change:
    status: str                 # new | split | rewritten | edited | unchanged | removed | merged
    new: RiskFactor | None
    old: RiskFactor | None
    match_score: float = 0.0    # semantic similarity of the matched pair
    text_ratio: float = 0.0     # lexical similarity of the bodies, 0..1
    reuse: float = 0.0          # split / merged: share of 5-grams reused from the linked risk


def signature(r: RiskFactor, chars: int = 600) -> str:
    """What the matcher compares: the title plus the opening of the body."""
    return f"{r.title}\n{r.text[:chars]}"


def _words(s: str) -> list[str]:
    return re.findall(r"\w+|[^\w\s]", s.lower())


def _title_key(t: str) -> str:
    return " ".join(_words(t))


def shingles(text: str, k: int = SHINGLE) -> set[tuple[str, ...]]:
    w = re.findall(r"\w+", text.lower())
    return {tuple(w[i:i + k]) for i in range(len(w) - k + 1)}


def reuse(part: str, whole: str) -> float:
    """Share of `part`'s word 5-grams that also occur in `whole`."""
    sp = shingles(part)
    return len(sp & shingles(whole)) / len(sp) if sp else 0.0


def _best_source(r: RiskFactor, pool: Sequence[RiskFactor]) -> tuple[int, float]:
    scores = [reuse(r.text, p.text) for p in pool]
    if not scores:
        return -1, 0.0
    k = max(range(len(scores)), key=lambda i: scores[i])
    return k, scores[k]


def text_ratio(a: str, b: str) -> float:
    """Word-level similarity, so reflowed whitespace does not count as an edit."""
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, _words(a), _words(b), autojunk=False).ratio()


def match(old: Sequence[RiskFactor], new: Sequence[RiskFactor],
          similarity: Similarity) -> list[Change]:
    sims: list[list[float]] = []
    if old and new:
        sims = similarity([signature(r) for r in old], [signature(r) for r in new])
    # Same title, same risk: a heavily rewritten body must not turn one risk
    # into a false "removed" plus a false "new" (Pfizer's topic headings).
    old_t = [_title_key(r.title) for r in old]
    new_t = [_title_key(r.title) for r in new]
    sims = [[1.0 if old_t[i] == new_t[j] else sims[i][j] for j in range(len(new))]
            for i in range(len(old))]
    pairs = sorted(
        ((sims[i][j], i, j) for i in range(len(old)) for j in range(len(new))),
        key=lambda t: (-t[0], t[1], t[2]),
    )
    used_old: set[int] = set()
    used_new: dict[int, tuple[int, float]] = {}
    for s, i, j in pairs:
        if s < MATCH_MIN:
            break
        if i in used_old or j in used_new:
            continue
        used_old.add(i)
        used_new[j] = (i, s)

    out: list[Change] = []
    for j, r in enumerate(new):
        if j not in used_new:
            k, share = _best_source(r, old)
            if share >= SPLIT_MIN:
                out.append(Change("split", r, old[k], reuse=round(share, 4)))
            else:
                out.append(Change("new", r, None))
            continue
        i, s = used_new[j]
        ratio = text_ratio(old[i].text, r.text)
        status = ("unchanged" if ratio >= UNCHANGED_MIN
                  else "edited" if ratio >= EDITED_MIN else "rewritten")
        out.append(Change(status, r, old[i], round(s, 4), round(ratio, 4)))
    for i, r in enumerate(old):
        if i not in used_old:
            k, share = _best_source(r, new)
            if share >= SPLIT_MIN:
                out.append(Change("merged", new[k], r, reuse=round(share, 4)))
            else:
                out.append(Change("removed", None, r))
    return out


def word_diff(a: str, b: str) -> list[tuple[str, str]]:
    """[(op, text)] with op in {"=", "+", "-"}, for rendering an edited risk."""
    wa, wb = re.findall(r"\S+\s*", a), re.findall(r"\S+\s*", b)
    out: list[tuple[str, str]] = []
    sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.append(("=", "".join(wa[i1:i2])))
        if op in ("delete", "replace"):
            out.append(("-", "".join(wa[i1:i2])))
        if op in ("insert", "replace"):
            out.append(("+", "".join(wb[j1:j2])))
    return out
