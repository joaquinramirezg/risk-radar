"""Score the year-over-year matcher against the labelled sample.

Reads labels/items.json plus one or more label files ({"labels": {id: {q1, q2}}})
and reports matcher precision, new/removed precision, clean-boundary rate and
inter-labeller agreement, with Wilson 95% intervals.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def rate(k: int, n: int) -> dict[str, object]:
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": [round(lo, 4), round(hi, 4)]}


def kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def score(items: list[dict], labels: dict[str, dict]) -> dict[str, object]:
    ids = [i for i in items if i["id"] in labels]
    matched = [i for i in ids if i["kind"] == "matched"]
    new = [i for i in ids if i["kind"] == "new"]
    removed = [i for i in ids if i["kind"] == "removed"]
    q1 = {i["id"]: labels[i["id"]]["q1"] for i in ids}
    return {
        "items": len(ids),
        "match_precision": rate(sum(q1[i["id"]] == "same" for i in matched), len(matched)),
        "new_precision": rate(sum(q1[i["id"]] == "truly_new" for i in new), len(new)),
        "removed_precision": rate(sum(q1[i["id"]] == "truly_removed" for i in removed), len(removed)),
        "missed_links": sorted(i["id"] for i in new + removed if q1[i["id"]].startswith("cand")),
        "clean_boundary": rate(sum(labels[i["id"]]["q2"] == "complete" for i in ids), len(ids)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "label_eval.json")
    args = ap.parse_args()
    items = json.loads((ROOT / "labels" / "items.json").read_text())["items"]
    sets = {p.stem: json.loads(p.read_text())["labels"] for p in args.labels}
    report: dict[str, object] = {name: score(items, lab) for name, lab in sets.items()}
    names = list(sets)
    agree = {}
    for x in range(len(names)):
        for y in range(x + 1, len(names)):
            a, b = sets[names[x]], sets[names[y]]
            common = sorted(set(a) & set(b))
            for q in ("q1", "q2"):
                va, vb = [a[i][q] for i in common], [b[i][q] for i in common]
                agree[f"{names[x]}~{names[y]}:{q}"] = {
                    "n": len(common),
                    "agreement": round(sum(u == v for u, v in zip(va, vb, strict=True)) / len(common), 4),
                    "kappa": round(kappa(va, vb), 3),
                    "disagree": [i for i, u, v in zip(common, va, vb, strict=True) if u != v],
                }
    report["agreement"] = agree
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
