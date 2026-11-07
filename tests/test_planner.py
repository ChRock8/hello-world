from d3helper.builds import load_build
from d3helper.evaluator import default_goals
from d3helper.planner import make_plan, short_text

BUILD = load_build("ww_rend_barb")
GOALS = default_goals(BUILD)


def plan(equipped=None, items=(), cube=(), res=None):
    return make_plan(BUILD, equipped or {}, list(items), cube, res or {}, GOALS)


def test_fresh_character_set_pieces_first_and_farm_tip():
    p = plan(res={"blood_shards": 10})
    assert p.steps[0].title == "Get Helm of the Wastes"
    assert p.steps[0].priority == 2 and not p.steps[0].ready
    assert any("Blood Shards" in f or "Death's Breath" in f for f in p.farm)


def test_affordability_counts_tries():
    p = plan(res={"blood_shards": 120})
    kadala = p.steps[0].options[0]
    assert kadala.tries == 4 and short_text(kadala) == "can do ×4"


def test_item_in_stash_is_equip_step():
    stash = [{"name": "Helm of the Wastes", "location": "Stash tab 2", "equipped": 0, "quality": "ancient"}]
    p = plan(items=stash)
    assert p.steps[0].title == "Equip Helm of the Wastes" and "Stash tab 2" in p.steps[0].why


def test_owned_cube_item_is_extract_step():
    p = plan(items=[{"name": "Ambo's Pride", "location": "Stash", "equipped": 0}])
    assert any(s.title == "Extract Ambo's Pride in Kanai's Cube" and s.priority == 1 for s in p.steps)
    assert not any("Ambo" in s.title for s in plan(cube={"Ambo's Pride"}).steps)


def test_spare_set_piece_offers_convert():
    worn = {"head": {"name": "Helm of the Wastes", "quality": "ancient", "affixes": {}}}
    spare = [{"name": "Helm of the Wastes", "equipped": 0, "location": "Stash"}]
    p = plan(equipped=worn, items=spare, res={"deaths_breath": 20, "forgotten_soul": 25})
    shoulders = next(s for s in p.steps if s.title == "Get Pauldrons of the Wastes")
    assert shoulders.options[0].text.startswith("Kanai's Cube: convert your spare Helm") and shoulders.options[0].tries == 2
    chest = next(s for s in p.steps if s.title == "Get Cuirass of the Wastes")
    assert "convert" not in chest.options[0].text  # the one spare is already spoken for


def test_non_ancient_and_below_goal_steps():
    eq = {"hands": {"name": "Gauntlet of the Wastes", "quality": "normal", "affixes": {"chc": 10, "chd": 50}},
          "neck": {"name": "Squirt's Necklace", "quality": "ancient",
                   "affixes": {"physical_pct": 20, "chd": 60, "chc": 10, "vit": None}}}
    titles = {s.title: s for s in plan(equipped=eq).steps}
    assert "Find an ancient Gauntlet of the Wastes" in titles
    neck = titles["Improve your Squirt's Necklace"]
    assert "Crit Damage 60 < 85" in neck.why and neck.options[0].text.startswith("Mystic: Enchant Vitality")


def test_everything_done_moves_to_endgame():
    perfect = {}
    for slot, spec in BUILD["slots"].items():
        perfect[slot] = {"name": spec.get("item") or "Any", "quality": "ancient",
                         "affixes": {k: None for k in spec["affixes"]}}
    p = plan(equipped=perfect, cube=set(BUILD["cube"].values()))
    assert p.done_slots == 13 and p.steps[0].title == "Augment your ancients"


def test_shard_cap_warning():
    assert plan(res={"blood_shards": 1000, "highest_gr": 60}).warnings  # cap 1100
    assert not plan(res={"blood_shards": 100, "highest_gr": 60}).warnings
