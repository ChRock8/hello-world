"""Every folder in tests/screens/ is a real (or synthetic) screen the reader must get right."""
import pytest

from d3helper import fixtures

CASES = fixtures.cases()


@pytest.mark.parametrize("folder", CASES, ids=[c.name for c in CASES])
def test_screen_reads_correctly(folder):
    problems, _ = fixtures.check_case(folder)
    assert not problems, "\n".join(problems)


def test_diff_reports_mistakes():
    exp = {"hovered": {"name": "Gauntlet of the Wastes", "quality": "ancient", "affixes": {"chc": 9.5, "chd": None}},
           "resources": {"gold": 100}}
    act = {"hovered": {"name": "Gauntiet of the Wastes", "quality": "normal", "rarity": "set",
                       "affixes": {"chc": 8.5, "str": 700}}, "equipped": [], "resources": {}}
    out = fixtures.diff(exp, act)
    assert "hovered quality: expected 'ancient', read 'normal'" in out
    assert "hovered stat missing: chd" in out and "hovered extra stat: str = 700" in out
    assert "hovered chc: expected 9.5, read 8.5" in out and "resource gold: expected 100, read None" in out
    assert not any("name" in line for line in out)  # OCR typo that snaps to the right item is fine


def test_make_case_round_trip(tmp_path):
    from d3helper.captures import Capture
    from tests import fake_screen as fs
    folder = fixtures.make_case(Capture((1920, 1080), fs.CURSOR, list(fs.LINES)), "x", root=tmp_path)
    problems, verified = fixtures.check_case(folder)
    assert problems == [] and not verified
