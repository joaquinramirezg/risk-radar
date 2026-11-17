"""The v3 forecast: scores, baselines, the refuse-after-filing rule, the model, 10-Q tags."""

from __future__ import annotations

import json
import math
import random
from datetime import UTC, datetime

import pytest

from extract_10q import norm, sentences, tag
from forecast import Logistic, solve
from forecast_baselines import b0_fit, b1_fit, brier, calibration, cross_val, log_loss
from forecast_common import FORECAST_THEMES, SITE, labels, sector
from forecast_features import build
from score_forecast import resolve


def test_brier_known_cases():
    assert brier([1.0, 0.0], [1, 0]) == 0
    assert brier([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0]) == 0.25
    assert brier([0.8, 0.3], [1, 0]) == pytest.approx((0.04 + 0.09) / 2)


def test_log_loss_known_case_and_clipping():
    assert log_loss([0.5], [1]) == pytest.approx(math.log(2))
    assert math.isfinite(log_loss([0.0], [1]))  # a certain miss is clipped, not infinite


FC = {
    "forecasts": [
        {"ticker": "AAA", "theme": "China", "p": 0.9, "b0": 0.3},
        {"ticker": "AAA", "theme": "Climate", "p": 0.2, "b0": 0.2},
        {"ticker": "BBB", "theme": "China", "p": 0.7, "b0": 0.3},
        {"ticker": "CCC", "theme": "China", "p": 0.4, "b0": 0.3},
    ]
}
FROZEN = datetime(2027, 1, 20, 18, 0, tzinfo=UTC)


def test_forecast_after_the_filing_is_refused():
    out = resolve(
        FC,
        {
            "AAA": {"filed": "2027-02-10", "up": ["China"]},
            "BBB": {"filed": "2027-01-15", "up": ["China"]},
        },
        FROZEN,
    )
    assert out["refused"] == ["BBB"]  # filed before the freeze: not a forecast
    assert out["companies_scored"] == 1 and out["companies_pending"] == 1
    assert out["model"]["brier"] == pytest.approx(((0.9 - 1) ** 2 + 0.2**2) / 2)


def test_filing_on_the_freeze_day_is_refused():
    out = resolve(FC, {"CCC": {"filed": "2027-01-20", "up": []}}, FROZEN)
    assert out["refused"] == ["CCC"] and out["n"] == 0


def test_baselines():
    rows = [
        {"ticker": f"T{i}", "theme": "China", "rose": i % 2, "y": int(i % 2 == 1 and i < 8)}
        for i in range(10)
    ]
    assert b0_fit(rows)({"theme": "China"}) == pytest.approx((4 + 1) / (10 + 2))
    b1 = b1_fit(rows)
    assert b1({"theme": "China", "rose": 1}) == pytest.approx((4 + 1) / (5 + 2))
    assert b1({"theme": "China", "rose": 0}) == pytest.approx(1 / 7)


def test_cross_val_never_sees_its_own_company():
    rows = [{"ticker": f"T{i}", "theme": "China", "rose": 0, "y": int(i == 0)} for i in range(10)]
    p = cross_val(rows, b0_fit, k=10)
    assert p[0] == pytest.approx(1 / 11)  # T0's own positive is not in its training fold


def test_calibration_bins():
    out = calibration([0.05, 0.05, 0.9, 0.95], [0, 0, 1, 0])
    assert out[0] == {"from": 0, "to": 0.1, "n": 2, "mean_p": 0.05, "observed": 0.0}
    assert out[-1]["n"] == 2 and out[-1]["observed"] == 0.5


def test_solve():
    assert solve([[2.0, 1.0], [1.0, 3.0]], [3.0, 5.0]) == pytest.approx([0.8, 1.4])


def test_logistic_learns_a_real_signal():
    rng = random.Random(1)
    rows = []
    for i in range(400):
        s = rng.random() < 0.5
        rows.append(
            {
                "ticker": f"T{i}",
                "theme": "China",
                "s": float(s),
                "noise": rng.random(),
                "y": int(rng.random() < (0.8 if s else 0.2)),
            }
        )
    m = Logistic(("s", "noise"), ("China",), l2=1.0).fit(rows)
    assert m.weights()["s"] > 0.5 and abs(m.weights()["noise"]) < 0.3
    assert m({"theme": "China", "s": 1.0, "noise": 0.5}) == pytest.approx(0.8, abs=0.07)
    assert "10-Q" not in m.reason({"theme": "China", "s": 1.0, "noise": 0.5})


def test_features_build():
    counts = {
        "AAA": {
            "current": dict.fromkeys(FORECAST_THEMES, 2),
            "previous": dict.fromkeys(FORECAST_THEMES, 1),
            "prev2": dict.fromkeys(FORECAST_THEMES, 1),
        },
        "BBB": {
            "current": dict.fromkeys(FORECAST_THEMES, 0),
            "previous": dict.fromkeys(FORECAST_THEMES, 0),
            "prev2": None,
        },
    }
    events = {
        "AAA": {
            "sector": "Technology",
            "next_10k": None,
            "back": [{"form": "8-K", "items": ["1.05", "8.01"]}],
            "next": [{"form": "10-Q", "items": []}],
        },
        "BBB": {"sector": "Technology", "next_10k": None, "back": [], "next": []},
    }
    q = {"AAA": {"next": {"updated": True, "themes": ["China"]}}}
    y = {"AAA": dict.fromkeys(FORECAST_THEMES, 1), "BBB": dict.fromkeys(FORECAST_THEMES, 0)}
    rows = build(counts, events, q, y)
    back = [r for r in rows if r["window"] == "back"]
    assert {r["ticker"] for r in back} == {"AAA"}  # BBB has no older 10-K: left out of the backtest
    cyber = next(r for r in back if r["theme"] == "Cybersecurity")
    assert cyber["k_cyber"] == 1 and cyber["rose"] == 0 and cyber["y"] == 1
    assert next(r for r in back if r["theme"] == "China")["k_cyber"] == 0
    china = next(
        r for r in rows if r["window"] == "next" and r["ticker"] == "AAA" and r["theme"] == "China"
    )
    assert (
        china["rose"] == 1
        and china["q_theme"] == 1
        and china["q_updated"] == 1
        and china["n_10q"] == 1
    )
    assert (
        next(r for r in rows if r["window"] == "next" and r["ticker"] == "BBB")["sector_share"]
        == 1.0
    )


def test_already_filed_company_is_not_forecast():
    counts = {
        "AAA": {
            "current": dict.fromkeys(FORECAST_THEMES, 1),
            "previous": dict.fromkeys(FORECAST_THEMES, 1),
            "prev2": None,
        }
    }
    events = {"AAA": {"next_10k": {"filed": "2026-11-10"}, "back": [], "next": []}}
    assert build(counts, events, {}, None) == []


def test_10q_tags():
    k = {
        norm(s)
        for s in sentences(
            "Our supply chain depends on suppliers in many countries around the world."
        )
    }
    assert (
        tag(
            "There have been no material changes to the risk factors in our Annual Report on Form 10-K.",
            k,
        )[0]
        == "no_change"
    )
    assert (
        tag("For risk factors, see Part I, Item 1A of our Annual Report on Form 10-K.", k)[0]
        == "reference_only"
    )
    new = (
        "In April 2026 the United States imposed new tariffs on imports from China that raise our costs. "
        * 1
        + "These tariffs may reduce demand for our products and hurt our margins over the coming year. "
        + "Retaliatory measures by China could restrict our ability to sell into that market at all. "
        + "We may be unable to pass these costs on to customers, and our results could suffer materially. "
        + "Further escalation could also disrupt the flow of components we buy from manufacturers there. "
        + "Our supply chain depends on suppliers in many countries around the world."
    )
    verdict, sents = tag(new, k)
    assert verdict == "updated"
    assert all("supply chain depends" not in s for s in sents)  # already in the 10-K: not new


def test_labels_match_the_findings_page():
    """The six v2 themes' outcomes are exactly the companies the findings page lists."""
    y = labels()
    for t in json.loads((SITE / "findings.json").read_text())["themes"]:
        assert sorted(k for k, v in y.items() if v[t["theme"]]) == sorted(t["tickers_up"]), t[
            "theme"
        ]


def test_sector():
    assert (
        sector("6021") == "Finance"
        and sector("3674") == "Technology"
        and sector("3711") == "Industrials"
        and sector("7372") == "Technology"
    )
    assert sector("2834") == "Health" and sector(None) == "Other"
