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


def test_worse_copy_is_keep_not_upgrade():
    current = {"hands": {"name": "Gauntlet of the Wastes", "quality": "ancient", "score": 90}}
    v = evaluate(BUILD, {"name": "Gauntlet of the Wastes", "quality": "ancient",
                         "affixes": affixes.parse("str vit")}, current)
    assert v.action == "KEEP"


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
