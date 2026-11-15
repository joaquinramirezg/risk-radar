from check_site import check_company

URL = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/x.htm"


def _doc(risks: list[dict], counts: dict, now: int, before: int) -> dict:
    return {"ticker": "X", "counts": counts, "risks": risks,
            "current": {"url": URL, "period_end": "2026-06-30", "filed": "2026-08-01",
                        "risks": now},
            "previous": {"url": URL, "period_end": "2025-06-30", "filed": "2025-08-01",
                         "risks": before}}


def test_a_consistent_company_passes():
    risks = [{"id": "a", "status": "new", "title": "New risk", "body": "Text."},
             {"id": "b", "status": "edited", "title": "T", "old_title": "T",
              "diff": [["=", "Same "], ["+", "more"]],
              "change": {"label": "escalated"}},
             {"id": "c", "status": "merged", "title": "Old", "body": "Old text.",
              "link_title": "T"}]
    assert check_company("X", _doc(risks, {"new": 1, "edited": 1, "merged": 1}, 2, 2)) == []


def test_counts_that_disagree_with_the_list_are_caught():
    risks = [{"id": "a", "status": "new", "title": "New risk", "body": "Text."}]
    bad = check_company("X", _doc(risks, {"new": 2}, 1, 0))
    assert any("counts" in b for b in bad)


def test_an_edit_with_nothing_changed_and_a_dangling_link_are_caught():
    risks = [{"id": "a", "status": "edited", "title": "T", "old_title": "T",
              "diff": [["=", "Same."]]},
             {"id": "b", "status": "split", "title": "S", "body": "Text.",
              "link_title": "Not a risk"}]
    bad = check_company("X", _doc(risks, {"edited": 1, "split": 1}, 2, 1))
    assert any("no change" in b for b in bad)
    assert any("partner" in b for b in bad)


def test_duplicate_ids_are_caught():
    risks = [{"id": "a", "status": "new", "title": "One", "body": "x"},
             {"id": "a", "status": "new", "title": "Two", "body": "y"}]
    bad = check_company("X", _doc(risks, {"new": 2}, 2, 0))
    assert any("used 2 times" in b for b in bad)
