import importlib

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    from d3helper import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SNAP_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite")
    from d3helper import web
    importlib.reload(web)
    return web.app.test_client()


def test_pages_render(client):
    for path in ["/", "/check", "/items", "/snapshots", "/import"]:
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
