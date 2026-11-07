"""Find Diablo 3 item tooltips in OCR output and turn them into items.

Works on text lines with screen positions (from ocr.recognize), so it can be
tested without the game. Every layout assumption comes from the screen profile
(d3helper/screen_profile.json). Expected layout:
  [Equipped]                 <- only on the comparison tooltip
  Item Name                  <- coloured banner, centred
  [icon] Ancient Set Gloves  <- type line
         1,234 Armor
  Primary
  +716 Strength ...
  Secondary
  ...
  (2) Set: ...               <- we stop here
"""
import re
import statistics
from dataclasses import dataclass, field

from . import affixes, profile


class Rules:
    """Compiled from a screen profile dict."""

    def __init__(self, prof: dict):
        t = prof["tooltip"]
        alt = lambda words: "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))  # noqa: E731
        self.type_re = re.compile(
            rf"^(?P<q>(?:{alt(t['quality_prefixes'])}) )?(?P<r>(?:{alt(t['rarity_words'])}) )?"
            rf"(?:one-handed |two-handed |2-handed )?(?P<t>{alt(t['types'])})s?\b", re.I)
        self.stop_re = re.compile("|".join(t["stop_patterns"]), re.I)
        self.skip_re = re.compile("|".join(t["skip_patterns"]), re.I)
        self.quality = {k.lower(): v for k, v in t["quality_prefixes"].items()}
        self.equipped_words = [w.lower() for w in t["equipped_words"]]
        self.section_words = [w.lower() for w in t["section_words"]]
        self.width = t["width"]
        self.icon_offset = t["icon_offset"]
        self.name_lines = t["name_max_lines_above"]
        self.name_offset = t["name_max_offset"]
        self.max_gap = t["max_gap_lines"]
        self.colors = prof["colors"]


_rules = (None, -1)


def rules() -> Rules:
    global _rules
    if _rules[1] != profile.version():
        _rules = (Rules(profile.load()), profile.version())
    return _rules[0]


@dataclass
class Tooltip:
    name: str
    type: str
    quality: str            # normal / ancient / primal
    rarity: str             # legendary / set / rare / magic / unknown
    affix_lines: list = field(default_factory=list)
    legendary_power: str = ""
    box: tuple = (0, 0, 0, 0)  # x, y, w, h on screen
    equipped: bool = False     # the "Equipped" comparison tooltip

    def to_item(self) -> dict:
        return {"name": self.name, "type": self.type, "quality": self.quality,
                "rarity": self.rarity, "affixes": affixes.parse_lines(self.affix_lines),
                "raw_text": "\n".join(self.affix_lines), "legendary_power": self.legendary_power}


def _clean(text: str) -> str:
    return re.sub(r"^[^A-Za-z0-9+(]+", "", text).strip()


def type_match(text: str, r: Rules | None = None):
    return (r or rules()).type_re.match(_clean(text))


def _is_equipped_label(text: str, r: Rules) -> bool:
    t = text.lower()
    return any(w in t for w in r.equipped_words)


def _read_one(lines, tl, width, med_h, r: Rules, color_of):
    m = type_match(tl.text, r)
    guess_cx = tl.x + r.icon_offset * width  # type line starts right of the item icon
    above = [l for l in lines
             if l.bottom <= tl.y + med_h * 0.5 and tl.y - l.y <= r.name_lines * med_h
             and abs(l.cx - guess_cx) <= r.name_offset * width
             and not type_match(l.text, r) and not _is_equipped_label(l.text, r)
             and not r.skip_re.search(_clean(l.text))]
    if not above:
        return None
    name_line = max(above, key=lambda l: l.y)
    name = _clean(name_line.text)
    for l in above:  # two-line names: another centred line right above
        if l is not name_line and 0 < name_line.y - l.y <= 1.8 * med_h and abs(l.cx - name_line.cx) < 0.2 * width:
            name = f"{_clean(l.text)} {name}"
    cx = name_line.cx
    left, right = cx - width / 2, cx + width / 2

    equipped = any(_is_equipped_label(l.text, r) and left <= l.cx <= right
                   and name_line.y - 5 * med_h <= l.y <= tl.bottom + 2 * med_h for l in lines)

    body = sorted((l for l in lines if l.y > tl.y + 0.5 * med_h and left <= l.cx <= right), key=lambda l: l.y)
    texts = [_clean(l.text).lower() for l in body]
    if r.section_words and r.section_words[0] in texts:
        body = body[texts.index(r.section_words[0]) + 1:]

    stats, power, last_bottom = [], [], tl.bottom
    for l in body:
        text = _clean(l.text)
        if r.stop_re.search(text):
            if re.match(r"^\(\d\)", text) and stats and not affixes.parse_line(stats[-1]):
                stats.pop()  # the set's name sits right above its bonuses
            break
        if stats and l.y - last_bottom > r.max_gap * med_h:
            break
        last_bottom = l.bottom
        if r.skip_re.search(text):
            continue
        if (color_of(l) if color_of else l.color) == "orange":
            power.append(text)
            continue
        stats.append(text)

    top = int(name_line.y - 1.5 * med_h)
    q = (m.group("q") or "").strip().lower()
    return Tooltip(
        name=name, type=_clean(tl.text),
        quality=r.quality.get(q, "normal"),
        rarity=(m.group("r") or "unknown").strip().lower(),
        affix_lines=stats, legendary_power=" ".join(power),
        box=(int(left), top, int(width), int(last_bottom + med_h - top)),
        equipped=equipped,
    )


def find_tooltips(lines, screen_h: int, color_of=None, r: Rules | None = None) -> list[Tooltip]:
    """All item tooltips on screen. Line colours come from line.color unless color_of is given."""
    r = r or rules()
    if not lines:
        return []
    width = r.width * screen_h
    med_h = statistics.median(l.h for l in lines) or 16
    found = []
    for l in lines:
        if type_match(l.text, r):
            tip = _read_one(lines, l, width, med_h, r, color_of)
            if tip and tip.name:
                found.append(tip)
    return found


def pick(tooltips: list[Tooltip], cursor) -> tuple[Tooltip | None, list[Tooltip]]:
    """Return (hovered tooltip, equipped comparison tooltips)."""
    if not tooltips:
        return None, []
    cx = cursor[0] if cursor else 0

    def dist(t):
        return abs(t.box[0] + t.box[2] / 2 - cx)

    hovered = min([t for t in tooltips if not t.equipped] or tooltips, key=dist)
    return hovered, [t for t in tooltips if t is not hovered and t.equipped]


def classify_color(rgb, c: dict) -> str:
    r, g, b = rgb
    if r > c["orange_min_red"] and r - b > c["orange_red_minus_blue"] and r > g:
        return "orange"
    if b > r + c["blue_over_red"] and b > g + 10:
        return "blue"
    if g > r + c["green_over_red"] and g > b:
        return "green"
    return "other"


def line_color(img, line, c: dict) -> str:
    crop = img.crop((line.x, line.y, line.x + max(line.w, 1), line.y + max(line.h, 1))).convert("RGB")
    raw = crop.tobytes()
    px = [raw[i:i + 3] for i in range(0, len(raw), 3)]
    px = [p for p in px if sum(p) > c["text_min_brightness"]]  # text pixels, not background
    if not px:
        return "other"
    n = len(px)
    return classify_color((sum(p[0] for p in px) / n, sum(p[1] for p in px) / n, sum(p[2] for p in px) / n), c)


def annotate_colors(lines, img, r: Rules | None = None):
    """Store each line's text colour on the line (kept in captures, so tests don't need the image)."""
    c = (r or rules()).colors
    for line in lines:
        line.color = line_color(img, line, c)
    return lines


def color_sampler(img, r: Rules | None = None):
    c = (r or rules()).colors
    return lambda line: line_color(img, line, c)
