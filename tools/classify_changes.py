#!/usr/bin/env python3
"""Classify what each edited or rewritten risk factor actually changed.

  ANTHROPIC_API_KEY=... python3 tools/classify_changes.py        # all companies
  python3 tools/classify_changes.py --only JPM MSFT --limit 20   # a slice

A word diff says *that* a risk changed; this says *how*. Every matched risk
whose text moved is sent to a small model with both versions and must come
back as exactly one of:

  new_exposure   a cause, product, market or event that was not there before
  escalated      same exposure, now described as likelier, larger or realised
  de_escalated   same exposure, softened, narrowed or described as resolved
  boilerplate    rewording, reordering, renamed entities, updated dates only

The answer is schema-constrained (structured outputs), so a reply always
parses. Results are appended to reports/change_types.jsonl and a rerun skips
risks already done, so an interrupted run resumes for free. Token usage and
latency are recorded per call; tools/score_changes.py turns them into cost
and agreement figures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
OUT = ROOT / "reports" / "change_types.jsonl"
MODEL = "claude-haiku-5-5"
PROMPT_VERSION = "v1"

SYSTEM = """You compare two versions of one risk factor from a company's annual report \
(SEC Form 10-K, Item 1A): last year's and this year's. Decide what kind of change the \
company made, from the investor's point of view.

Labels, pick exactly one:
- new_exposure: this year's text names a cause, product, business line, market, \
counterparty, law or event that last year's text did not cover at all.
- escalated: the same exposure, but now described as more likely, larger, more costly, \
already happening, or with new concrete examples of harm.
- de_escalated: the same exposure, but softened, narrowed, or described as resolved or \
less likely; or a material driver was dropped.
- boilerplate: rewording, reordering, defined-term or entity renames, updated dates or \
cross-references, with no change in substance.

When several apply, pick the one an investor would most want flagged, in this order: \
new_exposure, escalated, de_escalated, boilerplate. Quote the shortest passage that \
shows the change, copied exactly from the text it comes from."""


class Verdict(BaseModel):
    label: Literal["new_exposure", "escalated", "de_escalated", "boilerplate"]
    evidence: str = Field(description="Exact short quote that shows the change")
    reason: str = Field(description="One sentence, at most 30 words")


def units(only: list[str] | None) -> list[dict]:
    out = []
    for f in sorted(DATA.glob("*.json")):
        if f.name == "index.json" or (only and f.stem not in only):
            continue
        doc = json.loads(f.read_text())
        for r in doc["risks"]:
            if r["status"] not in ("edited", "rewritten"):
                continue
            old = "".join(t for op, t in r["diff"] if op != "+")
            new = "".join(t for op, t in r["diff"] if op != "-")
            key = hashlib.sha1(f"{doc['ticker']}|{r['title']}".encode()).hexdigest()[:12]
            out.append({"key": key, "ticker": doc["ticker"], "status": r["status"],
                        "old_title": r.get("old_title", r["title"]), "title": r["title"],
                        "old": old, "new": new, "ratio": r["ratio"]})
    return out


def classify(client: anthropic.Anthropic, u: dict) -> dict:
    user = (f"LAST YEAR\nTitle: {u['old_title']}\n\n{u['old']}\n\n"
            f"THIS YEAR\nTitle: {u['title']}\n\n{u['new']}")
    t0 = time.perf_counter()
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": user}],
        output_format=Verdict,
    )
    secs = time.perf_counter() - t0
    row = {k: u[k] for k in ("key", "ticker", "status", "title", "ratio")}
    row.update(model=MODEL, prompt=PROMPT_VERSION, seconds=round(secs, 2),
               input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens,
               stop_reason=resp.stop_reason)
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        row.update(label=None, evidence="", reason="no verdict")
    else:
        row.update(resp.parsed_output.model_dump())
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    done = set()
    if OUT.exists():
        done = {json.loads(line)["key"] for line in OUT.read_text().splitlines() if line}
    todo = [u for u in units(args.only) if u["key"] not in done][: args.limit]
    print(f"{len(done)} done, {len(todo)} to classify with {MODEL}", file=sys.stderr)
    client = anthropic.Anthropic(max_retries=4)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(args.workers) as pool, OUT.open("a") as f:
        for row in pool.map(lambda u: classify(client, u), todo):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{row['ticker']:5} {row['label']!s:13} {row['title'][:70]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
