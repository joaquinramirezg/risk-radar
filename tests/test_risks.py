import pytest

from harness.risks import split_risk_factors

B = 'style="font-weight:700"'
BODY = "This could hurt our revenue and margins in ways that are hard to predict. " * 4


def _doc(inner: str) -> str:
    return f"""<html><body>
    <table><tr><td>Item 1A.</td><td>Risk Factors</td><td>9</td></tr>
    <tr><td>Item 1B.</td><td>Unresolved Staff Comments</td><td>20</td></tr></table>
    <div><span {B}>Item 1A. Risk Factors</span></div>
    {inner}
    <div><span {B}>Item 1B. Unresolved Staff Comments</span></div><div>None.</div>
    </body></html>"""


def test_bold_titles_become_risks_under_their_category():
    rs = split_risk_factors(_doc(f"""
      <div><span {B}>Risks Related to Our Business</span></div>
      <div><span {B}>We depend on a few suppliers.</span></div><div>{BODY}</div>
      <div><span style="font-style:italic">Tariffs may raise our costs.</span></div>
      <div>{BODY}</div>
    """))
    assert [r.title for r in rs] == [
        "We depend on a few suppliers.", "Tariffs may raise our costs."]
    assert {r.category for r in rs} == {"Risks Related to Our Business"}


def test_run_in_bold_sentence_is_a_title():
    rs = split_risk_factors(_doc(f"<p><b>Competition is intense.</b> {BODY}</p>"))
    assert rs[0].title == "Competition is intense."
    assert rs[0].text.startswith("This could hurt")


def test_summary_bullets_and_page_furniture_are_not_risks():
    footer = "<div>Acme Corp | 2026 Form 10-K | 7</div>"
    rs = split_risk_factors(_doc(f"""
      <div><span {B}>Risk Factors Summary</span></div>
      <div>• We depend on a few suppliers.</div><div>{"Summary prose. " * 20}</div>
      {footer}<div><span {B}>We depend on a few suppliers.</span></div><div>{BODY}</div>
      {footer}{footer}
    """))
    assert [r.title for r in rs] == ["We depend on a few suppliers."]
    assert "Form 10-K" not in rs[0].text


def test_a_document_without_item_1a_raises():
    with pytest.raises(ValueError):
        split_risk_factors("<html><body><div>Item 2. Properties</div></body></html>")


IT = 'style="font-style:italic;font-weight:700"'


def test_short_headings_under_a_sentence_title_stay_inside_that_risk():
    # Microsoft: one titled risk, then italic subheadings, each with prose.
    rs = split_risk_factors(_doc(f"""
      <div>STRATEGIC AND COMPETITIVE RISKS</div>
      <div><span {IT}>We face intense competition across all markets.</span></div>
      <div><span {IT}>Competition in the technology sector</span></div><div>{BODY}</div>
      <div><span {IT}>Business model competition</span></div><div>{BODY}</div>
      <div><span {IT}>Our AI strategy requires large investments.</span></div><div>{BODY}</div>
    """))
    assert [r.title for r in rs] == [
        "We face intense competition across all markets.",
        "Our AI strategy requires large investments."]
    assert "Business model competition" in rs[0].text
    assert {r.category for r in rs} == {"STRATEGIC AND COMPETITIVE RISKS"}


def test_colon_leads_are_sections_of_the_risk_above():
    rs = split_risk_factors(_doc(f"""
      <div><span {B}>We are subject to many laws.</span></div><div>{BODY}</div>
      <p><b>Anti-corruption:</b> {BODY}</p>
      <p><b>Cybersecurity:</b> {BODY}</p>
    """))
    assert [r.title for r in rs] == ["We are subject to many laws."]
    assert "Anti-corruption:" in rs[0].text


def test_a_category_introduction_is_not_a_risk():
    # Exxon: a heading, an intro paragraph, then run-in titled risks.
    rs = split_risk_factors(_doc(f"""
      <div><span {B}>Supply and Demand</span></div><div>{BODY}</div>
      <p><b>Economic conditions.</b> {BODY}</p>
      <p><b>Other market factors.</b> {BODY}</p>
    """))
    assert [r.title for r in rs] == ["Economic conditions.", "Other market factors."]
    assert {r.category for r in rs} == {"Supply and Demand"}


def test_a_topic_heading_with_only_prose_is_still_a_risk():
    # Pfizer: capitals heading, prose, next heading. No titled risks inside.
    rs = split_risk_factors(_doc(f"""
      <div><span {B}>MANAGED CARE TRENDS</span></div><div>{BODY}</div>
      <div><span {B}>PATENT PROTECTION</span></div><div>{BODY}</div>
    """))
    assert [r.title for r in rs] == ["MANAGED CARE TRENDS", "PATENT PROTECTION"]


IT = 'style="font-style:italic"'


def test_dash_and_unpunctuated_run_in_titles():
    rs = split_risk_factors(_doc(f"""
      <p><b>We transport hazardous materials</b> – {BODY}</p>
      <p><b>Chevron is exposed to changing prices</b> {BODY}</p>
      <p><b>Note</b> that {BODY}</p>
    """))
    assert [r.title for r in rs] == [
        "We transport hazardous materials", "Chevron is exposed to changing prices"]
    assert rs[0].text.startswith("This could hurt")


def test_italic_body_section_uses_bold_for_titles():
    rs = split_risk_factors(_doc(f"""
      <div><span {B};font-style:italic">Pricing pressure hurts revenue.</span></div>
      <div><span {IT}>{BODY}</span></div>
      <div><span {B};font-style:italic">We may lose exclusivity early.</span></div>
      <div><span {IT}>{BODY}</span></div>
    """.replace(f'{B};', 'style="font-weight:700;')))
    assert [r.title for r in rs] == [
        "Pricing pressure hurts revenue.", "We may lose exclusivity early."]


def test_underlined_titles_count_as_emphasis():
    u = 'style="font-weight:400;text-decoration:underline"'
    rs = split_risk_factors(_doc(f"<div><span {u}>Our margins vary.</span></div><div>{BODY}</div>"))
    assert rs[0].title == "Our margins vary."


def test_cross_references_and_notices_are_not_titles():
    rs = split_risk_factors(_doc(f"""
      <div><span {B}>Reserves may prove inadequate.</span></div><div>{BODY}</div>
      <div><span {IT}>For additional information, see Item 7.</span></div>
      <div><span {B}>Reinsurance may be unavailable.</span></div><div>{BODY}</div>
      <div><span {B}>Cautionary Factors that May Affect Future Results</span></div><div>{BODY}</div>
    """))
    assert [r.title for r in rs] == [
        "Reserves may prove inadequate.", "Reinsurance may be unavailable."]
    assert rs[0].text.endswith("see Item 7.")


def test_section_without_item_label_ends_at_next_section():
    body = "".join(f"<p><b>Risk number {i} could hurt us.</b> {BODY * 4}</p>" for i in range(5))
    html = f"""<html><body><p>Risk Factors</p><p>24</p>
      <p><b>RISK FACTORS.</b> The following discussion covers material risks. {BODY}</p>
      <p><b>STRATEGIC RISKS.</b> Strategic risk relates to our plans. {BODY}</p>
      {body}
      <p><b>LEGAL PROCEEDINGS.</b> Refer to Note 24 for {BODY}</p></body></html>"""
    rs = split_risk_factors(html)
    assert len(rs) == 5
    assert {r.category for r in rs} == {"STRATEGIC RISKS"}


def test_a_summary_list_under_a_heading_is_not_a_risk():
    titles = ["Our suppliers may fail to deliver parts on time and at the agreed price.",
              "Rising interest rates could raise our borrowing costs and cut demand.",
              "A cyberattack on our systems could disrupt operations and expose data."]
    summary = "".join(f"<div>• {t}</div>" for t in titles)
    risks = "".join(f"<div><span {B}>{t}</span></div><div>{BODY}</div>" for t in titles)
    rs = split_risk_factors(_doc(f"<div><span {B}>Operational Risks</span></div>{summary}{risks}"))
    assert [r.title for r in rs] == titles


WORDS = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima".split()


def test_a_larger_font_marks_titles_when_nothing_is_emphasized():
    # Intel's layout: titles in 12pt, body in 9pt, no bold, italic or underline.
    big, small = 'style="font-size:12pt"', 'style="font-size:9pt"'
    rs = split_risk_factors(_doc("".join(
        f'<div><span {big}>Our {w} results could suffer.</span></div>'
        f'<div><span {small}>{w} {BODY}</span></div>' for w in WORDS[:9])))
    assert [r.title for r in rs] == [f"Our {w} results could suffer." for w in WORDS[:9]]


def test_a_colon_heading_on_its_own_line_stays_in_the_risk_above():
    rs = split_risk_factors(_doc(f"""
      <div><span {B}>We face competition.</span></div><div>{BODY}</div>
      <div><span {B}>Industry-Wide Factors:</span></div><div>{WORDS[0]} {BODY}</div>
      <div><span {B}>We may lose staff.</span></div><div>{WORDS[1]} {BODY}</div>
    """))
    assert [r.title for r in rs] == ["We face competition.", "We may lose staff."]
    assert "Industry-Wide Factors:" in rs[0].text
