from d3helper import screen_resources as sr
from d3helper.ocr import OcrLine


def test_parse_number():
    assert sr.parse_number("1,234,567") == 1234567 and sr.parse_number("1.234.567") == 1234567
    assert sr.parse_number("Gold: 98 765") == 98765 and sr.parse_number("none") is None


def test_label_same_line_and_beside():
    lines = [OcrLine("Veiled Crystal 4,321", 100, 100, 200, 16),
             OcrLine("Arcane Dust", 100, 130, 100, 16), OcrLine("2,000", 260, 131, 50, 16),
             OcrLine("Blood Shards", 600, 900, 110, 16), OcrLine("640", 610, 920, 30, 16)]
    out = sr.read_resources(lines, (1920, 1080))
    assert out == {"veiled_crystal": 4321, "arcane_dust": 2000, "blood_shards": 640}


def test_region_from_calibration():
    prof = {"resources": {"gold": {"labels": [], "region": [0.70, 0.90, 0.80, 0.95]}}}
    lines = [OcrLine("1,234,567,890", 1400, 990, 120, 16), OcrLine("+15% Gold Find", 100, 100, 150, 16)]
    assert sr.read_resources(lines, (1920, 1080), prof) == {"gold": 1234567890}


def test_gold_find_stat_is_not_gold():
    lines = [OcrLine("+15% Gold Find", 100, 100, 150, 16)]
    assert "gold" not in sr.read_resources(lines, (1920, 1080))
