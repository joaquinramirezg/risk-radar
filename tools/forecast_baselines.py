#!/usr/bin/env python3
"""Scores and the two baselines every forecast has to beat.

  B0 base rate      P = the share of companies whose 10-K added the theme, one
                    number per theme (from the year the model learns on).
  B1 company trend  P = that share among companies whose mentions of the theme
                    rose, or did not, in their 10-K before (two numbers per theme).

Brier score: the mean squared gap between the probability and what happened
(0 or 1); 0 is perfect, and always saying 50% scores 0.25. Log loss punishes a
confident miss harder. Both are scored out of sample (10 folds, by company), and
intervals come from resampling companies, since a company's eight themes are
not independent.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence

EPS = 1e-4


def brier(p: Sequence[float], y: Sequence[int]) -> float:
    return sum((a - b) ** 2 for a, b in zip(p, y, strict=True)) / len(p)


def log_loss(p: Sequence[float], y: Sequence[int]) -> float:
    return -sum(
        math.log(min(max(a if b else 1 - a, EPS), 1)) for a, b in zip(p, y, strict=True)
    ) / len(p)


def folds(tickers: Sequence[str], k: int = 10, seed: int = 0) -> dict[str, int]:
    ts = sorted(set(tickers))
    random.Random(seed).shuffle(ts)
    return {t: i % k for i, t in enumerate(ts)}


def b0_fit(rows: list[dict]) -> Callable[[dict], float]:
    by: dict[str, list[int]] = {}
    for r in rows:
        by.setdefault(r["theme"], []).append(r["y"])
    # Add-one smoothing keeps a theme no company added off 0%, which log loss would punish forever.
    rate = {t: (sum(v) + 1) / (len(v) + 2) for t, v in by.items()}
    return lambda r: rate.get(r["theme"], 0.5)


def b1_fit(rows: list[dict]) -> Callable[[dict], float]:
    by: dict[tuple[str, int], list[int]] = {}
    for r in rows:
        by.setdefault((r["theme"], r["rose"]), []).append(r["y"])
    rate = {k: (sum(v) + 1) / (len(v) + 2) for k, v in by.items()}
    return lambda r: rate.get((r["theme"], r["rose"]), 0.5)


def cross_val(
    rows: list[dict], fit: Callable[[list[dict]], Callable[[dict], float]], k: int = 10
) -> list[float]:
    """Out-of-sample probability for every row: each fold is predicted by a fit on the others."""
    fold = folds([r["ticker"] for r in rows], k)
    out = [0.0] * len(rows)
    for f in range(k):
        train = [r for r in rows if fold[r["ticker"]] != f]
        pred = fit(train)
        for i, r in enumerate(rows):
            if fold[r["ticker"]] == f:
                out[i] = pred(r)
    return out


def cluster_ci(
    rows: list[dict], stat: Callable[[list[int]], float], iterations: int = 2000, seed: int = 0
) -> tuple[float, float]:
    """95% percentile interval of stat(indices), resampling whole companies."""
    groups: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(r["ticker"], []).append(i)
    keys = sorted(groups)
    rng = random.Random(seed)
    vals = []
    for _ in range(iterations):
        idx = [i for _ in keys for i in groups[keys[rng.randrange(len(keys))]]]
        vals.append(stat(idx))
    vals.sort()
    return vals[int(0.025 * iterations)], vals[int(0.975 * iterations) - 1]


def score(rows: list[dict], probs: dict[str, list[float]], ref: str = "B0") -> dict:
    """Brier and log loss with intervals for each forecaster, and its gap to `ref`."""
    y = [r["y"] for r in rows]
    out: dict = {"n": len(rows), "companies": len({r["ticker"] for r in rows}), "positives": sum(y)}
    for name, p in probs.items():
        b = brier(p, y)
        s = {
            "brier": round(b, 4),
            "brier_ci": [
                round(v, 4)
                for v in cluster_ci(
                    rows, lambda ix, p=p: brier([p[i] for i in ix], [y[i] for i in ix])
                )
            ],
            "log_loss": round(log_loss(p, y), 4),
            "log_loss_ci": [
                round(v, 4)
                for v in cluster_ci(
                    rows, lambda ix, p=p: log_loss([p[i] for i in ix], [y[i] for i in ix])
                )
            ],
        }
        if name != ref and ref in probs:
            q = probs[ref]
            d = brier(p, y) - brier(q, y)
            s[f"brier_minus_{ref}"] = round(d, 4)
            s[f"brier_minus_{ref}_ci"] = [
                round(v, 4)
                for v in cluster_ci(
                    rows,
                    lambda ix, p=p, q=q: (
                        brier([p[i] for i in ix], [y[i] for i in ix])
                        - brier([q[i] for i in ix], [y[i] for i in ix])
                    ),
                )
            ]
        out[name] = s
    return out


def calibration(
    p: Sequence[float], y: Sequence[int], edges: Sequence[float] = (0, 0.1, 0.25, 0.5, 0.75, 1.0001)
) -> list[dict]:
    """Forecasts grouped by probability, against how often the theme was added."""
    rows = []
    for lo, hi in zip(edges, edges[1:], strict=False):
        ix = [i for i, a in enumerate(p) if lo <= a < hi]
        if ix:
            rows.append(
                {
                    "from": lo,
                    "to": min(hi, 1.0),
                    "n": len(ix),
                    "mean_p": round(sum(p[i] for i in ix) / len(ix), 3),
                    "observed": round(sum(y[i] for i in ix) / len(ix), 3),
                }
            )
    return rows
