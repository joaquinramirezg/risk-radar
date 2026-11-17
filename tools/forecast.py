#!/usr/bin/env python3
"""The forecaster: one small logistic regression over all eight themes.

  PYTHONPATH=src:tools python3 tools/forecast.py

Inputs per company and theme are the signals in data/forecast_features.json; the
model has one intercept per theme (each theme's own base rate) and one shared
weight per signal, with a ridge penalty, so 102 companies are enough to fit it.

1. Backtest: the "back" rows (signals before the latest 10-K, outcome = what it
   added) scored out of sample with 10 folds by company, against B0 and B1.
   Written to reports/forecast_backtest.json.
2. Forecast: fit on every "back" row, predict every "next" row. Written to
   site/data/forecast.json as a DRAFT. Freezing is a separate, deliberate
   commit (`--freeze`), and a frozen file is never edited again.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date

from forecast_baselines import b0_fit, b1_fit, calibration, cross_val, score
from forecast_common import BACKTEST, FEATURES, FORECAST, FORECAST_THEMES

MODEL_VERSION = "v3.0"
L2 = 1.0  # ridge penalty on the signal weights (not the theme intercepts)

PLAIN = {  # the top reason, in words, when this signal pushed the probability up / down
    "rose": (
        "its mentions of the theme rose in its last 10-K",
        "its mentions of the theme did not rise in its last 10-K",
    ),
    "level": (
        "its last 10-K already discusses the theme at length",
        "its last 10-K barely mentions the theme",
    ),
    "sector_share": (
        "many companies in its sector wrote more about the theme",
        "few companies in its sector wrote more about the theme",
    ),
    "q_theme": (
        "a 10-Q since added risk text on the theme",
        "no 10-Q since added risk text on the theme",
    ),
    "q_updated": ("a 10-Q since added new risk text", "its 10-Qs since added no new risk text"),
    "k_cyber": ("it filed a cybersecurity incident 8-K", "no cybersecurity incident 8-K"),
    "k_deal": (
        "it filed an 8-K on a material agreement or acquisition",
        "no 8-K on a material agreement or acquisition",
    ),
    "k_exec": (
        "it filed an 8-K on a director or officer change",
        "no 8-K on a director or officer change",
    ),
    "k_other": ("it filed several 'other events' 8-Ks", "few 'other events' 8-Ks"),
}


def sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z)) if z > -30 else 1e-13


class Logistic:
    """Ridge logistic regression by Newton's method; stdlib only, so it reads in one screen."""

    def __init__(self, features: tuple[str, ...], themes: tuple[str, ...], l2: float = L2):
        self.features, self.themes, self.l2 = features, themes, l2
        self.mean: dict[str, float] = {}
        self.sd: dict[str, float] = {}
        self.w: list[float] = []

    def x(self, r: dict) -> list[float]:
        th = [1.0 if r["theme"] == t else 0.0 for t in self.themes]
        return th + [(r[f] - self.mean[f]) / self.sd[f] for f in self.features]

    def fit(self, rows: list[dict]) -> Logistic:
        for f in self.features:
            v = [r[f] for r in rows]
            m = sum(v) / len(v)
            self.mean[f] = m
            self.sd[f] = math.sqrt(sum((a - m) ** 2 for a in v) / len(v)) or 1.0
        X = [self.x(r) for r in rows]
        y = [r["y"] for r in rows]
        d, nt = len(X[0]), len(self.themes)
        pen = [0.01] * nt + [self.l2] * (
            d - nt
        )  # a whisker on intercepts keeps an all-0 theme finite
        w = [0.0] * d
        for _ in range(50):
            p = [sigmoid(sum(a * b for a, b in zip(xi, w, strict=True))) for xi in X]
            g = [
                sum((p[i] - y[i]) * X[i][j] for i in range(len(X))) + pen[j] * w[j]
                for j in range(d)
            ]
            H = [
                [
                    sum(p[i] * (1 - p[i]) * X[i][j] * X[i][k] for i in range(len(X)))
                    + (pen[j] if j == k else 0)
                    for k in range(d)
                ]
                for j in range(d)
            ]
            step = solve(H, g)
            w = [a - b for a, b in zip(w, step, strict=True)]
            if max(abs(s) for s in step) < 1e-8:
                break
        self.w = w
        return self

    def __call__(self, r: dict) -> float:
        return sigmoid(sum(a * b for a, b in zip(self.x(r), self.w, strict=True)))

    def weights(self) -> dict[str, float]:
        nt = len(self.themes)
        return {f: round(self.w[nt + i], 4) for i, f in enumerate(self.features)}

    def reason(self, r: dict) -> str:
        """The signal that moved this forecast furthest from the theme's base rate, in words."""
        nt = len(self.themes)
        pushes = {
            f: self.w[nt + i] * (r[f] - self.mean[f]) / self.sd[f]
            for i, f in enumerate(self.features)
        }
        f = max(pushes, key=lambda k: abs(pushes[k]))
        if abs(pushes[f]) < 0.05:
            return "close to the base rate for this theme"
        words = PLAIN.get(f, (f"{f} is high", f"{f} is low"))
        return words[0 if pushes[f] > 0 else 1]


def solve(A: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            for k in range(c, n + 1):
                M[r][k] -= f * M[c][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (M[r][n] - sum(M[r][k] * x[k] for k in range(r + 1, n))) / M[r][r]
    return x


def model_fit(features: tuple[str, ...]):
    themes = tuple(FORECAST_THEMES)
    return lambda rows: Logistic(features, themes).fit(rows)


def backtest(rows: list[dict], features: tuple[str, ...]) -> dict:
    probs = {
        "B0": cross_val(rows, b0_fit),
        "B1": cross_val(rows, b1_fit),
        "model": cross_val(rows, model_fit(features)),
    }
    out = score(rows, probs, ref="B0")
    out["model"]["brier_minus_B1"] = round(out["model"]["brier"] - out["B1"]["brier"], 4)
    out["calibration"] = calibration(probs["model"], [r["y"] for r in rows])
    by_theme = {}
    for th in FORECAST_THEMES:
        ix = [i for i, r in enumerate(rows) if r["theme"] == th]
        sub = [rows[i] for i in ix]
        if not sub:
            continue
        y = [r["y"] for r in sub]
        by_theme[th] = {
            "n": len(sub),
            "added": sum(y),
            **{
                k: round(sum((probs[k][i] - rows[i]["y"]) ** 2 for i in ix) / len(ix), 4)
                for k in probs
            },
        }
    out["by_theme"] = by_theme
    return out


def freeze() -> int:
    """Mark the draft frozen. Commit it alone right after ("Forecast frozen YYYY-MM-DD"):
    that commit's time is the public timestamp, and CI fails if the file changes after it."""
    doc = json.loads(FORECAST.read_text())
    if doc["status"] == "frozen":
        print("already frozen")
        return 1
    doc["status"], doc["frozen"] = "frozen", date.today().isoformat()
    FORECAST.write_text(json.dumps(doc, indent=0))
    print(
        f"frozen {doc['frozen']}: now commit {FORECAST.relative_to(FORECAST.parents[2])} on its own"
    )
    return 0


def main(argv: list[str]) -> int:
    if "--freeze" in argv:
        return freeze()
    data = json.loads(FEATURES.read_text())
    features = tuple(data["features"])
    back = [r for r in data["rows"] if r["window"] == "back"]
    nxt = [r for r in data["rows"] if r["window"] == "next"]
    report = backtest(back, features)
    full = Logistic(features, tuple(FORECAST_THEMES)).fit(back)
    report["weights"] = full.weights()
    report["model_version"] = MODEL_VERSION
    BACKTEST.parent.mkdir(parents=True, exist_ok=True)
    BACKTEST.write_text(json.dumps(report, indent=1))
    for k in ("B0", "B1", "model"):
        s = report[k]
        print(
            f"{k:6} Brier {s['brier']:.4f} {s['brier_ci']}  log loss {s['log_loss']:.4f} {s['log_loss_ci']}"
        )
    m = report["model"]
    print(
        f"model - B0 Brier {m['brier_minus_B0']:+.4f} {m['brier_minus_B0_ci']}; model - B1 {m['brier_minus_B1']:+.4f}"
    )
    print("weights", report["weights"])

    if FORECAST.exists() and json.loads(FORECAST.read_text()).get("status") == "frozen":
        print(f"{FORECAST.name} is frozen; not rewriting it. A new version is a new file.")
        return 0
    b0 = b0_fit(back)
    forecasts = []
    for r in nxt:
        forecasts.append(
            {
                "ticker": r["ticker"],
                "theme": r["theme"],
                "p": round(full(r), 3),
                "b0": round(b0(r), 3),
                "reason": full.reason(r),
                "inputs": {f: r[f] for f in features} | {"n_10q": r["n_10q"]},
            }
        )
    FORECAST.write_text(
        json.dumps(
            {
                "status": "draft",
                "question": "Will the company's next 10-K add or escalate risk language on this theme?",
                "made": date.today().isoformat(),
                "frozen": None,
                "model_version": MODEL_VERSION,
                "themes": list(FORECAST_THEMES),
                "backtest": {k: report[k] for k in ("n", "companies", "positives")}
                | {
                    k: {"brier": report[k]["brier"], "brier_ci": report[k]["brier_ci"]}
                    for k in ("B0", "B1", "model")
                },
                "forecasts": forecasts,
            },
            indent=0,
        )
    )
    print(
        f"wrote {len(forecasts)} draft forecasts for {len({f['ticker'] for f in forecasts})} companies to {FORECAST}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
