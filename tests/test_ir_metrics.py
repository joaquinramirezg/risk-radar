"""Hand-computed expectations. A bug in the scorer invalidates every number in
the README, so these are checked against arithmetic done by hand, not against
the implementation's own output.
"""
import math

import pytest

from harness.ir_metrics import (
    bootstrap_ci,
    dcg_at_k,
    mean,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

RANKED = ["c1", "c2", "c3", "c4", "c5"]


def test_recall_at_k_counts_only_the_top_k():
    assert recall_at_k(RANKED, {"c2", "c9"}, 3) == 0.5   # 1 of 2 found
    assert recall_at_k(RANKED, {"c2", "c4"}, 3) == 0.5   # c4 sits at rank 4
    assert recall_at_k(RANKED, {"c2", "c4"}, 4) == 1.0


def test_precision_denominator_is_k_not_results_returned():
    # Only two results, one relevant. Precision@5 must be 1/5, not 1/2:
    # a system that returns too few results is penalised for it.
    assert precision_at_k(["c1", "c2"], {"c1"}, 5) == pytest.approx(0.2)


def test_reciprocal_rank_uses_the_first_hit_only():
    assert reciprocal_rank(RANKED, {"c3", "c5"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(RANKED, {"zzz"}) == 0.0


def test_dcg_matches_hand_computation():
    # hits at ranks 1 and 3 -> 1/log2(2) + 1/log2(4) = 1.0 + 0.5
    assert dcg_at_k(RANKED, {"c1", "c3"}, 5) == pytest.approx(1.5)


def test_ndcg_is_one_for_a_perfect_ranking():
    assert ndcg_at_k(RANKED, {"c1", "c2"}, 5) == pytest.approx(1.0)


def test_ndcg_penalises_a_late_hit():
    # hit at rank 3 only: dcg = 0.5, ideal (1 relevant) = 1.0
    assert ndcg_at_k(RANKED, {"c3"}, 5) == pytest.approx(0.5)


def test_ndcg_ideal_is_capped_by_k():
    # 3 relevant chunks but k=2, so the ideal ranking can only place 2 of them:
    # ideal = 1/log2(2) + 1/log2(3) = 1.6309, NOT the 3-hit ideal.
    ideal = 1.0 + 1.0 / math.log2(3)
    # Retrieved top-2 are both relevant -> dcg equals ideal -> 1.0.
    assert ndcg_at_k(RANKED, {"c1", "c2", "c3"}, 2) == pytest.approx(1.0)
    # Only rank 2 is relevant -> dcg = 1/log2(3), divided by that same ideal.
    assert ndcg_at_k(RANKED, {"c2", "c9", "c8"}, 2) == pytest.approx(
        (1.0 / math.log2(3)) / ideal
    )


def test_unanswerable_questions_must_not_be_scored_as_zero():
    # Scoring an unanswerable question as recall 0.0 would silently drag the
    # headline number down and hide the abstention story. Refuse instead.
    with pytest.raises(ValueError):
        recall_at_k(RANKED, set(), 3)
    with pytest.raises(ValueError):
        ndcg_at_k(RANKED, set(), 3)


def test_duplicate_chunk_ids_are_rejected():
    with pytest.raises(ValueError):
        recall_at_k(["c1", "c1"], {"c1"}, 2)


def test_k_must_be_positive():
    with pytest.raises(ValueError):
        precision_at_k(RANKED, {"c1"}, 0)


def test_mean_rejects_empty():
    with pytest.raises(ValueError):
        mean([])


def test_bootstrap_ci_is_deterministic_and_brackets_the_mean():
    vals = [1.0] * 6 + [0.0] * 4          # mean 0.6
    lo, hi = bootstrap_ci(vals, seed=42)
    assert lo <= 0.6 <= hi
    assert bootstrap_ci(vals, seed=42) == bootstrap_ci(vals, seed=42)
    # At n=10 the interval must be wide. If this ever tightens below 20 points,
    # something is wrong with the resampling.
    assert hi - lo > 0.2


def test_bootstrap_ci_on_a_constant_sequence_has_zero_width():
    assert bootstrap_ci([0.5] * 20) == (0.5, 0.5)
