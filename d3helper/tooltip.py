"""Find Diablo 3 item tooltips in OCR output and turn them into items.

Works on text lines with screen positions (from ocr.recognize), so it can be
tested without the game. Layout assumptions (1080p-ish, scales with height):
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

from . import affixes

TYPES = [
    "helm", "spirit stone", "voodoo mask", "wizard hat", "shoulders", "chest armor", "cloak",
    "gloves", "bracers", "belt", "mighty belt", "pants", "boots", "amulet", "ring",
    "mighty weapon", "axe", "sword", "mace", "spear", "dagger", "fist weapon", "flail",
    "scythe", "ceremonial knife", "wand", "hand crossbow", "bow", "crossbow", "polearm",
    "staff", "daibo", "shield", "crusader shield", "mojo", "orb", "source", "quiver",
    "phylactery",
]
TYPE_RE = re.compile(
    r"^(?P<q>primal ancient |ancient )?(?P<r>legendary |set |rare |magic |crafted )?"
    r"(?:one-handed |two-handed |2-handed )?(?P<t>" + "|".join(sorted(TYPES, key=len, reverse=True)) + r")s?\b",
    re.I)
STOP_RE = re.compile(r"^\(\d\)|required level|account bound|durability|item level|sell value|"
                     r"^level \d+$|^unidentified|crafted by|^\d+ of \d+ set", re.I)
SKIP_RE = re.compile(r"^(primary|secondary)$|per second|^armor$|^[\d,.]+$|^[\d,.]+\s*-\s*[\d,.]+", re.I)

TOOLTIP_WIDTH = 0.36  # tooltip width as a share of screen height


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


def type_match(text: str):
    return TYPE_RE.match(_clean(text))


def _read_one(lines, ti, width, med_h, color_of):
    tl = lines[ti]
    m = type_match(tl.text)
    guess_cx = tl.x + 0.25 * width  # type line starts right of the item icon
    above = [l for l in lines
             if l.bottom <= tl.y + med_h * 0.5 and tl.y - l.y <= 6 * med_h
             and abs(l.cx - guess_cx) <= 0.4 * width
             and not type_match(l.text) and "equipped" not in l.text.lower()
             and not SKIP_RE.search(_clean(l.text))]
    if not above:
        return None
    name_line = max(above, key=lambda l: l.y)
    name = _clean(name_line.text)
    # Two-line names: another centred line right above.
    for l in above:
        if l is not name_line and 0 < name_line.y - l.y <= 1.8 * med_h and abs(l.cx - name_line.cx) < 0.2 * width:
            name = f"{_clean(l.text)} {name}"
    cx = name_line.cx
    left, right = cx - width / 2, cx + width / 2

    equipped = any("equipped" in l.text.lower() and left <= l.cx <= right
                   and name_line.y - 5 * med_h <= l.y <= tl.bottom + 2 * med_h for l in lines)

    body = sorted((l for l in lines if l.y > tl.y + 0.5 * med_h and left <= l.cx <= right),
                  key=lambda l: l.y)
    texts = [_clean(l.text).lower() for l in body]
    if "primary" in texts:
        body = body[texts.index("primary") + 1:]

    stats, power, last_bottom = [], [], tl.bottom
    for l in body:
        text = _clean(l.text)
        if STOP_RE.search(text):
            if re.match(r"^\(\d\)", text) and stats and not affixes.parse_line(stats[-1]):
                stats.pop()  # the set's name sits right above its bonuses
            break
        if stats and l.y - last_bottom > 5 * med_h:
            break
        last_bottom = l.bottom
        if SKIP_RE.search(text):
            continue
        if color_of and color_of(l) == "orange":
            power.append(text)
            continue
        stats.append(text)

    top = int(name_line.y - 1.5 * med_h)
    q = (m.group("q") or "").strip().lower()
    return Tooltip(
        name=name,
        type=_clean(tl.text),
        quality="primal" if q.startswith("primal") else ("ancient" if q else "normal"),
        rarity=(m.group("r") or "unknown").strip().lower(),
        affix_lines=stats,
        legendary_power=" ".join(power),
        box=(int(left), top, int(width), int(last_bottom + med_h - top)),
        equipped=equipped,
    )


def find_tooltips(lines, screen_h: int, color_of=None) -> list[Tooltip]:
    if not lines:
        return []
    width = TOOLTIP_WIDTH * screen_h
    med_h = statistics.median(l.h for l in lines) or 16
    found = []
    for i, l in enumerate(lines):
        if type_match(l.text):
            tip = _read_one(lines, i, width, med_h, color_of)
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

    hovered_pool = [t for t in tooltips if not t.equipped] or tooltips
    hovered = min(hovered_pool, key=dist)
    return hovered, [t for t in tooltips if t is not hovered and t.equipped]


def color_sampler(img):
    """Return a function classifying a line's text colour from the screenshot."""
    def color_of(line) -> str:
        crop = img.crop((line.x, line.y, line.x + max(line.w, 1), line.y + max(line.h, 1))).convert("RGB")
        raw = crop.tobytes()
        px = [raw[i:i + 3] for i in range(0, len(raw), 3)]
        px = [p for p in px if sum(p) > 300]  # text pixels, not background
        if not px:
            return "other"
        r = sum(p[0] for p in px) / len(px)
        g = sum(p[1] for p in px) / len(px)
        b = sum(p[2] for p in px) / len(px)
        if r > 150 and r - b > 70 and r > g:
            return "orange"
        if b > r + 30 and b > g + 10:
            return "blue"
        if g > r + 20 and g > b:
            return "green"
        return "other"
    return color_of
