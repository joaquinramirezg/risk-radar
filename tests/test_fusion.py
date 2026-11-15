import pytest

from harness.fusion import reciprocal_rank_fusion


def test_a_chunk_ranked_well_by_both_beats_one_ranked_first_by_one():
    bm25 = ["a", "b", "c"]
    dense = ["b", "d", "a"]
    assert reciprocal_rank_fusion([bm25, dense], k=2) == ["b", "a"]


def test_fusion_is_scale_free_it_only_reads_ranks():
    # Same ranks, so the same fused order, whatever produced them.
    assert reciprocal_rank_fusion([["x", "y"], ["y", "x"]]) == ["x", "y"]  # tie -> id order


def test_k_truncates_and_empty_inputs_are_fine():
    assert reciprocal_rank_fusion([["a", "b", "c"]], k=1) == ["a"]
    assert reciprocal_rank_fusion([[], []]) == []


def test_a_ranking_with_duplicates_is_rejected():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([["a", "a"]])
