#!/usr/bin/env python3
"""Slice the Item 1A "Risk Factors" section out of a 10-K primary document.

Usage:  python3 tools/extract_item1a.py data/raw/*.htm
Writes: data/corpus/<doc_id>.txt

Stdlib only. Prints a per-file report and REFUSES to write a suspiciously
short extract, because a silently truncated corpus would make every metric
downstream meaningless while still looking healthy.
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

MIN_CHARS = 4_000          # a real risk-factors section is far longer
SKIP_TAGS = {"script", "style", "head"}


class Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag in ("p", "div", "br", "tr", "table", "li", "h1", "h2", "h3", "h4"):
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


# The table of contents also contains "Item 1A." and "Item 1B.", so anchoring
# on the first occurrence lands in the TOC and yields a 200-character extract.
# Take the LAST plausible start and the first end that follows it.
_START = re.compile(r"item\s*1a\.?\s*[-–—:]?\s*risk\s*factors", re.I)
_END = re.compile(
    r"item\s*1b\.?\s*[-–—:]?\s*unresolved\s+staff\s+comments"
    r"|item\s*2\.?\s*[-–—:]?\s*propert",
    re.I,
)


def extract(raw_html: str) -> tuple[str, str]:
    p = Text()
    p.feed(raw_html)
    text = re.sub(r"[ \t\xa0]+", " ", p.text())
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    starts = list(_START.finditer(text))
    if not starts:
        return "", "no 'Item 1A Risk Factors' heading found"
    # Prefer the last start that leaves a long enough body: the TOC entry is
    # early and immediately followed by another Item, the real one is not.
    best, reason = "", "all candidate sections were too short"
    for m in starts:
        tail = text[m.end():]
        e = _END.search(tail)
        body = (tail[: e.start()] if e else tail).strip()
        if len(body) > len(best):
            best = body
    if len(best) < MIN_CHARS:
        return "", f"{reason} (longest was {len(best)} chars)"
    return best, ""


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    out_dir = Path("data/corpus")
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for arg in argv:
        path = Path(arg)
        body, err = extract(path.read_text(errors="replace"))
        if err:
            print(f"SKIP  {path.name}: {err}")
            failures += 1
            continue
        dest = out_dir / (path.stem + ".txt")
        dest.write_text(body)
        print(f"ok    {path.name} -> {dest}  {len(body):,} chars")
    if failures:
        print(f"\n{failures} file(s) produced no usable extract. Inspect them by hand;")
        print("do NOT lower MIN_CHARS to make them pass.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
