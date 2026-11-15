#!/usr/bin/env python3
"""Hand-write the golden set for "Ask the filings". This is the one part nobody can do for you.

  python3 tools/label.py                 # read a risk factor, write the question it answers
  python3 tools/label.py --unanswerable  # questions the filings cannot answer
  python3 tools/label.py --status        # progress and composition

For each risk factor shown: write a question a reader might ask that this
passage answers, type the numbers of the sentences that answer it, and a short
answer in your own words. That gives the gold risk, the gold sentences and a
reference answer, all from a person. If a model wrote the questions or the
labels, the test would grade itself, so this tool has no generation mode.

Resumable: appends to data/golden/golden.jsonl and never shows a risk twice.
At the question prompt: s skip | q save and quit
"""
from __future__ import annotations

import argparse
import json
import random
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "data" / "golden" / "golden.jsonl"
CORPUS = ROOT / "api" / "_data" / "corpus.json"
TARGET = 60
# Questions people ask are mostly about what changed, so changed risks are
# shown more often than unchanged ones. Every risk can still come up.
WEIGHT = {"new": 4, "rewritten": 3, "split": 3, "edited": 2, "unchanged": 1}
STATUS_NOTE = {
    "new": "NEW this year",
    "rewritten": "REWRITTEN since last year",
    "split": "SPLIT out of a risk from last year",
    "edited": "EDITED since last year",
    "unchanged": "unchanged from last year",
}


def load() -> list[dict]:
    if not GOLDEN.exists():
        return []
    return [json.loads(x) for x in GOLDEN.read_text().splitlines() if x.strip()]


def append(rec: dict) -> None:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    with GOLDEN.open("a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def next_qid(items: list[dict]) -> str:
    return f"q{len(items) + 1:03d}"


def status(items: list[dict]) -> None:
    unans = sum(1 for i in items if not i["gold_risks"])
    print(f"\ngolden set: {len(items)} of ~{TARGET} "
          f"({len(items) - unans} answerable, {unans} unanswerable)")
    want_unans = max(0, round(0.15 * TARGET) - unans)
    if want_unans:
        print(f"still to do: about {want_unans} unanswerable "
              f"(python3 tools/label.py --unanswerable)")


def ask(prompt: str) -> str:
    return input(prompt).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unanswerable", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    corpus = json.loads(CORPUS.read_text())
    names = {t: c["name"] for t, c in corpus["companies"].items()}
    items = load()
    if args.status:
        status(items)
        return 0

    if args.unanswerable:
        print(textwrap.dedent("""
            Questions a reader might plausibly ask that the risk factors cannot answer:
            a number they never state, a company outside the S&P 100, an opinion,
            a future event. These make the refusal rate measurable. Blank line to stop.
        """))
        while True:
            q = ask("unanswerable question: ")
            if not q:
                break
            why = ask("  why the filings cannot answer it: ")
            append({"qid": next_qid(items), "question": q, "gold_risks": [],
                    "gold_sentences": [], "answer": "", "note": why})
            items = load()
            print(f"  saved ({len(items)} total)\n")
        status(items)
        return 0

    used = {r for i in items for r in i["gold_risks"]}
    pool = [r for r in corpus["risks"] if r["sentences"] and r["id"] not in used]
    rng = random.Random(args.seed)
    pool.sort(key=lambda r: rng.random() ** (1 / WEIGHT.get(r["status"], 1)), reverse=True)

    print(textwrap.dedent(f"""
        For each risk factor: write a question someone might ask that it answers
        (it can name the company, or be about what changed this year), then the
        sentence numbers that answer it, then a one-line answer. s skips, q quits.
        {len(items)} done so far, aiming for about {TARGET}.
    """))
    for r in pool:
        print("=" * 78)
        print(f"{names[r['ticker']]} ({r['ticker']})   [{STATUS_NOTE.get(r['status'], r['status'])}]")
        print(textwrap.fill(r["title"], 78))
        if r.get("change_reason"):
            print(textwrap.fill(f"(what changed: {r['change_reason']})", 78))
        print("-" * 78)
        shown = r["sentences"][:14]
        for n, s in enumerate(shown, 1):
            print(textwrap.fill(s, 78, initial_indent=f"{n:>2}  ", subsequent_indent="    "))
        if len(r["sentences"]) > len(shown):
            print(f"    ... {len(r['sentences']) - len(shown)} more sentences not shown")
        print("=" * 78)
        q = ask("question: ")
        if q == "q":
            break
        if q == "s" or not q:
            continue
        while True:
            raw = ask("  sentence numbers that answer it (e.g. 2,3): ")
            try:
                nums = sorted({int(x) for x in raw.replace(" ", ",").split(",") if x})
            except ValueError:
                nums = []
            if nums and all(1 <= n <= len(shown) for n in nums):
                break
            print(f"  type numbers between 1 and {len(shown)}")
        answer = ask("  short answer in your words: ")
        append({"qid": next_qid(items), "question": q, "gold_risks": [r["id"]],
                "gold_sentences": [f"{r['id']}.{n - 1}" for n in nums], "answer": answer})
        items = load()
        print(f"  saved {len(items)}\n")
        if len(items) >= TARGET:
            print("That is the target. Thank you.")
            break
    status(items)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
