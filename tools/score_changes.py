#!/usr/bin/env python3
"""Agreement, cost and latency of the change-type classifier.

  python3 tools/score_changes.py

Compares reports/change_types.jsonl with labels/change_labels.json on the
labelled sample and writes reports/change_eval.json: accuracy and Cohen's kappa
with a bootstrap 95% interval, the confusion matrix, cost at list price, and
latency percentiles over every call.
"""
from __future__ import annotations

import json
import random
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = ["new_exposure", "escalated", "de_escalated", "boilerplate"]
PRICE_PER_MTOK = {"claude-haiku-5-5": (0.10, 0.50)}  # input, output in USD


def kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in LABELS) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def bootstrap(a: list[str], b: list[str], stat, reps: int = 2000) -> list[float]:
    rnd = random.Random(0)
    idx = range(len(a))
    vals = sorted(stat(*zip(*[(a[i], b[i]) for i in rnd.choices(idx, k=len(a))], strict=True))
                  for _ in range(reps))
    return [round(vals[int(0.025 * reps)], 3), round(vals[int(0.975 * reps)], 3)]


def acc(a, b) -> float:
    return sum(x == y for x, y in zip(a, b, strict=True)) / len(a)


def main() -> int:
    lines = (ROOT / "reports" / "change_types.jsonl").read_text().splitlines()
    rows = [json.loads(x) for x in lines if x]
    gold = json.loads((ROOT / "labels" / "change_labels.json").read_text())["labels"]
    pred = {r["key"]: r["label"] for r in rows}
    keys = [k for k in gold if k in pred]
    g = [gold[k]["label"] for k in keys]
    p = [pred[k] or "none" for k in keys]
    model = rows[0]["model"]
    pin, pout = PRICE_PER_MTOK[model]
    tin = sum(r["input_tokens"] for r in rows)
    tout = sum(r["output_tokens"] for r in rows)
    secs = sorted(r["seconds"] for r in rows)
    report = {
        "model": model,
        "calls": len(rows),
        "labelled": len(keys),
        "accuracy": round(acc(g, p), 3), "accuracy_ci95": bootstrap(g, p, acc),
        "kappa": round(kappa(g, p), 3), "kappa_ci95": bootstrap(g, p, kappa),
        "confusion": {gl: {pl: sum(1 for x, y in zip(g, p, strict=True) if x == gl and y == pl)
                           for pl in LABELS} for gl in LABELS},
        "predicted_all": dict(Counter(r["label"] for r in rows)),
        "tokens": {"input": tin, "output": tout},
        "cost_usd": round(tin / 1e6 * pin + tout / 1e6 * pout, 4),
        "latency_s": {"p50": statistics.median(secs), "p95": secs[int(0.95 * (len(secs) - 1))]},
        "disagreements": [{"key": k, "ticker": gold[k]["ticker"], "gold": x, "model": y}
                          for k, x, y in zip(keys, g, p, strict=True) if x != y],
    }
    (ROOT / "reports" / "change_eval.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "disagreements"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
