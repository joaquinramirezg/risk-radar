#!/usr/bin/env python3
"""Out-of-sample accuracy check on the companies added when Risk Radar grew
from 20 companies to the S&P 100.

  ANTHROPIC_API_KEY=... python3 tools/audit_scaled.py      # writes reports/audit_scaled.jsonl
  python3 tools/audit_scaled.py --score                    # writes reports/audit_scaled.json

The splitter and matcher were tuned on the first 20 companies, and the first
labelled sample came from ten of them. This draws a fresh sample from the 78
companies nobody looked at while building it and has an independent model
(Claude Opus 5.5, which never saw the pipeline's decisions as anything but the
thing to check) judge three questions:

  pair      a seeded sample of matched risks: is last year's risk the same risk?
  unpaired  every risk called new, removed, split or merged: is that right,
            given the other year's full list of risks?
  boundary  a seeded sample of risks: is this one whole risk factor?

A model judge is not a person; the point is a second, independent reading of
data the pipeline was not tuned on, scored the same way as the first sample.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
OUT = ROOT / "reports" / "audit_scaled.jsonl"
SEED = 20261116
FIRST_20 = set("AAPL MSFT NVDA AMZN GOOGL META JPM GS V JNJ PFE UNH XOM CAT BA WMT KO NKE "
               "DIS TSLA".split())
PAIRS, BOUNDARIES = 80, 80
MODEL = "claude-opus-5-5"


def text_now(r: dict) -> str:
    if "diff" in r:
        return "".join(t for op, t in r["diff"] if op != "-")
    return r.get("body", "")


def text_before(r: dict) -> str:
    if "diff" in r:
        return "".join(t for op, t in r["diff"] if op != "+")
    return r.get("body", "")


def clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + " […]"


def sample() -> list[dict]:
    rng = random.Random(SEED)
    docs = []
    for f in sorted(DATA.glob("*.json")):
        if f.stem in ("index", "findings", "search") or f.stem in FIRST_20:
            continue
        docs.append(json.loads(f.read_text()))
    items: list[dict] = []
    pairs = [(d, r) for d in docs for r in d["risks"]
             if r["status"] in ("edited", "rewritten", "unchanged")]
    for d, r in rng.sample(pairs, PAIRS):
        items.append({"q": "pair", "ticker": d["ticker"], "id": r["id"], "status": r["status"],
                      "old_title": r.get("old_title", r["title"]),
                      "old": clip(text_before(r), 2500),
                      "title": r["title"], "new": clip(text_now(r), 2500)})
    for d in docs:
        now = [r for r in d["risks"] if r["status"] not in ("removed", "merged")]
        before = [r for r in d["risks"] if r["status"] not in ("new", "split")]
        for r in d["risks"]:
            if r["status"] not in ("new", "removed", "split", "merged"):
                continue
            other = before if r["status"] in ("new", "split") else now
            side = text_before if r["status"] in ("new", "split") else text_now
            items.append({
                "q": "unpaired", "ticker": d["ticker"], "id": r["id"], "status": r["status"],
                "title": r["title"], "text": clip(r.get("body", ""), 3000),
                "link_title": r.get("link_title"),
                "other": [{"title": o.get("old_title", o["title"])
                           if r["status"] in ("new", "split") else o["title"],
                           "opening": clip(side(o), 300)} for o in other],
            })
    allr = [(d, r) for d in docs for r in d["risks"] if r["status"] not in ("removed", "merged")]
    for d, r in rng.sample(allr, BOUNDARIES):
        items.append({"q": "boundary", "ticker": d["ticker"], "id": r["id"],
                      "status": r["status"], "title": r["title"], "text": clip(text_now(r), 6000)})
    return items


SYSTEM = """You audit a tool that compares the risk factors (Item 1A) of a company's \
10-K with the previous year's. Judge only from the text you are given. Be strict and \
literal: you are checking the tool, not the company."""


def prompt(it: dict) -> tuple[str, type]:
    from pydantic import BaseModel, Field

    class Pair(BaseModel):
        same_risk: Literal["yes", "no", "unsure"]
        reason: str = Field(description="One sentence")

    class Unpaired(BaseModel):
        verdict: Literal["correct", "has_counterpart", "wrong_link", "unsure"]
        counterpart: str = Field(description="Exact title of the counterpart, or empty")
        reason: str = Field(description="One sentence")

    class Boundary(BaseModel):
        verdict: Literal["complete", "fragment", "contains_other_risks", "not_a_risk"]
        reason: str = Field(description="One sentence")

    if it["q"] == "pair":
        return (f"Are these the same risk factor, carried from last year to this year "
                f"(possibly reworded)?\n\nLAST YEAR\nTitle: {it['old_title']}\n{it['old']}"
                f"\n\nTHIS YEAR\nTitle: {it['title']}\n{it['new']}"), Pair
    if it["q"] == "unpaired":
        yr = "last year's" if it["status"] in ("new", "split") else "this year's"
        claim = {
            "new": "this risk is new: nothing in last year's list covers it",
            "removed": "this risk was dropped: nothing in this year's list covers it",
            "split": f"this risk was split off from last year's risk \"{it['link_title']}\"",
            "merged": f"this risk was folded into this year's risk \"{it['link_title']}\"",
        }[it["status"]]
        others = "\n".join(f"- {o['title']} :: {o['opening']}" for o in it["other"])
        return (f"The tool claims {claim}.\n\nRISK\nTitle: {it['title']}\n{it['text']}\n\n"
                f"{yr.upper()} RISKS (title :: opening)\n{others}\n\n"
                "Answer correct if the claim holds. Answer has_counterpart if one risk in the "
                "list is plainly the same risk (name it). Answer wrong_link if the claim names "
                "a split/merge partner that is not where this text came from or went."), Unpaired
    return (f"Is this one whole risk factor: a title and all of its own body, with no body "
            f"text belonging to a different risk factor and nothing obviously cut off?\n\n"
            f"Title: {it['title']}\n{it['text']}"), Boundary


def judge(client, it: dict) -> dict:
    from pydantic import ValidationError

    user, schema = prompt(it)
    row = {k: it[k] for k in ("q", "ticker", "id", "status", "title")}
    try:
        resp = client.messages.parse(model=MODEL, max_tokens=2048, system=SYSTEM,
                                     output_config={"effort": "low"},
                                     messages=[{"role": "user", "content": user}],
                                     output_format=schema)
    except ValidationError:
        return {**row, "answer": None}
    row.update(answer=resp.parsed_output.model_dump() if resp.parsed_output else None,
               input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens)
    return row


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return []
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return [round(max(0, c - h), 4), round(min(1, c + h), 4)]


def score() -> int:
    rows = [json.loads(x) for x in OUT.read_text().splitlines() if x]
    rows = [r for r in rows if r.get("answer")]

    def rate(sel: list[dict], ok) -> dict:
        k = sum(1 for r in sel if ok(r["answer"]))
        return {"k": k, "n": len(sel), "rate": round(k / len(sel), 4) if sel else None,
                "ci95": wilson(k, len(sel))}

    # Drop judgements the judge could not make from what it was shown: a body
    # cut at the prompt's length limit read as a fragment, and "unsure" on an
    # unpaired risk when it saw only the other year's openings.
    cost = sum(r.get("input_tokens", 0) * 4 + r.get("output_tokens", 0) * 20 for r in rows) / 1e6
    clipped = {r["id"] for r in rows if r["q"] == "boundary"
               and r["answer"]["verdict"] == "fragment" and "[…]" in r["answer"]["reason"]}
    unsure = [r for r in rows if r["q"] == "unpaired" and r["answer"]["verdict"] == "unsure"]
    rows = [r for r in rows if r["id"] not in clipped and r not in unsure]
    # Items the pipeline no longer produces after the fix the audit prompted
    # (summary lists read as risks) are scored again against the rebuilt data.
    now: dict[tuple[str, str], str] = {}
    for f in DATA.glob("*.json"):
        if f.stem not in ("index", "findings", "search"):
            for r in json.loads(f.read_text())["risks"]:
                now[(f.stem, r["id"])] = r["status"]
    gone = [r for r in rows if r["q"] == "unpaired" and (r["ticker"], r["id"]) not in now]
    # Raising the split/merge threshold (0.10 to 0.13) after the audit turned
    # some audited split/merge calls into new/removed. Their verdict was about
    # the old call, so they are counted out rather than re-scored unjudged.
    moved = [r for r in rows if r["q"] == "unpaired" and r not in gone
             and now[(r["ticker"], r["id"])] != r["status"]]
    by = {q: [r for r in rows if r["q"] == q] for q in ("pair", "unpaired", "boundary")}
    un = by["unpaired"]
    fixed = [r for r in un if r not in gone and r not in moved]
    report = {
        "judge": MODEL,
        "companies": len({r["ticker"] for r in rows}),
        "pairs_same": rate(by["pair"], lambda a: a["same_risk"] == "yes"),
        "new_correct": rate([r for r in un if r["status"] == "new"],
                            lambda a: a["verdict"] == "correct"),
        "removed_correct": rate([r for r in un if r["status"] == "removed"],
                                lambda a: a["verdict"] == "correct"),
        "split_merge_correct": rate([r for r in un if r["status"] in ("split", "merged")],
                                    lambda a: a["verdict"] == "correct"),
        "boundary_complete": rate(by["boundary"], lambda a: a["verdict"] == "complete"),
        "excluded": {"boundary_cut_by_prompt_limit": len(clipped), "unpaired_unsure": len(unsure)},
        "after_fix": {
            "resolved_by_summary_fix": len(gone),
            "resolved": sorted({f"{r['ticker']} {r['status']}" for r in gone}),
            "status_changed_by_threshold": [
                f"{r['ticker']} {r['status']}->{now[(r['ticker'], r['id'])]} "
                f"(judged {r['answer']['verdict']})" for r in moved],
            "new_correct": rate([r for r in fixed if r["status"] == "new"],
                                lambda a: a["verdict"] == "correct"),
            "removed_correct": rate([r for r in fixed if r["status"] == "removed"],
                                    lambda a: a["verdict"] == "correct"),
            "split_merge_correct": rate([r for r in fixed if r["status"] in ("split", "merged")],
                                        lambda a: a["verdict"] == "correct"),
        },
        "misses": [{k: r[k] for k in ("q", "ticker", "status", "title")} | r["answer"]
                   for r in rows
                   if (r["q"] == "pair" and r["answer"]["same_risk"] != "yes")
                   or (r["q"] != "pair" and r["answer"]["verdict"] not in ("correct", "complete"))],
        "cost_usd": round(cost, 2),
    }
    (ROOT / "reports" / "audit_scaled.json").write_text(json.dumps(report, indent=1) + "\n")
    for k, v in list(report.items()) + [(f"after_fix.{k}", v)
                                         for k, v in report["after_fix"].items()]:
        if isinstance(v, dict) and "k" in v:
            print(f"{k:32} {v['k']}/{v['n']} {v['ci95']}")
    print("excluded", report["excluded"], "resolved", report["after_fix"]["resolved"])
    print("threshold moved", report["after_fix"]["status_changed_by_threshold"])
    print("misses", len(report["misses"]), "cost", report["cost_usd"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if args.score:
        return score()
    import anthropic

    items = sample()
    done = set()
    if OUT.exists():
        done = {(json.loads(x)["q"], json.loads(x)["id"]) for x in OUT.read_text().splitlines()}
    todo = [it for it in items if (it["q"], it["id"]) not in done]
    print(f"{len(items)} items, {len(todo)} to judge", file=sys.stderr)
    client = anthropic.Anthropic(max_retries=4)
    with ThreadPoolExecutor(args.workers) as pool, OUT.open("a") as f:
        for row in pool.map(lambda it: judge(client, it), todo):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
    return score()


if __name__ == "__main__":
    raise SystemExit(main())
