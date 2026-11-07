"""'What should I do next?' - gear status + your materials -> a short to-do list
and what to farm.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from .affixes import label
from .builds import SLOT_LABELS
from .evaluator import canonical_name, check_goals, qrank, score_affixes

GAME = json.loads((Path(__file__).parent / "game_data.json").read_text(encoding="utf-8"))
RESOURCES = GAME["resources"]
RES_LABEL = {r["key"]: r["label"] for r in RESOURCES}
SLOT_KIND = {"neck": "amulet", "ring1": "ring", "ring2": "ring", "main_hand": "weapon", "off_hand": "weapon"}
TYPE_NAME = {"head": "helm", "shoulders": "shoulders", "chest": "chest armor", "hands": "gloves",
             "bracers": "bracers", "waist": "belt", "legs": "pants", "feet": "boots", "neck": "amulet",
             "ring1": "ring", "ring2": "ring", "main_hand": "1-hand weapon", "off_hand": "1-hand weapon",
             "weapon": "1-hand weapon", "ring": "ring", "amulet": "amulet"}


@dataclass
class Option:
    text: str
    cost: dict = field(default_factory=dict)
    tries: int | None = None          # times you can afford it; None = no fixed cost
    short: dict = field(default_factory=dict)  # resource -> how many more you need for one try


@dataclass
class Step:
    priority: int
    title: str
    why: str
    options: list = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.options or any(o.tries is None or o.tries > 0 for o in self.options)


@dataclass
class Plan:
    steps: list
    farm: list
    warnings: list
    done_slots: int = 0


def _option(text, cost, res) -> Option:
    if not cost:
        return Option(text)
    tries = min(int(res.get(k, 0)) // v for k, v in cost.items())
    short = {k: v - int(res.get(k, 0)) for k, v in cost.items() if int(res.get(k, 0)) < v}
    return Option(text, cost, tries, short)


def _kadala(kind: str, res) -> Option:
    cat = kind if kind in ("ring", "amulet", "weapon") else "armor"
    price = GAME["kadala"][cat]
    return _option(f"Gamble {TYPE_NAME.get(kind, kind)} at Kadala ({price} shards a try, ~1 in 10 is legendary)",
                   {"blood_shards": price}, res)


def _recipe(key: str, text: str, res) -> Option:
    r = GAME["recipes"][key]
    return _option(f"{text} ({r['name']})", r["cost"], res)


def _find_options(kind: str, res, extra=()) -> list:
    return [*extra, _kadala(kind, res),
            _recipe("upgrade_rare", f"Kanai's Cube: upgrade a rare {TYPE_NAME.get(kind, kind)}", res)]


def make_plan(build, equipped: dict, items: list, cube_done, resources: dict, goals: dict) -> Plan:
    res = {k: int(v or 0) for k, v in (resources or {}).items()}
    cube_done = set(cube_done or ())
    stash = [i for i in items if not i.get("equipped")]

    def owned(name):
        mine = [i for i in stash if canonical_name(build, i["name"]) == name]
        return max(mine, key=lambda i: (qrank(i), i.get("score") or 0)) if mine else None

    set_sizes = {}
    for spec in build["slots"].values():
        if spec.get("set"):
            set_sizes[spec["set"]] = set_sizes.get(spec["set"], 0) + 1

    # Duplicates of set pieces you already wear can be converted into missing pieces.
    worn = {canonical_name(build, e["name"]) for e in equipped.values()}
    piece_set = {s["item"]: s["set"] for s in build["slots"].values() if s.get("set") and s.get("item")}
    spare_pool = [{**i, "_set": piece_set[canonical_name(build, i["name"])]} for i in stash
                  if canonical_name(build, i["name"]) in piece_set and canonical_name(build, i["name"]) in worn]

    steps, done = [], 0
    for slot, spec in build["slots"].items():
        target, where = spec.get("item"), SLOT_LABELS[slot]
        kind = SLOT_KIND.get(slot, slot)
        eq = equipped.get(slot)
        weights = spec.get("affixes", {})
        big_set = spec.get("set") and set_sizes.get(spec["set"], 0) >= 4

        if not target:
            if not eq:
                top = ", ".join(label(k) for k, _ in sorted(weights.items(), key=lambda kv: -kv[1])[:2])
                steps.append(Step(6, f"Fill your {where.lower()}", f"Any legendary with {top}.",
                                  [_kadala(kind, res)]))
            else:
                done += 1
            continue

        if not eq or canonical_name(build, eq["name"]) != target:
            have = owned(target)
            if have:
                steps.append(Step(1, f"Equip {target}", f"You have one in {have.get('location') or 'your stash'}."))
                continue
            extra = []
            if big_set:
                spare = next((i for i in spare_pool if i["_set"] == spec["set"]), None)
                if spare:
                    spare_pool.remove(spare)  # each spare can only be converted once
                    extra.append(_recipe("convert_set", f"Kanai's Cube: convert your spare {spare['name']}", res))
            why = f"Piece of your {spec['set']} set." if spec.get("set") else "Core item for your build."
            steps.append(Step(2 if big_set else (3 if spec.get("set") else 5), f"Get {target}", why,
                              _find_options(kind, res, extra)))
            continue

        aff = eq.get("affixes") or {}
        meets, below = check_goals(weights, aff, goals.get(slot, {}))
        if qrank(eq) == 0:
            steps.append(Step(7, f"Find an ancient {target}", "Ancients roll much higher numbers.",
                              [_recipe("reforge", f"Kanai's Cube: reforge your {target}", res),
                               *_find_options(kind, res)]))
        elif not meets:
            reroll = score_affixes(weights, aff, slot)[2]
            missing = [label(k) for k, w in weights.items() if w >= 3 and k not in aff]
            why = "; ".join(filter(None, [f"missing {', '.join(missing)}" if missing else "",
                                           ", ".join(below)]))
            opts = [Option(f"Mystic: {reroll} (gold + materials, gets pricier each try)")] if reroll else []
            opts.append(_recipe("reforge", f"Kanai's Cube: reforge it", res))
            steps.append(Step(8, f"Improve your {target}", why[:1].upper() + why[1:] + ".", opts))
        else:
            done += 1

    for cube_slot, name in (build.get("cube") or {}).items():
        if name in cube_done:
            continue
        have = owned(name)
        if have:
            steps.append(Step(1, f"Extract {name} in Kanai's Cube", f"You have one in {have.get('location') or 'your stash'}.",
                              [_recipe("extract", "Extract it", res)]))
        else:
            kind = GAME["cube_item_types"].get(name, "armor")
            steps.append(Step(4, f"Find {name}", f"Its power goes in your cube's {cube_slot} slot.",
                              _find_options(kind, res)))

    if not steps:
        steps.append(Step(9, "Augment your ancients", "Every slot is done. Kanai's Cube: Caldesann's Despair adds Strength."))
        steps.append(Step(9, "Level legendary gems and push Greater Rifts", "More damage, more blood shards."))

    steps.sort(key=lambda s: (s.priority, not s.ready))
    return Plan(steps, _farm_tips(steps, res), _warnings(res), done)


def _farm_tips(steps, res) -> list:
    """What's stopping the next few steps, and where to farm it."""
    needs: dict = {}
    for step in steps[:4]:
        if step.ready or not step.options:
            continue
        best = min(step.options, key=lambda o: sum(v / max(o.cost[k], 1) for k, v in o.short.items()) if o.cost else 99)
        for k, n in best.short.items():
            needs.setdefault(k, (n, step.title))
    tips = []
    for k, (n, title) in list(needs.items())[:3]:
        tips.append(f"Farm {RES_LABEL.get(k, k)}: {GAME['sources'].get(k, '')}. "
                    f"Need {n:,} more for \"{title}\".")
    if not tips and steps and steps[0].priority < 9:
        tips.append("You can afford your next steps - go spend!")
    return tips


def _warnings(res) -> list:
    out = []
    cap_cfg = GAME["shard_cap"]
    if res.get("highest_gr"):
        cap = cap_cfg["base"] + cap_cfg["per_gr"] * res["highest_gr"]
        if res.get("blood_shards", 0) >= 0.8 * cap:
            out.append(f"Blood shards {res['blood_shards']:,}/{cap:,}: spend them at Kadala before you hit the cap.")
    return out


def short_text(opt: Option) -> str:
    if opt.tries is None:
        return ""
    if opt.tries:
        return f"can do ×{opt.tries}"
    return "need " + ", ".join(f"{n:,} {RES_LABEL.get(k, k)}" for k, n in opt.short.items())
