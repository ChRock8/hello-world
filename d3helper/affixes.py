"""Turn item text into canonical affix keys.

Accepts either real tooltip lines ("Critical Hit Chance Increased by 6.0%")
or quick shorthand typed by hand ("chc chd socket str").
"""
import re

LABELS = {
    "str": "Strength", "vit": "Vitality", "chc": "Crit Chance", "chd": "Crit Damage",
    "ias": "Attack Speed", "cdr": "Cooldown Reduction", "rcr": "Resource Cost Reduction",
    "life_pct": "% Life", "physical_pct": "Physical %", "skill:whirlwind": "Whirlwind %",
    "skill:rend": "Rend %", "socket": "Socket", "damage_pct": "+% Damage",
    "elite_dmg": "Elite Damage", "area_dmg": "Area Damage", "all_res": "All Resist",
    "armor": "Armor", "life_on_hit": "Life per Hit", "dex": "Dexterity", "int": "Intelligence",
}

# (regex, key) checked in order against each tooltip line.
_LINE_RULES = [
    (r"empty socket|^socket", "socket"),
    (r"critical hit chance", "chc"),
    (r"critical hit damage", "chd"),
    (r"attack speed", "ias"),
    (r"cooldown", "cdr"),
    (r"resource cost", "rcr"),
    (r"physical skills deal", "physical_pct"),
    (r"whirlwind damage", "skill:whirlwind"),
    (r"rend damage", "skill:rend"),
    (r"damage against elites", "elite_dmg"),
    (r"area damage", "area_dmg"),
    (r"resistance to all elements", "all_res"),
    (r"life per hit", "life_on_hit"),
    (r"^\+?[\d.,]+%? life$|\d% life\b", "life_pct"),
    (r"\bstrength\b", "str"),
    (r"\bvitality\b", "vit"),
    (r"\bdexterity\b", "dex"),
    (r"\bintelligence\b", "int"),
    (r"^\+\s*[\d,]+ armor", "armor"),  # bonus armor only, not the item's base armor
    (r"^\+?\d+% damage$", "damage_pct"),
]

_SHORTHAND = {
    "str": "str", "strength": "str", "vit": "vit", "vitality": "vit",
    "chc": "chc", "cc": "chc", "crit": "chc", "chd": "chd", "cd": "chd", "critdmg": "chd",
    "ias": "ias", "as": "ias", "cdr": "cdr", "rcr": "rcr", "life": "life_pct", "life%": "life_pct",
    "phys": "physical_pct", "physical": "physical_pct", "ww": "skill:whirlwind",
    "whirlwind": "skill:whirlwind", "rend": "skill:rend", "socket": "socket", "soc": "socket",
    "sockets": "socket", "dmg": "damage_pct", "damage": "damage_pct", "elite": "elite_dmg",
    "area": "area_dmg", "ad": "area_dmg", "allres": "all_res", "ar": "all_res",
    "armor": "armor", "loh": "life_on_hit", "dex": "dex", "int": "int",
}

_NUM = re.compile(r"[+]?([\d][\d,]*\.?\d*)")


def _value(line: str):
    m = _NUM.search(line)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_line(line: str):
    """Return (key, value) for one tooltip line, or None if unrecognised."""
    text = line.strip().lower()
    if not text:
        return None
    for pattern, key in _LINE_RULES:
        if re.search(pattern, text):
            return key, (None if key == "socket" else _value(text))
    return None


def parse_lines(lines) -> dict:
    """Parse tooltip lines (one stat per line), e.g. from OCR."""
    out: dict = {}
    for line in lines:
        hit = parse_line(line)
        if hit:
            key, val = hit
            if key == "socket":
                out[key] = out.get(key, 0) + 1
            else:
                out[key] = val
    return out


def parse_shorthand(text: str) -> dict:
    """'chc chd socket x2 str' -> {'chc': None, 'chd': None, 'socket': 2, 'str': None}"""
    out: dict = {}
    tokens = re.split(r"[,\s;/]+", text.strip().lower())
    for i, tok in enumerate(tokens):
        m = re.fullmatch(r"(\d*)x?([a-z%:]+?)(?:x?(\d+))?", tok)
        if not m:
            continue
        key = _SHORTHAND.get(m.group(2))
        if not key:
            continue
        count = m.group(1) or m.group(3)
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if not count and re.fullmatch(r"x\d+", nxt):
            count = nxt[1:]
        if key == "socket":
            out[key] = out.get(key, 0) + int(count or 1)
        else:
            out[key] = None
    return out


def parse(text: str) -> dict:
    """Parse free text. Lines that look like tooltip text win; otherwise shorthand."""
    lines = [l for l in text.splitlines() if l.strip()]
    tooltip_like = [l for l in lines if len(l.split()) >= 3]
    if tooltip_like:
        out = parse_lines(lines)
        if out:
            return out
    return parse_shorthand(text)


def label(key: str) -> str:
    return LABELS.get(key, key)
