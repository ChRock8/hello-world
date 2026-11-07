import queue

import pytest

from d3helper import tooltip
from d3helper.overlay_layout import place_card
from tests import fake_screen as fs


def test_finds_hovered_and_equipped_tooltips():
    tips = tooltip.find_tooltips(fs.LINES, 1080, fs.color_of)
    hovered, compares = tooltip.pick(tips, fs.CURSOR)
    assert hovered.name == "Gauntiet of the Wastes" and not hovered.equipped
    assert hovered.quality == "ancient" and hovered.rarity == "set"
    assert len(compares) == 1 and compares[0].quality == "normal"


def test_hovered_stats_skip_armor_power_and_set_bonus():
    hovered, _ = tooltip.pick(tooltip.find_tooltips(fs.LINES, 1080, fs.color_of), fs.CURSOR)
    item = hovered.to_item()
    assert set(item["affixes"]) == {"chc", "chd", "str", "ias"}
    assert item["affixes"]["chc"] == 9.5           # not overwritten by the orange power line
    assert "Gain 1%" in hovered.legendary_power


def test_type_line_variants():
    m = tooltip.type_match("Primal Ancient Legendary Mighty Belt")
    assert m.group("q").strip().lower() == "primal ancient" and m.group("t").lower() == "mighty belt"
    assert tooltip.type_match("Set Mighty Weapon 1-Hand")
    assert not tooltip.type_match("Ringing bells")
    assert not tooltip.type_match("Critical Hit Chance Increased by 6%")


def test_no_tooltip_when_nothing_hovered():
    assert tooltip.find_tooltips(fs.INVENTORY_NOISE, 1080) == []


def test_card_placement():
    # room above the tooltip
    assert place_card((1000, 400, 390, 400), 300, 150, 1920, 1080) == (1045, 242)
    # tooltip at the very top -> below it
    assert place_card((1000, 10, 390, 400), 300, 150, 1920, 1080)[1] == 418
    # tall tooltip -> beside it, clamped to the screen
    x, y = place_card((50, 10, 390, 1060), 300, 150, 1920, 1080)
    assert x == 448 and 0 <= y


@pytest.fixture
def engine(tmp_path, monkeypatch):
    from d3helper import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SNAP_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    from d3helper.engine import Engine
    return Engine(queue.Queue(), grab=fs.image, read_text=lambda img, scale: fs.LINES)


def test_engine_upgrade_vs_onscreen_equipped(engine):
    r = engine.analyze(fs.image(), fs.CURSOR)
    v = r.verdict
    assert v.name == "Gauntlet of the Wastes"      # OCR typo fixed
    assert v.action == "UPGRADE" and v.slot == "hands" and v.score == 87
    assert "Area Damage" in v.missing


def test_engine_hotkeys_save_and_equip(engine):
    from d3helper import db
    engine.save_hovered()
    assert engine.q.get()[1] == "Hover an item first."
    engine.current = engine.analyze(fs.image(), fs.CURSOR)
    engine.equip_hovered()
    assert "marked as equipped" in engine.q.get()[1]
    with db.connect() as con:
        eq = db.equipped_by_slot(con)
    assert eq["hands"]["name"] == "Gauntlet of the Wastes" and eq["hands"]["quality"] == "ancient"


def test_engine_f9_without_key_saves_snapshot(engine):
    engine.current = engine.analyze(fs.image(), fs.CURSOR)
    engine.ask_claude()
    assert "Snapshot saved" in engine.q.get()[1]


def test_hover_loop_reads_once_then_hides_on_move(engine, monkeypatch):
    import threading
    import time
    from d3helper import config
    monkeypatch.setattr(config, "HOVER_MS", 100)
    pos = {"p": fs.CURSOR}
    engine.cursor = lambda: pos["p"]
    t = threading.Thread(target=engine.run, daemon=True)
    t.start()
    time.sleep(0.5)
    assert engine.q.get(timeout=1)[0] == "show"
    pos["p"] = (fs.CURSOR[0] + 100, fs.CURSOR[1])
    time.sleep(0.3)
    engine.stop()
    assert engine.q.get(timeout=1)[0] == "hide"


def test_f8_cycles_simple_full_off(engine):
    assert engine.mode == "simple" and engine.enabled
    engine.toggle()
    assert engine.mode == "full" and engine.enabled
    engine.toggle()
    assert not engine.enabled
    engine.toggle()
    assert engine.enabled and engine.mode == "simple"


def test_f7_sends_plan(engine):
    engine.show_plan()
    kind, plan = engine.q.get()
    assert kind == "plan" and plan.steps[0].title == "Get Helm of the Wastes"


def test_simple_headline_for_overlay(engine):
    r = engine.analyze(fs.image(), fs.CURSOR)
    assert r.verdict.headline == "Wear it - ancient beats your normal one."
