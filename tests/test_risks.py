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


I = 'style="font-style:italic;font-weight:700"'


def test_short_headings_under_a_sentence_title_stay_inside_that_risk():
    # Microsoft: one titled risk, then italic subheadings, each with prose.
    rs = split_risk_factors(_doc(f"""
      <div>STRATEGIC AND COMPETITIVE RISKS</div>
      <div><span {I}>We face intense competition across all markets.</span></div>
      <div><span {I}>Competition in the technology sector</span></div><div>{BODY}</div>
      <div><span {I}>Business model competition</span></div><div>{BODY}</div>
      <div><span {I}>Our AI strategy requires large investments.</span></div><div>{BODY}</div>
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
