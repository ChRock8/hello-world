from d3helper import affixes, blizzard
from d3helper.builds import load_build
from d3helper.evaluator import evaluate

BUILD = load_build("ww_rend_barb")


def test_parse_tooltip_lines():
    text = """+712 Strength
Critical Hit Chance Increased by 6.0%
Critical Hit Damage Increased by 50.0%
Attack Speed Increased by 7.0%
Empty Socket"""
    a = affixes.parse(text)
    assert a["str"] == 712 and a["chc"] == 6.0 and a["chd"] == 50.0 and "ias" in a
    assert a["socket"] == 1


def test_parse_skill_and_physical_lines():
    a = affixes.parse("Increases Rend Damage by 15%\nPhysical skills deal 20% more damage\n+14% Life")
    assert set(a) == {"skill:rend", "physical_pct", "life_pct"}


def test_parse_shorthand():
    a = affixes.parse("chc chd socket x2 str")
    assert a == {"chc": None, "chd": None, "socket": 2, "str": None}


def test_perfect_gloves_equip_when_slot_empty():
    v = evaluate(BUILD, {"name": "Gauntlet of the Wastes", "affixes": affixes.parse("chc chd str ias area")})
    assert v.action == "EQUIP" and v.slot == "hands" and v.score == 100


def test_reroll_suggestion():
    v = evaluate(BUILD, {"name": "Gauntlet of the Wastes", "affixes": affixes.parse("chc chd str vit")})
    assert v.reroll and "Vitality" in v.reroll and "Attack Speed" in v.reroll


def test_ancient_upgrade_over_normal():
    current = {"hands": {"name": "Gauntlet of the Wastes", "quality": "normal", "score": 80}}
    v = evaluate(BUILD, {"name": "Gauntlet of the Wastes", "quality": "ancient",
                         "affixes": affixes.parse("chc chd str")}, current)
    assert v.action == "UPGRADE"


def test_worse_copy_is_salvage():
    current = {"hands": {"name": "Gauntlet of the Wastes", "quality": "ancient", "score": 90}}
    v = evaluate(BUILD, {"name": "Gauntlet of the Wastes", "quality": "ancient",
                         "affixes": affixes.parse("str vit")}, current)
    assert v.action == "SALVAGE" and "worse than yours" in v.headline


def test_keep_when_one_reroll_beats_current():
    current = {"hands": {"name": "Gauntlet of the Wastes", "quality": "ancient", "score": 80}}
    v = evaluate(BUILD, {"name": "Gauntlet of the Wastes", "quality": "ancient",
                         "affixes": affixes.parse("chc chd str vit")}, current)
    assert v.action == "KEEP" and "Vitality → Attack Speed" in v.headline


def test_roll_quality_counts():
    lo = evaluate(BUILD, {"name": "Gauntlet of the Wastes", "affixes": {"chc": 8.0, "chd": 35.0}})
    hi = evaluate(BUILD, {"name": "Gauntlet of the Wastes", "affixes": {"chc": 10.0, "chd": 50.0}})
    assert hi.score > lo.score


def test_goals_and_done_slot():
    perfect = {"chc": 10.0, "chd": 50.0, "str": 900, "ias": 7.0, "area_dmg": 24.0}
    v = evaluate(BUILD, {"name": "Gauntlet of the Wastes", "quality": "ancient", "affixes": {**perfect, "chc": 8.1}})
    assert not v.meets_goals and v.below_goal == ["Crit Chance 8.1 < 9.4"]
    # Wearing an ancient pair that meets every goal -> any other copy is salvage.
    current = {"hands": {"name": "Gauntlet of the Wastes", "quality": "ancient", "affixes": {**perfect, "area_dmg": None}}}
    v = evaluate(BUILD, {"name": "Gauntlet of the Wastes", "quality": "ancient",
                         "affixes": {"chc": 9.6, "chd": 49.0, "str": 800, "ias": 6.0}}, current)
    assert v.action == "SALVAGE" and "slot is done" in v.headline


def test_custom_goal_override():
    from d3helper.evaluator import merged_goals
    goals = merged_goals(BUILD, {"hands": {"chc": 9.9}})
    v = evaluate(BUILD, {"name": "Gauntlet of the Wastes", "affixes": {"chc": 9.5, "chd": 50.0}}, goals=goals)
    assert v.below_goal == ["Crit Chance 9.5 < 9.9"]


def test_headline_always_set():
    for item in [{"name": "Ambo's Pride"}, {"name": "Random", "type": "Rare Gloves", "rarity": "rare"},
                 {"name": "Immortal King's Triumph", "type": "Set Helm"}, {"name": "Focus"}, {"name": "???"}]:
        assert evaluate(BUILD, {"affixes": {}, **item}).headline


def test_off_build_legendary_salvage():
    v = evaluate(BUILD, {"name": "Immortal King's Triumph", "type": "Set Helm", "affixes": {}})
    assert v.action == "SALVAGE" and "Helm of the Wastes" in v.reasons[0]


def test_cube_item():
    assert evaluate(BUILD, {"name": "Ambo's Pride", "affixes": {}}).action == "CUBE"
    assert evaluate(BUILD, {"name": "Ambo's Pride", "affixes": {}}, cube_done={"Ambo's Pride"}).action == "SALVAGE"


def test_flex_bracers_scored_by_type():
    v = evaluate(BUILD, {"name": "Some Bracers", "type": "Legendary Bracers", "affixes": affixes.parse("phys chc str")})
    assert v.slot == "bracers" and v.action == "EQUIP"


def test_blizzard_parse_items():
    data = {"head": {"name": "Helm of the Wastes", "typeName": "Ancient Set Helm",
                     "attributes": {"primary": [{"text": "+700 Strength"}], "secondary": []}},
            "leftFinger": {"name": "Focus", "typeName": "Set Ring"}}
    out = {i["slot"]: i for i in blizzard.parse_items(data)}
    assert out["head"]["quality"] == "ancient" and "Strength" in out["head"]["raw_text"]
    assert out["ring1"]["name"] == "Focus"


def test_why_drops_repeated_action_word():
    from d3helper.evaluator import Verdict
    assert Verdict("SALVAGE", headline="Salvage - your gloves slot is done.").why == "Your gloves slot is done."
    assert Verdict("UPGRADE", headline="Wear it - ancient beats yours.").why == "Wear it - ancient beats yours."
