"""Decide what to do with an item for the active build.

Every verdict comes with a one-line `headline` - the whole decision in plain words.
"""
import difflib
from dataclasses import dataclass, field

from .affixes import fmt, label, roll_quality, roll_range
from .builds import SLOT_LABELS

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
GOAL_POINT = 0.7  # default goal: 70% of the way from the worst to the best roll


@dataclass
class Verdict:
    action: str                 # EQUIP, UPGRADE, KEEP, CUBE, SALVAGE, CHECK, EQUIPPED
    slot: str | None = None
    score: int = 0
    headline: str = ""
    reasons: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    have: list = field(default_factory=list)
    below_goal: list = field(default_factory=list)
    reroll: str | None = None
    name: str = ""
    meets_goals: bool = False

    @property
    def why(self) -> str:
        """Headline without a leading word that just repeats the action ("Salvage - ...")."""
        head, sep, rest = self.headline.partition(" - ")
        return rest[:1].upper() + rest[1:] if sep and head.lower() == self.action.lower() else self.headline


def _norm(name: str) -> str:
    return "".join(c for c in (name or "").lower() if c.isalnum())


def qrank(item) -> int:
    return QUALITY_RANK.get((item.get("quality") or "normal").lower(), 0)


def canonical_name(build: dict, name: str) -> str:
    """Snap a slightly-misread name (OCR) to a build or cube item name."""
    known = [s["item"] for s in build["slots"].values() if s.get("item")]
    known += list((build.get("cube") or {}).values())
    by_norm = {_norm(k): k for k in known}
    if _norm(name) in by_norm:
        return by_norm[_norm(name)]
    hit = difflib.get_close_matches(_norm(name), list(by_norm), n=1, cutoff=0.82)
    return by_norm[hit[0]] if hit else name


def find_slots(build: dict, name: str, item_type: str = "") -> list:
    """Slots this item is the build's pick for; else slots its type could fit."""
    n = _norm(canonical_name(build, name))
    exact = [s for s, spec in build["slots"].items() if spec.get("item") and _norm(spec["item"]) == n]
    if exact:
        return exact
    t = (item_type or name or "").lower()
    for word, slots in TYPE_SLOTS:
        if word in t:
            return slots
    return []


# ---- goals -------------------------------------------------------------

def default_goals(build: dict) -> dict:
    """slot -> {affix: minimum value}. Must-have stats with a known range, plus any 'goals' in the build file."""
    out = {}
    for slot, spec in build["slots"].items():
        goals = {}
        for key, weight in spec.get("affixes", {}).items():
            rng = roll_range(key, slot)
            if weight >= 3 and rng:
                goal = rng[0] + GOAL_POINT * (rng[1] - rng[0])
                goals[key] = round(goal) if rng[1] - rng[0] >= 10 else round(goal, 1)
        goals.update(spec.get("goals", {}))
        out[slot] = goals
    return out


def merged_goals(build: dict, overrides: dict | None = None) -> dict:
    goals = default_goals(build)
    for slot, vals in (overrides or {}).items():
        goals.setdefault(slot, {}).update(vals)
    return goals


def check_goals(weights: dict, affixes: dict, goals: dict) -> tuple[bool, list]:
    """(meets all goals and has every must-have stat, list of 'X 8.1 < 9.5' misses)."""
    below = []
    for key, goal in (goals or {}).items():
        val = affixes.get(key)
        if key in affixes and val is not None and val < goal:
            below.append(f"{label(key)} {fmt(val)} < {fmt(goal)}")
    musts = all(k in affixes for k, w in weights.items() if w >= 3)
    return musts and not below, below


# ---- scoring -----------------------------------------------------------

def score_affixes(weights: dict, affixes: dict, slot: str = "") -> tuple[int, list, str | None, int]:
    """(score 0-100, missing stats, Mystic tip, score after that Mystic reroll).

    A wanted stat at its worst roll is worth 60% of a perfect roll.
    """
    if not weights:
        return 0, [], None, 0
    total = sum(weights.values())

    def worth(k):
        return weights[k] * (0.6 + 0.4 * roll_quality(k, affixes.get(k), slot))

    got = sum(worth(k) for k in weights if k in affixes)
    missing = sorted((k for k in weights if k not in affixes), key=lambda k: -weights[k])
    reroll, potential = None, got
    if missing:
        best = missing[0]
        junk = [k for k in affixes if k not in weights]
        if junk:
            reroll = f"Enchant {label(junk[0])} → {label(best)}"
            potential = got + weights[best]
        else:
            # The Mystic can change one stat: swap the weakest wanted one if that helps.
            present = [k for k in weights if k in affixes]
            weakest = min(present, key=worth) if present else None
            if weakest and weights[weakest] < weights[best]:
                reroll = f"Enchant {label(weakest)} → {label(best)}"
                potential = got - worth(weakest) + weights[best]
    return round(100 * got / total), missing, reroll, round(100 * potential / total)


# ---- the decision ------------------------------------------------------

def evaluate(build: dict, item: dict, equipped: dict | None = None, cube_done=None,
             goals: dict | None = None) -> Verdict:
    """item: {name, type, quality, rarity, affixes{key: value}}. equipped: slot -> item dict."""
    goals = goals if goals is not None else default_goals(build)
    v = _evaluate(build, item, equipped or {}, set(cube_done or ()), goals)
    v.name = canonical_name(build, item.get("name", ""))
    return v


def _evaluate(build, item, equipped, cube_done, goals) -> Verdict:
    cube_done = {_norm(c) for c in cube_done}
    name = canonical_name(build, item.get("name", ""))
    affixes = item.get("affixes") or {}
    quality = (item.get("quality") or "normal").lower()
    rarity = (item.get("rarity") or "").lower()

    for cube_slot, cube_item in (build.get("cube") or {}).items():
        if _norm(cube_item) == _norm(name):
            if _norm(cube_item) in cube_done:
                return Verdict("SALVAGE", headline="Salvage - this power is already in your cube.")
            return Verdict("CUBE", headline=f"Extract it in Kanai's Cube ({cube_slot} slot).",
                           reasons=["Mark it extracted on the dashboard afterwards."])

    slots = find_slots(build, name, item.get("type", ""))
    build_pick = [s for s in slots if build["slots"][s].get("item") and
                  _norm(build["slots"][s]["item"]) == _norm(name)]
    flex = [s for s in slots if not build["slots"][s].get("item")]

    if not build_pick and rarity in ("rare", "magic", "normal"):
        return Verdict("SALVAGE", slot=slots[0] if slots else None,
                       headline=f"Salvage - {rarity} items are only materials at level 70.")
    if not build_pick and not flex:
        if slots:
            wanted = " / ".join(dict.fromkeys(build["slots"][s]["item"] for s in slots))
            return Verdict("SALVAGE", slot=slots[0], headline="Salvage - your build doesn't use this.",
                           reasons=[f"You want {wanted} here."])
        return Verdict("CHECK", headline="Not sure what this is - press F9 to ask Claude.")

    results = [_judge_slot(build, slot, item, affixes, quality, equipped.get(slot), goals.get(slot, {}))
               for slot in (build_pick or flex)]
    order = {"EQUIP": 0, "UPGRADE": 0, "KEEP": 1}
    return min(results, key=lambda v: order.get(v.action, 2))


def _judge_slot(build, slot, item, affixes, quality, current, goals) -> Verdict:
    spec = build["slots"][slot]
    weights = spec.get("affixes", {})
    where = SLOT_LABELS.get(slot, slot).lower()
    score, missing, reroll, potential = score_affixes(weights, affixes, slot)
    meets, below = check_goals(weights, affixes, goals)
    have = sorted((k for k in affixes if k in weights), key=lambda k: -weights[k])
    v = Verdict("EQUIP", slot=slot, score=score, missing=[label(m) for m in missing],
                have=[label(h) for h in have], below_goal=below, reroll=reroll, meets_goals=meets)
    new_q = QUALITY_RANK.get(quality, 0)
    target = spec.get("item")

    if current is None:
        v.headline = f"Wear it - nothing in your {where} slot yet."
    elif target and canonical_name(build, current.get("name", "")) != target:
        v.action = "UPGRADE"
        v.headline = f"Wear it - replaces your off-build {where}."
    else:
        cur_q = qrank(current)
        cur_aff = current.get("affixes")
        if cur_aff:
            cur_score = score_affixes(weights, cur_aff, slot)[0]
            cur_done = cur_q >= 1 and check_goals(weights, cur_aff, goals)[0]
        else:
            cur_score, cur_done = current.get("score") or 0, False
        cur_name = current.get("quality") or "normal"
        if new_q > cur_q and score >= cur_score - 15:
            v.action, v.headline = "UPGRADE", f"Wear it - {quality} beats your {cur_name} one."
        elif new_q == cur_q and score > cur_score + 5:
            v.action, v.headline = "UPGRADE", f"Wear it - better rolls than yours ({score} vs {cur_score})."
        elif new_q < cur_q:
            v.action, v.headline = "SALVAGE", f"Salvage - yours is {cur_name}."
        elif cur_done:
            v.action, v.headline = "SALVAGE", f"Salvage - your {where} slot is done."
        elif reroll and potential > cur_score + 5:
            v.action, v.headline = "KEEP", f"Spare - {reroll} at the Mystic to beat yours."
        else:
            v.action, v.headline = "SALVAGE", f"Salvage - worse than yours ({score} vs {cur_score})."

    if v.action in ("EQUIP", "UPGRADE") and below:
        v.reasons.append("Below your goals: " + ", ".join(below))
    if spec.get("verify"):
        v.reasons.append("This slot's pick is unverified - check your guide.")
    return v
