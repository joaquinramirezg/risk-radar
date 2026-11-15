from harness.risks import RiskFactor
from harness.yoy import match, text_ratio, word_diff

BODY = "We sell products in many countries and currency moves affect results. " * 5


def _jaccard(a, b):
    def sim(x, y):
        sx, sy = set(x.lower().split()), set(y.lower().split())
        return len(sx & sy) / len(sx | sy)
    return [[sim(x, y) for y in b] for x in a]


def rf(title, body=BODY):
    return RiskFactor("", title, [body])


def test_each_new_risk_gets_exactly_one_status_and_removed_ones_are_listed():
    old = [rf("Currency risk"), rf("Pandemic risk", "Covid closed our stores for months. " * 8)]
    new = [rf("Currency risk"), rf("Tariff risk", "New tariffs raise the cost of imports. " * 8)]
    got = {(c.status, (c.new or c.old).title) for c in match(old, new, _jaccard)}
    assert got == {("unchanged", "Currency risk"), ("new", "Tariff risk"),
                   ("removed", "Pandemic risk")}


def test_an_old_risk_is_never_matched_twice():
    old = [rf("Currency risk")]
    new = [rf("Currency risk"), rf("Currency risk")]
    statuses = sorted(c.status for c in match(old, new, _jaccard))
    assert statuses == ["new", "unchanged"]


def test_small_edits_are_edited_and_big_ones_rewritten():
    base = "alpha beta gamma delta epsilon zeta eta theta iota kappa " * 4
    assert text_ratio(base, base) == 1.0
    edited = base.replace("gamma", "GAMMA-X", 1)
    assert 0.75 <= text_ratio(base, edited) < 0.98
    assert text_ratio(base, "completely different words here " * 10) < 0.75


def test_whitespace_reflow_is_not_an_edit():
    assert text_ratio("a  b\nc", "a b c") == 1.0


def test_word_diff_round_trips_both_sides():
    a, b = "we may face tariffs in China", "we may face new tariffs in Mexico"
    d = word_diff(a, b)
    assert "".join(t for op, t in d if op != "+") == a
    assert "".join(t for op, t in d if op != "-") == b


def test_identical_titles_match_even_when_the_body_was_rewritten():
    def never_similar(a, b):
        return [[0.0 for _ in b] for _ in a]
    old = [rf("PRICING AND REIMBURSEMENT", "Old text about rebates. " * 10)]
    new = [rf("Pricing and reimbursement", "Entirely new text on tariffs. " * 10)]
    (c,) = match(old, new, never_similar)
    assert c.status == "rewritten"
