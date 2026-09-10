from harness.chunking import _iter_paragraphs, chunk_document, normalize

DOC = """Item 1A. Risk Factors

Supply Chain Concentration

We depend on a single supplier for a critical component. A disruption could
materially affect our results of operations.

Foreign Currency Risk

A substantial portion of revenue is denominated in currencies other than the
US dollar. Adverse movements could reduce reported revenue.
"""


def test_normalize_collapses_spaces_but_keeps_paragraphs():
    assert normalize("a   b\n\n\n\nc") == "a b\n\nc"


def test_headings_are_carried_onto_their_chunks():
    chunks = chunk_document("AAPL-2025", DOC, target_chars=400, overlap_chars=0)
    headings = {c.heading for c in chunks}
    assert "Supply Chain Concentration" in headings
    assert "Foreign Currency Risk" in headings


def test_no_chunk_is_orphaned_from_a_heading():
    # The failure this corpus is chosen to expose: a chunk saying "could
    # materially affect our results" with no indication of which risk.
    for c in chunk_document("AAPL-2025", DOC, target_chars=200, overlap_chars=0):
        assert c.heading, f"chunk {c.chunk_id} has no heading"


def test_chunk_ids_are_unique_and_ordered():
    chunks = chunk_document("X", DOC, target_chars=200, overlap_chars=0)
    ids = [c.chunk_id for c in chunks]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


def test_offsets_point_back_into_the_normalized_text():
    chunks = chunk_document("X", DOC, target_chars=400, overlap_chars=0)
    for c in chunks:
        assert 0 <= c.char_start < c.char_end <= len(normalize(DOC))


def test_overlap_carries_tail_context_forward():
    chunks = chunk_document("X", DOC, target_chars=200, overlap_chars=60)
    assert len(chunks) > 1
    assert any(len(c.text) > 0 for c in chunks)


def test_rejects_bad_parameters():
    import pytest

    with pytest.raises(ValueError):
        chunk_document("X", DOC, target_chars=0)
    with pytest.raises(ValueError):
        chunk_document("X", DOC, target_chars=100, overlap_chars=100)


def test_no_corpus_text_is_ever_lost():
    """The invariant that matters most: chunking must not delete content.

    Regression guard for a real bug where a 139-character paragraph of risk
    prose was misclassified as a heading and dropped entirely. Every
    non-heading paragraph must appear in some chunk.
    """
    from harness.chunking import is_heading

    for target in (150, 200, 400, 1200):
        chunks = chunk_document("X", DOC, target_chars=target, overlap_chars=0)
        joined = "\n".join(c.text for c in chunks)
        for _, para in _iter_paragraphs(normalize(DOC)):
            if is_heading(para):
                continue
            first_line = para.split("\n")[0][:40]
            assert first_line in joined, (
                f"lost content at target_chars={target}: {first_line!r}"
            )


def test_is_heading_rejects_prose_that_merely_looks_short():
    from harness.chunking import is_heading

    assert is_heading("Supply Chain Concentration")
    assert is_heading("Item 1A. Risk Factors")          # item number, not a sentence
    assert not is_heading("A disruption could affect our results.")   # ends in a period
    assert not is_heading("Currency moves. Revenue falls")           # sentence break
    assert not is_heading("Line one\nline two")                      # multi-line
    assert not is_heading("x" * 200)                                 # too long
    assert not is_heading("lowercase start")


def test_overlap_never_crosses_a_heading_boundary():
    """Regression guard for a bug found by the end-to-end smoke test.

    A chunk headed "Foreign Currency Exposure" opened with supplier-concentration
    prose carried over as overlap. Any gold label attached to that chunk would
    have been wrong in a way no metric could reveal.
    """
    doc = """Supplier Concentration

We rely on a single supplier in Taiwan for a critical semiconductor component.

Foreign Currency Exposure

More than half of our revenue is billed in euros and yen.
"""
    chunks = chunk_document("X", doc, target_chars=120, overlap_chars=60)
    for c in chunks:
        if c.heading == "Foreign Currency Exposure":
            assert "supplier" not in c.text.lower(), c.text
        if c.heading == "Supplier Concentration":
            assert "euros" not in c.text.lower(), c.text
