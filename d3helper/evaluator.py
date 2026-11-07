"""Decide what to do with an item for the active build."""
from dataclasses import dataclass, field

from .affixes import label

# Item type words seen on tooltips -> build slot(s).
TYPE_SLOTS = [
    ("helm", ["head"]), ("shoulder", ["shoulders"]), ("pauldron", ["shoulders"]),
    ("chest", ["chest"]), ("cuirass", ["chest"]), ("glove", ["hands"]), ("gauntlet", ["hands"]),
    ("bracer", ["bracers"]), ("belt", ["waist"]), ("pants", ["legs"]), ("tasset", ["legs"]),
    ("boot", ["feet"]), ("sabaton", ["feet"]), ("amulet", ["neck"]), ("ring", ["ring1", "ring2"]),
    ("weapon", ["main_hand", "off_hand"]), ("sword", ["main_hand", "off_hand"]),
    ("axe", ["main_hand", "off_hand"]), ("mace", ["main_hand", "off_hand"]),
]

QUALITY_RANK = {"normal": 0, "ancient": 1, "primal": 2}


@dataclass
class Verdict:
    action: str                 # EQUIP, UPGRADE, KEEP, CUBE, SALVAGE, CHECK
    slot: str | None = None
    score: int = 0
    reasons: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    reroll: str | None = None


def _norm(name: str) -> str:
    return "".join(c for c in (name or "").lower() if c.isalnum())


def find_slots(build: dict, name: str, item_type: str = "") -> list:
    """Slots this item is the build's pick for; else slots its type could fit."""
    n = _norm(name)
    exact = [s for s, spec in build["slots"].items() if spec.get("item") and _norm(spec["item"]) == n]
    if exact:
        return exact
    t = (item_type or name or "").lower()
    for word, slots in TYPE_SLOTS:
        if word in t:
            return slots
    return []


def score_affixes(weights: dict, affixes: dict) -> tuple[int, list, str | None]:
    """0-100 score: share of the slot's wanted affix weight this item has."""
    if not weights:
        return 0, [], None
    total = sum(weights.values())
    got = sum(w for k, w in weights.items() if k in affixes)
    missing = sorted((k for k in weights if k not in affixes), key=lambda k: -weights[k])
    junk = [k for k in affixes if k not in weights]
    reroll = None
    if missing:
        if junk:
            reroll = f"Enchant {label(junk[0])} → {label(missing[0])}"
        elif len(missing) == 1:
            reroll = f"Only missing {label(missing[0])}"
    return round(100 * got / total), missing, reroll


def evaluate(build: dict, item: dict, equipped: dict | None = None, cube_done: set | None = None) -> Verdict:
    """item: {name, type, quality, affixes{key: value}}. equipped: slot -> stored item dict."""
    equipped = equipped or {}
    cube_done = {_norm(c) for c in (cube_done or set())}
    name = item.get("name", "")
    affixes = item.get("affixes") or {}
    quality = (item.get("quality") or "normal").lower()

    # Is it a cube power for this build?
    for cube_slot, cube_item in (build.get("cube") or {}).items():
        if _norm(cube_item) == _norm(name):
            if _norm(cube_item) in cube_done:
                return Verdict("SALVAGE", reasons=[f"{cube_item} power is already in your cube."])
            return Verdict("CUBE", reasons=[f"Extract {cube_item} into Kanai's Cube ({cube_slot} slot)."])

    slots = find_slots(build, name, item.get("type", ""))
    build_pick = [s for s in slots if build["slots"][s].get("item") and
                  _norm(build["slots"][s]["item"]) == _norm(name)]
    flex = [s for s in slots if not build["slots"][s].get("item")]

    if not build_pick and not flex:
        if slots:
            wanted = ", ".join(build["slots"][s]["item"] for s in slots)
            return Verdict("SALVAGE", slot=slots[0], reasons=[f"Build uses {wanted} in this slot."])
        return Verdict("CHECK", reasons=["Couldn't tell which slot this is. Add the item type."])

    candidates = build_pick or flex
    best = None
    for slot in candidates:
        spec = build["slots"][slot]
        score, missing, reroll = score_affixes(spec.get("affixes", {}), affixes)
        current = equipped.get(slot)
        v = Verdict("EQUIP", slot=slot, score=score, missing=[label(m) for m in missing], reroll=reroll)
        if current is None:
            v.reasons.append("You don't have this slot filled yet.")
        else:
            cur_q = QUALITY_RANK.get((current.get("quality") or "normal").lower(), 0)
            new_q = QUALITY_RANK.get(quality, 0)
            cur_score = current.get("score") or 0
            if new_q > cur_q and score >= cur_score - 15:
                v.action = "UPGRADE"
                v.reasons.append(f"Higher quality ({quality}) than your current {current.get('quality') or 'normal'}.")
            elif new_q == cur_q and score > cur_score + 5:
                v.action = "UPGRADE"
                v.reasons.append(f"Better rolls: {score} vs {cur_score} on your current one.")
            elif new_q < cur_q:
                v.action = "SALVAGE"
                v.reasons.append("Your equipped one is a higher quality.")
            else:
                v.action = "KEEP"
                v.reasons.append(f"Not better than current ({cur_score}). Keep as a reroll/augment base or salvage.")
        if spec.get("verify"):
            v.reasons.append("Note: this slot's recommendation is unverified - check your guide.")
        if best is None or (v.action in ("EQUIP", "UPGRADE") and best.action not in ("EQUIP", "UPGRADE")):
            best = v
    return best
