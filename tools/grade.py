#!/usr/bin/env python3
"""Grade 30 of the agent's answers by hand, to check the model grader.

  python3 tools/grade.py            # about 20 minutes; resumable
  python3 tools/grade.py --status   # agreement with the model grader so far

Shows the question, the reference answer and the agent's answer (Haiku run),
in a fixed random order, without the model grader's verdict. Type c (correct),
p (partly correct) or w (wrong). Results go to results/human_grades.jsonl, and
`node api/_tools/eval.mjs report` publishes how often the model grader agrees
with you.
"""

from __future__ import annotations

import argparse
import json
import random
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANSWERS = ROOT / "results" / "answers-claude-haiku-5-5-low.jsonl"
GOLDEN = ROOT / "data" / "golden" / "golden.jsonl"
OUT = ROOT / "results" / "human_grades.jsonl"
TARGET = 30
VERDICT = {"c": "correct", "p": "partial", "w": "wrong"}


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def status(rows: list[dict], graded: list[dict]) -> None:
    model = {r["qid"]: (r.get("judge") or {}).get("verdict") for r in rows}
    pairs = [(g["verdict"], model[g["qid"]]) for g in graded if model.get(g["qid"])]
    same = sum(1 for h, m in pairs if h == m)
    print(f"graded {len(graded)} of {TARGET}; model grader agrees on {same} of {len(pairs)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    rows = [r for r in load(ANSWERS) if r["answerable"] and not r["abstained"]]
    ref = {g["qid"]: g for g in load(GOLDEN)}
    graded = load(OUT)
    if args.status:
        status(rows, graded)
        return 0
    done = {g["qid"] for g in graded}
    order = sorted(rows, key=lambda r: r["qid"])
    random.Random(30).shuffle(order)
    todo = [r for r in order[:TARGET] if r["qid"] not in done]
    print(f"{len(done)} graded, {len(todo)} to go. c = correct, p = partly, w = wrong, q = quit.\n")
    for r in todo:
        print("=" * 78)
        print(textwrap.fill("QUESTION: " + r["question"], 78))
        print(textwrap.fill("REFERENCE: " + ref[r["qid"]]["answer"], 78))
        print("-" * 78)
        print(textwrap.fill(r["answer"], 78))
        print("=" * 78)
        while (v := input("c / p / w / q: ").strip().lower()) not in ("c", "p", "w", "q"):
            pass
        if v == "q":
            break
        with OUT.open("a") as fh:
            fh.write(json.dumps({"qid": r["qid"], "verdict": VERDICT[v]}) + "\n")
    status(rows, load(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
