#!/usr/bin/env python3
"""Read Part II, Item 1A of every downloaded 10-Q and say whether it adds anything.

  python3 tools/extract_10q.py

Each 10-Q is tagged:
  updated         has risk-factor sentences that are not in the 10-K it follows
  no_change       says there are no material changes to the 10-K's risk factors
  reference_only  points back to the 10-K and adds nothing (or the section is empty)

"Not in the 10-K" is an exact match after normalising case, spacing and quotes,
so a company that reprints all its risk factors every quarter is only
"updated" by the sentences it actually changed. The new sentences are kept, and
matched against the eight forecast themes with the same patterns as the 10-Ks.

Writes data/q_risk.json and prints the count of companies with updated text.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter

from extract_item1a import Text
from forecast_common import Q_RISK, RAW_10Q, company_doc, index, mentions

UPDATED_CHARS = 400  # this much genuinely new risk text, at least, to count as an update
_START = re.compile(r"(?m)^[ \t]*item\s*1a\.?\s*[-–—:.]?\s*risk\s*factors", re.I)
_END = re.compile(
    r"(?m)^[ \t]*item\s*(2|3|4|5|6)\.?\s*[-–—:.]?\s*"
    r"(unregistered|defaults|mine|other\s+information|exhibits|issuer|purchases|market)",
    re.I,
)
_NO_CHANGE = re.compile(
    r"no\s+material\s+changes?|not\s+materially\s+changed|"
    r"no\s+significant\s+changes?|have\s+not\s+(been\s+)?(materially\s+)?changed",
    re.I,
)
_BOILER = re.compile(
    r"form 10-k|annual report|quarterly report|forward-looking|"
    r"should carefully consider|risk factors (set forth|described|disclosed|discussed)",
    re.I,
)
_SPLIT = re.compile(r"(?<=[.?!])\s+(?=[A-Z0-9“\"(])")


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("“", '"').replace("”", '"').replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def sentences(text: str) -> list[str]:
    return [
        s.strip()
        for p in re.split(r"\n\s*\n", text)
        for s in _SPLIT.split(p.replace("\n", " "))
        if s.strip()
    ]


def section(raw_html: str) -> str:
    """The longest Item 1A body closed by a later Part II item; '' if none."""
    p = Text()
    p.feed(raw_html)
    text = re.sub(r"[ \t\xa0]+", " ", p.text())
    text = re.sub(r"\n{3,}", "\n\n", text)
    best = ""
    for m in _START.finditer(text):
        tail = text[m.end() :]
        e = _END.search(tail)
        body = (tail[: e.start()] if e else "").strip()
        if len(body) > len(best):
            best = body
    return best


def filing_text(doc: dict, which: str) -> str:
    """One year's Item 1A rebuilt from a company page file: 'current' or 'previous'."""
    parts = []
    for r in doc["risks"]:
        only_prev = r["status"] in ("removed", "merged")
        if (
            which == "current"
            and only_prev
            or which == "previous"
            and r["status"] in ("new", "split")
        ):
            continue
        if "diff" in r:
            keep = "+" if which == "current" else "-"
            body = "".join(t for op, t in r["diff"] if op in ("=", keep))
            title = r["title"] if which == "current" else r.get("old_title", r["title"])
        else:
            body, title = r.get("body", ""), r["title"]
        parts.append(f"{title}\n{body}")
    return "\n".join(parts)


def tag(q_text: str, k_sentences: set[str]) -> tuple[str, list[str]]:
    new = [
        s
        for s in sentences(q_text)
        if len(s) >= 40 and norm(s) not in k_sentences and not _BOILER.search(s)
    ]
    if sum(len(s) for s in new) >= UPDATED_CHARS:
        return "updated", new
    if _NO_CHANGE.search(q_text):
        return "no_change", []
    return "reference_only", []


def main() -> int:
    rows = list(csv.DictReader((RAW_10Q / "MANIFEST.tsv").open(), delimiter="\t"))
    out: dict[str, dict] = {}
    k_cache: dict[tuple[str, str], set[str]] = {}
    for c in index()["companies"]:
        t = c["ticker"]
        doc = company_doc(t)
        out[t] = {}
        for window in ("back", "next"):
            # The 10-Qs in the back window follow the previous 10-K; those in the next window, the latest.
            which = "previous" if window == "back" else "current"
            if (t, which) not in k_cache:
                k_cache[(t, which)] = {norm(s) for s in sentences(filing_text(doc, which))}
            filings, new_all = [], []
            for r in sorted(
                (r for r in rows if r["ticker"] == t and r["window"] == window),
                key=lambda r: r["filing_date"],
            ):
                body = section((RAW_10Q / r["file"]).read_text(errors="replace"))
                verdict, new = tag(body, k_cache[(t, which)])
                seen = {norm(s) for s in new_all}
                new_all += [s for s in new if norm(s) not in seen]
                filings.append(
                    {
                        "accession": r["accession"],
                        "date": r["filing_date"],
                        "tag": verdict,
                        "chars": len(body),
                        "new_chars": sum(len(s) for s in new),
                    }
                )
            hits = mentions("\n".join(new_all))
            out[t][window] = {
                "filings": filings,
                "updated": any(f["tag"] == "updated" for f in filings),
                "themes": sorted(k for k, v in hits.items() if v),
                "new_sentences": new_all[:60],
            }
    Q_RISK.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for window in ("back", "next"):
        tags = Counter(f["tag"] for v in out.values() for f in v[window]["filings"])
        upd = sorted(t for t, v in out.items() if v[window]["updated"])
        none = sorted(t for t, v in out.items() if not v[window]["filings"])
        print(f"{window}: {sum(tags.values())} 10-Qs {dict(tags)}")
        print(f"  companies with updated risk factors: {len(upd)} of {len(out)}  {' '.join(upd)}")
        print(f"  companies with no 10-Q: {len(none)}  {' '.join(none)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
