#!/usr/bin/env python3
"""Hand-label the golden set. This is the one part nobody can do for you.

  python3 tools/label.py                 # walk chunks, write a question for each
  python3 tools/label.py --unanswerable  # add questions the corpus cannot answer
  python3 tools/label.py --status        # progress and composition

Reading a chunk and writing the question it answers gives you the gold span for
free and guarantees the label is real. If an LLM generates both the questions
and the labels, every downstream number is circular and the project is worth
nothing, so this tool deliberately has no generation mode.

Resumable: appends to data/golden/golden.jsonl and skips chunks already used.
Commands at the prompt: <question text> | s skip | b back | q save and quit
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from harness.corpus import load_corpus, load_golden, validate_golden

GOLDEN = Path("data/golden/golden.jsonl")


def next_qid(items) -> str:
    n = max((int(i.qid[1:]) for i in items if i.qid[1:].isdigit()), default=0)
    return f"q{n + 1:03d}"


def append(rec: dict) -> None:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    with GOLDEN.open("a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def status(items, chunks) -> None:
    ans = sum(1 for i in items if i.answerable)
    print(f"golden set: {len(items)} items ({ans} answerable, {len(items) - ans} unanswerable)")
    print(f"corpus:     {len({c.doc_id for c in chunks})} documents, {len(chunks)} chunks")
    covered = {cid for i in items for cid in i.gold_chunk_ids}
    print(f"chunks used as a gold span: {len(covered)}")
    problems = validate_golden(items, chunks)
    if problems:
        print("\nnot ready yet:")
        for p in problems:
            print("  -", p)
    else:
        print("\nthe set passes validation and the numbers are citable.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="data/corpus")
    ap.add_argument("--unanswerable", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--seed", type=int, default=0,
                    help="chunk order is shuffled so the set is not front-loaded "
                         "with whichever company sorts first")
    args = ap.parse_args()

    chunks = load_corpus(Path(args.corpus))
    items = load_golden(GOLDEN) if GOLDEN.exists() else []

    if args.status:
        status(items, chunks)
        return 0

    if args.unanswerable:
        print("Questions a reader might plausibly ask that Item 1A cannot answer.")
        print("These are what make the abstention rate measurable. Blank line to stop.\n")
        while True:
            q = input("unanswerable question: ").strip()
            if not q:
                break
            note = input("  why it is unanswerable: ").strip()
            qid = next_qid(items)
            append({"qid": qid, "question": q, "gold_chunk_ids": [], "note": note})
            items = load_golden(GOLDEN)
            print(f"  saved {qid}\n")
        status(items, chunks)
        return 0

    used = {cid for i in items for cid in i.gold_chunk_ids}
    pool = [c for c in chunks if c.chunk_id not in used]
    random.Random(args.seed).shuffle(pool)
    print(f"{len(pool)} unlabelled chunks. Write the question each one answers.\n")

    idx = 0
    while idx < len(pool):
        c = pool[idx]
        print("=" * 78)
        print(f"{c.chunk_id}   [{c.doc_id}]   {c.heading}")
        print("-" * 78)
        print(c.text[:1400])
        print("=" * 78)
        raw = input("question (s skip, b back, q quit): ").strip()
        if raw == "q":
            break
        if raw == "s":
            idx += 1
            continue
        if raw == "b":
            idx = max(0, idx - 1)
            continue
        if len(raw) < 15:
            print("  too short to be a real question; try again\n")
            continue
        qid = next_qid(items)
        append({"qid": qid, "question": raw, "gold_chunk_ids": [c.chunk_id]})
        items = load_golden(GOLDEN)
        print(f"  saved {qid}  ({len(items)} labelled)\n")
        idx += 1

    status(items, chunks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
