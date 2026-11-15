#!/usr/bin/env python3
"""Classify what each edited or rewritten risk factor actually changed.

  ANTHROPIC_API_KEY=... python3 tools/classify_changes.py        # all companies
  python3 tools/classify_changes.py --only JPM MSFT --limit 20   # a slice
  python3 tools/classify_changes.py --sample --model opus --effort high
                                    # the 80 labelled risks only, another model

A word diff says *that* a risk changed; this says *how*. Every matched risk
whose text moved is sent to a small model with both versions and must come
back as exactly one of:

  new_exposure   a cause, product, market or event that was not there before
  escalated      same exposure, now described as likelier, larger or realised
  de_escalated   same exposure, softened, narrowed or described as resolved
  boilerplate    rewording, reordering, renamed entities, updated dates only

The answer is schema-constrained (structured outputs), so a reply always
parses. Results are appended to reports/change_types.<prompt>[.<model>].jsonl
(the model suffix is left off for the production Haiku run); a rerun skips
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
MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
SAMPLE = ROOT / "labels" / "change_sample.json"

SYSTEM_V1 = """You compare two versions of one risk factor from a company's annual report \
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

# v2, after reading where v1 disagreed on the development half of the labelled
# sample (v1 flagged any added phrase as new and any dropped detail as softer).
SYSTEM_V2 = SYSTEM_V1 + """

Hold every label except boilerplate to a materiality bar: would a careful analyst \
mention this change in a note to a portfolio manager? If not, it is boilerplate.
- Dropping an example, a list item, a statistic or a named regulation, or condensing \
the text, is boilerplate unless the company says the exposure itself shrank or ended.
- Updating figures or dates is boilerplate unless the size of the exposure clearly moved.
- A newly named law, product, market, counterparty or event is new_exposure only if it \
introduces a source of loss that last year's text did not cover in any form; a new \
example of a source already covered is escalated if it shows the risk materialising, \
otherwise boilerplate.
When in doubt between two labels, prefer the less dramatic one."""

PROMPTS = {"v1": SYSTEM_V1, "v2": SYSTEM_V2}


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


def classify(client: anthropic.Anthropic, u: dict, version: str, model: str,
             effort: str) -> dict:
    user = (f"LAST YEAR\nTitle: {u['old_title']}\n\n{u['old']}\n\n"
            f"THIS YEAR\nTitle: {u['title']}\n\n{u['new']}")
    t0 = time.perf_counter()
    extra = {} if effort == "low" else {"thinking": {"type": "adaptive"}}
    resp = client.messages.parse(
        model=model,
        max_tokens=1024 if effort == "low" else 16000,
        system=PROMPTS[version],
        output_config={"effort": effort},
        messages=[{"role": "user", "content": user}],
        output_format=Verdict,
        **extra,
    )
    secs = time.perf_counter() - t0
    row = {k: u[k] for k in ("key", "ticker", "status", "title", "ratio")}
    row.update(model=model, served_by=resp.model, prompt=version, effort=effort,
               seconds=round(secs, 2),
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
    ap.add_argument("--prompt", choices=sorted(PROMPTS), default="v2")
    ap.add_argument("--model", choices=sorted(MODELS), default="haiku")
    ap.add_argument("--effort", choices=["low", "medium", "high"], default="low")
    ap.add_argument("--sample", action="store_true", help="only the labelled sample")
    args = ap.parse_args()
    model = MODELS[args.model]
    tag = "" if (args.model, args.effort) == ("haiku", "low") else f".{args.model}"
    tag += "" if args.effort == "low" else f"-{args.effort}"
    out = ROOT / "reports" / f"change_types.{args.prompt}{tag}.jsonl"

    done = set()
    if out.exists():
        done = {json.loads(line)["key"] for line in out.read_text().splitlines() if line}
    pool_ = json.loads(SAMPLE.read_text()) if args.sample else units(args.only)
    todo = [u for u in pool_ if u["key"] not in done][: args.limit]
    print(f"{len(done)} done, {len(todo)} to classify with {model}", file=sys.stderr)
    client = anthropic.Anthropic(max_retries=4)
    out.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(args.workers) as pool, out.open("a") as f:
        for row in pool.map(
            lambda u: classify(client, u, args.prompt, model, args.effort), todo
        ):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{row['ticker']:5} {row['label']!s:13} {row['title'][:70]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
