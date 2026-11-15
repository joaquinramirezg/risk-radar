"""Split a 10-K's Item 1A into individual risk factors, from the HTML itself.

Plain text loses the one signal that reliably marks a risk factor: its title is
set in bold or italic. So this works on the filing's HTML. Every block (a div,
p, li or table cell) is reduced to its text plus how much of that text is
emphasized. Inside Item 1A an emphasized block is either:

  - a CATEGORY heading ("Risks Related to Our Industry"): short, no closing
    period, or written in capitals, or starting with "Risks related";
  - a risk TITLE: a sentence ("We may be unable to ..."). Its body is every
    plain block until the next emphasized block.

Stdlib only, like the rest of the deterministic half.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

BLOCK_TAGS = {"div", "p", "li", "td", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "br"}
SKIP_TAGS = {"script", "style", "head", "title"}
EMPH_SHARE = 0.9  # share of a block's letters that must be bold/italic to count

_BOLD = re.compile(r"font-weight\s*:\s*(bold|[6-9]00)", re.I)
_ITALIC = re.compile(r"font-style\s*:\s*italic", re.I)
_START = re.compile(r"^\s*item\s*1a\.?\s*[-–—:]?\s*risk\s*factors\.?\s*$", re.I)
_START_A = re.compile(r"^\s*item\s*1a\.?\s*$", re.I)
_START_B = re.compile(r"^\s*risk\s*factors\.?\s*$", re.I)
_PREAMBLE = re.compile(
    r"^\s*(the following|the above|certain factors|you should|in addition to|this section|"
    r"an investment in|our operations and financial results are subject|"
    r"please carefully|for an enterprise|special note regarding forward|"
    r"cautionary statements?|forward-looking statements)", re.I)
_SUMMARY = re.compile(
    r"^\s*(risk factors|(summary of )?risk factors? summary|summary( of)?( risk factors)?)"
    r"\s*:?\s*$", re.I)
_FURNITURE = re.compile(r"^\s*(\d{1,3}|table of contents|page \d+|part i{1,3}\.?)\s*$", re.I)
_END = re.compile(
    r"^\s*item\s*(1b|1c|2)\.?\s*$"  # the item label alone in its own cell
    r"|^\s*item\s*(1b\.?\s*[-–—:]?\s*unresolved|1c\.?\s*[-–—:]?\s*cybersecurity"
    r"|2\.?\s*[-–—:]?\s*propert)",
    re.I,
)
_CATEGORY_HINT = re.compile(
    r"^\s*(risks?\s+(related|relating|associated)\b|general\s+risks?)", re.I)


@dataclass
class Block:
    text: str
    emph_chars: int
    letters: int
    lead: str = ""  # the emphasized run-in prefix, when the block opens with one

    @property
    def emphasized(self) -> bool:
        return self.letters > 0 and self.emph_chars / self.letters >= EMPH_SHARE


@dataclass
class RiskFactor:
    category: str
    title: str
    body: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(self.body)


class _Blocks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self._style: list[tuple[str, bool, bool]] = []  # (tag, bold, italic)
        self._skip = 0
        self._buf: list[str] = []
        self._emph = 0
        self._letters = 0
        self._lead: list[str] = []
        self._lead_open = True

    def _flush(self) -> None:
        text = _norm("".join(self._buf))
        if text:
            self.blocks.append(Block(text, self._emph, self._letters, _norm("".join(self._lead))))
        self._buf, self._emph, self._letters = [], 0, 0
        self._lead, self._lead_open = [], True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self._skip += 1
            return
        if tag in BLOCK_TAGS:
            self._flush()
        style = dict(attrs).get("style") or ""
        parent_b = self._style[-1][1] if self._style else False
        parent_i = self._style[-1][2] if self._style else False
        bold = parent_b or tag in ("b", "strong") or bool(_BOLD.search(style))
        italic = parent_i or tag in ("i", "em") or bool(_ITALIC.search(style))
        if "font-weight" in style and not _BOLD.search(style):
            bold = tag in ("b", "strong")  # an explicit normal weight resets bold
        if tag != "br":
            self._style.append((tag, bold, italic))

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        for i in range(len(self._style) - 1, -1, -1):
            if self._style[i][0] == tag:
                del self._style[i:]
                break
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self._buf.append(data)
        n = sum(ch.isalpha() for ch in data)
        self._letters += n
        emph = bool(self._style and (self._style[-1][1] or self._style[-1][2]))
        if emph:
            self._emph += n
        if self._lead_open:
            if emph:
                self._lead.append(data)
            elif n:  # first plain letter closes the run-in prefix
                self._lead_open = False

    def close(self) -> None:
        super().close()
        self._flush()


def _norm(s: str) -> str:
    return re.sub(r"[\s\xa0\u200b\u202f]+", " ", s).strip()


def html_blocks(raw_html: str) -> list[Block]:
    p = _Blocks()
    p.feed(raw_html)
    p.close()
    return p.blocks


def _item1a_span(blocks: list[Block]) -> tuple[int, int]:
    """Indices [start, end) of the real Item 1A: the longest span from a
    heading-only "Item 1A. Risk Factors" block to the next Item 1B/1C/2 block.
    The table of contents yields a tiny span; cross-references never sit
    alone in a block, so they are not candidates."""
    best = (0, 0)
    for i, b in enumerate(blocks):
        if _START_A.match(b.text) and i + 1 < len(blocks) and _START_B.match(blocks[i + 1].text):
            i += 1
        elif not _START.match(b.text):
            continue
        for j in range(i + 1, len(blocks)):
            if _END.match(blocks[j].text):
                n = sum(len(x.text) for x in blocks[i + 1 : j])
                if n > sum(len(x.text) for x in blocks[best[0] : best[1]]):
                    best = (i + 1, j)
                break
    return best


def is_category(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    caps = bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8
    return caps or bool(_CATEGORY_HINT.match(text)) or (
        len(text) < 90 and not text.rstrip().endswith((".", ":"))
    )


def _run_in(b: Block) -> tuple[str, str] | None:
    """A paragraph that opens with an emphasized sentence ("Our global business
    exposes us to risks. Our customers...") carries its title inline."""
    lead = b.lead.rstrip()
    if len(lead) < 12 or len(lead) >= len(b.text) - 40 or not lead.endswith((".", ":")):
        return None
    return lead, b.text[len(b.lead):].strip() if b.text.startswith(b.lead) else b.text


def split_risk_factors(raw_html: str) -> list[RiskFactor]:
    blocks = html_blocks(raw_html)
    lo, hi = _item1a_span(blocks)
    if hi <= lo:
        raise ValueError("no Item 1A section found")
    # Page headers and footers ("Pfizer Inc.", "Apple Inc. | 2026 Form 10-K | 19")
    # are short lines that repeat across pages. They are not content.
    seen: dict[str, int] = {}
    for b in blocks:
        key = re.sub(r"\d+", "#", b.text)
        seen[key] = seen.get(key, 0) + 1

    def furniture(b: Block) -> bool:
        return bool(_FURNITURE.match(b.text)) or (
            len(b.text) < 80 and seen[re.sub(r"\d+", "#", b.text)] >= 3
        )

    out: list[RiskFactor] = []
    category = ""
    current: RiskFactor | None = None   # the risk the next body block belongs to
    prev_was_title = False
    in_summary = False
    for b in blocks[lo:hi]:
        if furniture(b):
            continue
        if b.emphasized and len(b.text) >= 3:
            if _SUMMARY.match(b.text) or (_PREAMBLE.match(b.text) and is_category(b.text)):
                # A summary list or a boilerplate heading: skip its body.
                in_summary, current, prev_was_title = True, None, False
                continue
            in_summary = False
            if is_category(b.text):
                category, current, prev_was_title = b.text, None, False
            elif _PREAMBLE.match(b.text):
                current, prev_was_title = None, False
            elif prev_was_title and current is not None and not current.body:
                current.title += " " + b.text  # a title split across two blocks
            else:
                current = RiskFactor(category, b.text)
                out.append(current)
                prev_was_title = True
            continue
        prev_was_title = False
        if in_summary:
            continue
        run_in = _run_in(b)
        if run_in and not _PREAMBLE.match(run_in[0]):
            current = RiskFactor(category, run_in[0], [run_in[1]])
            out.append(current)
            continue
        if current is None:
            # Body directly under a heading with no sentence title: the heading
            # IS the risk (Pfizer's "MANAGED CARE TRENDS"). Bullets here are a
            # risk-factors summary, not a risk, so they are dropped.
            if not category or b.text.lstrip().startswith(("•", "·", "●")):
                continue
            current = RiskFactor(category, category)
            out.append(current)
        current.body.append(b.text)
    # A "title" with almost no body is a stray emphasis, not a risk.
    return [r for r in out if sum(len(x) for x in r.body) >= 150]
