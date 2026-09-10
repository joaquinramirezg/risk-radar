import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from extract_item1a import extract  # noqa: E402

BODY = ("We face many risks. " * 300)


def _filing(body: str) -> str:
    # Mimics a real 10-K: a table of contents that also says "Item 1A."
    return f"""<html><head><style>p{{}}</style></head><body>
    <table><tr><td>Item 1A.</td><td>Risk Factors</td><td>12</td></tr>
    <tr><td>Item 1B.</td><td>Unresolved Staff Comments</td><td>34</td></tr></table>
    <p>Item 1A. Risk Factors</p>
    <p>{body}</p>
    <p>Item 1B. Unresolved Staff Comments</p>
    <p>None.</p></body></html>"""


def test_anchors_past_the_table_of_contents():
    got, err = extract(_filing(BODY))
    assert not err
    assert "We face many risks." in got
    assert "Unresolved Staff Comments" not in got
    assert len(got) > 4000


def test_refuses_a_truncated_extract_instead_of_writing_it():
    got, err = extract(_filing("Too short."))
    assert got == ""
    assert "too short" in err


def test_reports_a_missing_section_rather_than_guessing():
    got, err = extract("<html><body><p>Item 2. Properties</p></body></html>")
    assert got == ""
    assert "no 'Item 1A" in err


def test_script_and_style_content_is_dropped():
    got, _ = extract(_filing(BODY).replace("<body>", "<body><script>var x=1;</script>"))
    assert "var x=1" not in got
