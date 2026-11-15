from pathlib import Path

import pytest

from build_radar import read_risks
from test_risks import BODY, WORDS, B, _doc


def _filing(n: int) -> str:
    return _doc("".join(f"<div><span {B}>Our {w} results could suffer.</span></div>"
                        f"<div>{w} {BODY}</div>" for w in WORDS[:n]))


def test_the_annual_report_is_read_when_the_10k_only_points_to_it(tmp_path: Path):
    # BNY, U.S. Bancorp and Wells Fargo put Item 1A in the annual report
    # exhibit; the 10-K itself has a stub.
    primary = tmp_path / "BK_10-K.htm"
    primary.write_text(_filing(2))
    primary.with_suffix(".annual.html").write_text(_filing(9))
    assert len(read_risks(primary)) == 9


def test_the_10k_wins_when_it_has_the_risk_factors(tmp_path: Path):
    primary = tmp_path / "AAPL_10-K.htm"
    primary.write_text(_filing(9))
    primary.with_suffix(".annual.html").write_text(_filing(3))
    assert len(read_risks(primary)) == 9


def test_no_item_1a_anywhere_raises(tmp_path: Path):
    primary = tmp_path / "X_10-K.htm"
    primary.write_text("<html><body><p>Nothing here.</p></body></html>")
    with pytest.raises(ValueError):
        read_risks(primary)
