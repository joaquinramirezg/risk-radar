#!/usr/bin/env python3
"""Agreement, cost and latency of the change-type classifier.

  python3 tools/score_changes.py

Compares each reports/change_types.<prompt>[.<model>].jsonl with two label sets
and writes reports/change_eval.json: "original" (labels/change_labels.json) and
"adjudicated" (labels/change_labels_adjudicated.json, the 17 items where the
models agreed against the original label re-read once). The first is a lower
bound and the second an upper bound on accuracy. It also reports pairwise kappa
between every run and both label sets. For each run it gives accuracy and
Cohen's kappa with a bootstrap 95% interval, the confusion matrix, cost at list
price, and latency percentiles.

The labelled sample is split in two by key: "dev" (even) is the half that was
read to revise the prompt, "test" (odd) was not looked at, so only test scores
say how a prompt revision generalises.
"""
from __future__ import annotations

import json
import random
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = ["new_exposure", "escalated", "de_escalated", "boilerplate"]
PRICE_PER_MTOK = {  # input, output in USD, list price
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


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


def split(key: str) -> str:
    return "dev" if int(key, 16) % 2 == 0 else "test"


def agreement(gold: dict, pred: dict, keys: list[str]) -> dict:
    g = [gold[k]["label"] for k in keys]
    p = [pred[k] or "none" for k in keys]
    return {"n": len(keys), "accuracy": round(acc(g, p), 3), "accuracy_ci95": bootstrap(g, p, acc),
            "kappa": round(kappa(g, p), 3), "kappa_ci95": bootstrap(g, p, kappa)}


def score_run(path: Path, gold: dict) -> dict:
    rows = [json.loads(x) for x in path.read_text().splitlines() if x]
    pred = {r["key"]: r["label"] for r in rows}
    keys = [k for k in gold if k in pred]
    g = [gold[k]["label"] for k in keys]
    p = [pred[k] or "none" for k in keys]
    model = rows[0]["model"]
    sample = [r for r in rows if r["key"] in gold]
    pin, pout = PRICE_PER_MTOK[model]
    tin = sum(r["input_tokens"] for r in sample)
    tout = sum(r["output_tokens"] for r in sample)
    secs = sorted(r["seconds"] for r in sample)
    return {
        "model": model,
        "prompt": rows[0]["prompt"],
        "effort": rows[0].get("effort", "low"),
        "calls": len(rows),
        "all": agreement(gold, pred, keys),
        "dev": agreement(gold, pred, [k for k in keys if split(k) == "dev"]),
        "test": agreement(gold, pred, [k for k in keys if split(k) == "test"]),
        "confusion": {gl: {pl: sum(1 for x, y in zip(g, p, strict=True) if x == gl and y == pl)
                           for pl in LABELS} for gl in LABELS},
        "predicted_all": dict(Counter(r["label"] for r in rows)),
        "tokens_on_sample": {"input": tin, "output": tout},
        "cost_usd_on_sample": round(tin / 1e6 * pin + tout / 1e6 * pout, 4),
        "cost_usd_per_1000": round((tin * pin + tout * pout) / 1e6 / len(sample) * 1000, 2),
        "latency_s": {"p50": statistics.median(secs), "p95": secs[int(0.95 * (len(secs) - 1))]},
        "disagreements": [{"key": k, "ticker": gold[k]["ticker"], "gold": x, "model": y}
                          for k, x, y in zip(keys, g, p, strict=True) if x != y],
    }


def pairwise(sets: dict[str, dict[str, str]], keys: list[str]) -> dict[str, dict[str, float]]:
    return {a: {b: round(kappa([sets[a][k] or "none" for k in keys],
                               [sets[b][k] or "none" for k in keys]), 3) for b in sets}
            for a in sets}


def main() -> int:
    golds = {name: json.loads((ROOT / "labels" / f).read_text())["labels"]
             for name, f in (("original", "change_labels.json"),
                             ("adjudicated", "change_labels_adjudicated.json"))}
    runs = sorted((ROOT / "reports").glob("change_types.*.jsonl"))
    report: dict[str, object] = {
        name: {r.stem.split(".", 1)[1]: score_run(r, gold) for r in runs}
        for name, gold in golds.items()
    }
    keys = list(golds["original"])
    sets = {f"labels:{n}": {k: g[k]["label"] for k in keys} for n, g in golds.items()}
    for r in runs:
        rows = [json.loads(x) for x in r.read_text().splitlines() if x]
        sets[r.stem.split(".", 1)[1]] = {x["key"]: x["label"] for x in rows}
    report["kappa_matrix"] = pairwise(sets, keys)
    (ROOT / "reports" / "change_eval.json").write_text(json.dumps(report, indent=1) + "\n")
    for gname in golds:
        for name, r in report[gname].items():
            t = r["test"]
            print(f"{gname:11} {name:14} test acc {t['accuracy']} kappa {t['kappa']} "
                  f"{t['kappa_ci95']} | all acc {r['all']['accuracy']} kappa {r['all']['kappa']}"
                  f" | ${r['cost_usd_per_1000']}/1k | p50 {r['latency_s']['p50']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
