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


def drain(engine):
    out = []
    while not engine.q.empty():
        out.append(engine.q.get())
    return out


def toasts(engine):
    return [m[1] for m in drain(engine) if m[0] == "toast"]


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
    assert toasts(engine) == ["Hover an item first."]
    engine.current = engine.analyze(fs.image(), fs.CURSOR)
    engine.equip_hovered()
    assert any("marked as equipped" in t for t in toasts(engine))
    with db.connect() as con:
        eq = db.equipped_by_slot(con)
    assert eq["hands"]["name"] == "Gauntlet of the Wastes" and eq["hands"]["quality"] == "ancient"


def test_engine_f9_without_key_saves_snapshot(engine):
    engine.current = engine.analyze(fs.image(), fs.CURSOR)
    engine.ask_claude()
    assert any("Snapshot saved" in t for t in toasts(engine))


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
    assert "show" in [m[0] for m in drain(engine)]
    pos["p"] = (fs.CURSOR[0] + 100, fs.CURSOR[1])
    time.sleep(0.3)
    engine.stop()
    assert [m[0] for m in drain(engine)][0] == "hide"  # then it reads again where the mouse settled


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
    kind, plan, session = engine.q.get()
    assert kind == "plan" and plan.steps[0].title == "Get Helm of the Wastes"
    assert session["checked"] == 0


def test_simple_headline_for_overlay(engine):
    r = engine.analyze(fs.image(), fs.CURSOR)
    assert r.verdict.headline == "Wear it - ancient beats your normal one."


def test_learns_equipped_gear_from_comparison_tooltip(engine):
    from d3helper import db
    engine.analyze(fs.image(), fs.CURSOR)
    assert "Learned your gloves: Gauntlet of the Wastes" in toasts(engine)
    with db.connect() as con:
        eq = db.equipped_by_slot(con)["hands"]
    assert eq["quality"] == "normal" and eq["affixes"] == {"str": 500.0, "chc": 8.0}
    engine.analyze(fs.image(), fs.CURSOR)  # seen again: no new toast, no duplicate row
    assert toasts(engine) == []
    with db.connect() as con:
        assert len(db.list_items(con)) == 1


def test_f12_saves_capture_for_fixing(engine):
    from d3helper import captures
    engine.analyze(fs.image(), fs.CURSOR)
    engine.current = None
    folder = engine.report_wrong()
    assert (folder / "screen.png").exists()
    cap, data = captures.load(folder)
    assert len(cap.lines) == len(fs.LINES) and data["app_read"]["hovered"]["quality"] == "ancient"
    assert any("Saved for fixing" in t for t in toasts(engine))


def test_f6_reads_resources(engine, monkeypatch):
    from d3helper import db
    from d3helper.ocr import OcrLine
    lines = [OcrLine("Death's Breath", 300, 500, 120, 16), OcrLine("1,234", 430, 500, 50, 16),
             OcrLine("Forgotten Soul: 87", 300, 530, 160, 16)]
    engine.read_text = lambda img, scale: lines
    engine.cursor = lambda: (10, 10)
    found = engine.read_resources()
    assert found == {"deaths_breath": 1234, "forgotten_soul": 87}
    with db.connect() as con:
        assert db.get_resources(con)["deaths_breath"] == 1234
    assert engine.session.summary()["checked"] == 0


def test_session_counts_unique_items(engine):
    r = engine.analyze(fs.image(), fs.CURSOR)
    assert engine.session.record(r) and not engine.session.record(r)
    s = engine.session.summary()
    assert s["checked"] == 1 and s["upgrades"] == ["Gauntlet of the Wastes"]
