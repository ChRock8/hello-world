"""SQLite storage for items, snapshots and cube powers."""
import json
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT DEFAULT '',
    quality TEXT DEFAULT 'normal',
    affixes TEXT DEFAULT '{}',
    raw_text TEXT DEFAULT '',
    location TEXT DEFAULT 'Inbox',
    slot TEXT,
    equipped INTEGER DEFAULT 0,
    score INTEGER DEFAULT 0,
    verdict TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    snapshot TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    status TEXT DEFAULT 'new',
    error TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS cube (name TEXT PRIMARY KEY);
"""


@contextmanager
def connect():
    config.ensure_dirs()
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def _row(r):
    if r is None:
        return None
    d = dict(r)
    if "affixes" in d:
        d["affixes"] = json.loads(d["affixes"] or "{}")
    return d


def add_item(con, **fields) -> int:
    fields = dict(fields)
    fields["affixes"] = json.dumps(fields.get("affixes") or {})
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    cur = con.execute(f"INSERT INTO items ({cols}) VALUES ({marks})", list(fields.values()))
    return cur.lastrowid


def update_item(con, item_id: int, **fields):
    if "affixes" in fields:
        fields["affixes"] = json.dumps(fields["affixes"] or {})
    sets = ", ".join(f"{k} = ?" for k in fields)
    con.execute(f"UPDATE items SET {sets} WHERE id = ?", [*fields.values(), item_id])


def get_item(con, item_id: int):
    return _row(con.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())


def list_items(con, q: str = "", location: str = ""):
    sql, args = "SELECT * FROM items WHERE 1=1", []
    if q:
        sql += " AND (name LIKE ? OR notes LIKE ? OR raw_text LIKE ?)"
        args += [f"%{q}%"] * 3
    if location:
        sql += " AND location = ?"
        args.append(location)
    sql += " ORDER BY created_at DESC, id DESC"
    return [_row(r) for r in con.execute(sql, args)]


def locations(con):
    return [r[0] for r in con.execute("SELECT DISTINCT location FROM items ORDER BY location")]


def equipped_by_slot(con) -> dict:
    return {r["slot"]: _row(r) for r in con.execute("SELECT * FROM items WHERE equipped = 1 AND slot IS NOT NULL")}


def set_equipped(con, item_id: int, slot: str):
    con.execute("UPDATE items SET equipped = 0, location = CASE WHEN location = 'Equipped' THEN 'Stash' ELSE location END WHERE slot = ? AND equipped = 1", (slot,))
    con.execute("UPDATE items SET equipped = 1, slot = ?, location = 'Equipped' WHERE id = ?", (slot, item_id))


def delete_item(con, item_id: int):
    con.execute("DELETE FROM items WHERE id = ?", (item_id,))


def cube_powers(con) -> set:
    return {r[0] for r in con.execute("SELECT name FROM cube")}


def toggle_cube(con, name: str):
    if con.execute("SELECT 1 FROM cube WHERE name = ?", (name,)).fetchone():
        con.execute("DELETE FROM cube WHERE name = ?", (name,))
    else:
        con.execute("INSERT INTO cube (name) VALUES (?)", (name,))


def add_snapshot(con, path: str) -> int:
    return con.execute("INSERT INTO snapshots (path) VALUES (?)", (path,)).lastrowid


def list_snapshots(con):
    return [dict(r) for r in con.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT 100")]


def get_snapshot(con, snap_id: int):
    r = con.execute("SELECT * FROM snapshots WHERE id = ?", (snap_id,)).fetchone()
    return dict(r) if r else None


def set_snapshot_status(con, snap_id: int, status: str, error: str = ""):
    con.execute("UPDATE snapshots SET status = ?, error = ? WHERE id = ?", (status, error, snap_id))
