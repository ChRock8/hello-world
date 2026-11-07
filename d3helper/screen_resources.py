"""Read gold, blood shards and materials off the screen (F6).

Two ways, both set in the screen profile:
- region: a box you drew on the Calibrate page; the number inside it is used.
- labels: words printed next to the number ("Death's Breath 1,234").
"""
import re

from . import profile

_NUM = re.compile(r"\d{1,3}(?:[,.  ]\d{3})+(?!\d)|\d+")


def parse_number(text: str):
    """'1,234,567' / '1.234.567' / '1 234' -> int; None if there's no number."""
    nums = [int(re.sub(r"[,.  ]", "", m)) for m in _NUM.findall(text or "")]
    return max(nums) if nums else None


def _in_region(line, region, w, h) -> bool:
    x0, y0, x1, y1 = region
    return x0 * w <= line.cx <= x1 * w and y0 * h <= line.y + line.h / 2 <= y1 * h


_NUMBER_ONLY = re.compile(r"^[\sx×:]*[\d][\d,.\u00a0 ]*$")


def _nearby_number(label_line, lines, h):
    """A bare number on the same row (preferred) or just below the label.
    Lines with words in them belong to some other label, so they're ignored."""
    best, best_rank = None, None
    for l in lines:
        if l is label_line or not _NUMBER_ONLY.match(l.text.strip()):
            continue
        same_row = abs((l.y + l.h / 2) - (label_line.y + label_line.h / 2)) <= label_line.h * 0.7
        below = 0 < l.y - label_line.bottom <= label_line.h * 2 and abs(l.cx - label_line.cx) <= label_line.w
        if not (same_row or below):
            continue
        d = abs(l.cx - label_line.cx) + abs(l.y - label_line.y)
        rank = (0 if same_row else 1, d)
        if d <= 0.3 * h and (best_rank is None or rank < best_rank):
            best, best_rank = parse_number(l.text), rank
    return best


def read_resources(lines, screen, prof: dict | None = None) -> dict:
    prof = prof or profile.load()
    w, h = screen
    out = {}
    for key, cfg in prof.get("resources", {}).items():
        if key.startswith("_") or not isinstance(cfg, dict):
            continue
        if cfg.get("region"):
            nums = [n for n in (parse_number(l.text) for l in lines if _in_region(l, cfg["region"], w, h)) if n is not None]
            if nums:
                out[key] = max(nums)
                continue
        for label in cfg.get("labels", []):
            for l in lines:
                low = l.text.lower()
                if label in low:
                    n = parse_number(low.replace(label, " "))
                    if n is None:
                        n = _nearby_number(l, lines, h)
                    if n is not None:
                        out[key] = n
                        break
            if key in out:
                break
    return out
