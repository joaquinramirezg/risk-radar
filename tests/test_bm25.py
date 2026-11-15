
import pytest

from harness.bm25 import BM25, tokenize

CORPUS = {
    "c0": "Supply chain disruption in Asia could delay product shipments.",
    "c1": "Currency exchange rate fluctuation may reduce reported revenue.",
    "c2": "A supply chain concentration risk exists with a single supplier.",
    "c3": "Cybersecurity incidents could compromise customer data.",
}


def build():
    ids = list(CORPUS)
    return BM25(ids, [CORPUS[i] for i in ids])


def test_tokenize_lowercases_and_drops_stopwords():
    assert tokenize("A risk IS in the Supply chain") == ["risk", "supply", "chain"]


def test_search_finds_the_lexically_matching_chunks():
    top = build().search("supply chain supplier", k=4)
    assert set(top[:2]) == {"c0", "c2"}
    assert "c3" not in top


def test_zero_scoring_chunks_are_dropped_not_padded():
    # Only one chunk mentions cybersecurity; asking for 4 must return 1, not
    # pad the list with irrelevant chunks that would inflate recall@k.
    assert build().search("cybersecurity", k=4) == ["c3"]


def test_no_match_returns_empty():
    assert build().search("photosynthesis chlorophyll", k=5) == []


def test_idf_is_never_negative_and_is_small_for_a_universal_term():
    b = BM25(["a", "b"], ["risk factor", "risk factor"])
    rare = BM25(["a", "b"], ["risk factor", "cybersecurity incident"])
    # Lucene-style smoothing keeps a universal term slightly positive rather
    # than zero or negative. What matters is that it carries far less weight
    # than a discriminating term.
    assert 0.0 < b.idf["risk"] < rare.idf["risk"]


def test_scoring_is_reproducible_under_ties():
    b = BM25(["z", "a"], ["identical text here", "identical text here"])
    assert b.search("identical", k=2) == b.search("identical", k=2)
    assert b.search("identical", k=2) == ["a", "z"]   # tie broken on id


def test_rejects_malformed_index():
    with pytest.raises(ValueError):
        BM25(["a"], ["x", "y"])
    with pytest.raises(ValueError):
        BM25([], [])
    with pytest.raises(ValueError):
        BM25(["a", "a"], ["x", "y"])


def test_bm25_saturates_with_term_frequency():
    # BM25's k1 term saturates: 10 repeats must not score 10x a single mention.
    b = BM25(["one", "many"], ["fraud", "fraud " * 10])
    scores = dict(b.score("fraud"))
    assert scores["many"] < 10 * scores["one"]
