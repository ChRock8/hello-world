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
    assert b"equipped" in client.get("/").data
    # A worse Focus is now just a KEEP
    r = client.post("/check", data={"name": "Focus", "quality": "ancient", "affixes": "str vit"})
    assert b"KEEP" in r.data
