import importlib

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    from d3helper import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SNAP_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite")
    from d3helper import fixtures, profile, web
    monkeypatch.setattr(fixtures, "CASES_DIR", tmp_path / "cases")
    profile.reload()
    importlib.reload(web)
    yield web.app.test_client()
    profile.reload()


def test_pages_render(client):
    for path in ["/", "/check", "/items", "/snapshots", "/import", "/debug", "/calibrate", "/cleanup", "/goals", "/stuff"]:
        assert client.get(path).status_code == 200, path


def test_check_save_and_equip_flow(client):
    r = client.post("/check", data={"name": "Focus", "quality": "ancient", "affixes": "chc chd socket ias",
                                    "save": "1", "location": "Stash 1"}, follow_redirects=True)
    assert b"EQUIP" in r.data
    r = client.post("/items/1", data={"action": "equip", "slot": "ring1"}, follow_redirects=True)
    assert b"EQUIPPED" in r.data
    assert b'pill done' in client.get("/").data  # ancient + meets goals
    # A worse Focus is salvage
    r = client.post("/check", data={"name": "Focus", "quality": "ancient", "affixes": "str vit"})
    assert b"SALVAGE" in r.data


def test_stuff_and_goals_pages(client):
    r = client.post("/stuff", data={"gold": "2.5m", "blood_shards": "1,200", "highest_gr": "70",
                                    "deaths_breath": "30"}, follow_redirects=True)
    assert b"Next steps" in r.data and b"spend them at Kadala" in r.data  # 1200 >= 80% of 1200 cap
    r = client.post("/goals", data={"hands|chc": "9.9"}, follow_redirects=True)
    assert b'value="9.9"' in r.data
    r = client.post("/goals", data={"reset": "1"}, follow_redirects=True)
    assert b'value="9.4"' in r.data


def test_parse_amount():
    from d3helper.web import parse_amount
    assert parse_amount("2.5m") == 2_500_000 and parse_amount("1,234") == 1234
    assert parse_amount("300k") == 300_000 and parse_amount("abc") == 0


def _feedback(tmp_path):
    from d3helper import captures
    from tests import fake_screen as fs
    return captures.save(captures.Capture((1920, 1080), fs.CURSOR, list(fs.LINES), fs.image()),
                         tmp_path / "feedback" / "20261107_200000", {"app_read": None})


def test_debug_page_and_make_test_case(client, tmp_path):
    _feedback(tmp_path)
    assert b"20261107_200000" in client.get("/debug").data
    r = client.get("/debug/feedback/20261107_200000")
    assert b"Gauntiet of the Wastes" in r.data and b"orange" in r.data
    r = client.post("/debug/feedback/20261107_200000", data={"case": "gloves"}, follow_redirects=True)
    assert b"Test case created" in r.data
    assert (tmp_path / "cases" / "gloves" / "expected.json").exists()
    assert (tmp_path / "cases" / "gloves" / "screen.png").exists()
    assert client.get("/debug/feedback/..%2f..%2fetc").status_code == 404


def test_calibrate_saves_region(client, tmp_path):
    from d3helper import profile
    _feedback(tmp_path)
    assert b"calimg" in client.get("/calibrate").data
    client.post("/calibrate", data={"key": "gold", "x0": "0.7", "y0": "0.9", "x1": "0.8", "y1": "0.95",
                                    "src": "feedback/20261107_200000"})
    assert profile.load()["resources"]["gold"]["region"] == [0.7, 0.9, 0.8, 0.95]
    assert (tmp_path / "screen_profile.json").exists()


def test_cleanup_lists_and_removes_junk(client):
    for name, extra in [("Immortal King's Triumph", {"type": "Set Helm"}), ("Focus", {})]:
        client.post("/check", data={"name": name, "affixes": "chc chd socket", "save": "1", **extra},
                    follow_redirects=True)  # consume the "Saved ..." notices
    r = client.get("/cleanup")
    assert b"Immortal King" in r.data and b"Focus" not in r.data
    client.post("/cleanup", data={"id": "1"})
    assert b"Nothing to clean up" in client.get("/cleanup").data
