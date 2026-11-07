"""Local web UI (Flask). Open http://localhost:5173 while you play."""
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for

from . import affixes, blizzard, builds, config, db, vision
from .evaluator import evaluate

app = Flask(__name__)
app.secret_key = "d3helper-local"


def active_build():
    return builds.load_build(config.ACTIVE_BUILD)


def _evaluate_and_store(con, item_id):
    item = db.get_item(con, item_id)
    equipped = db.equipped_by_slot(con)
    if item.get("equipped"):
        equipped.pop(item.get("slot"), None)  # don't compare an item with itself
    v = evaluate(active_build(), item, equipped, db.cube_powers(con))
    if item.get("equipped"):
        v.action = "EQUIPPED"
    db.update_item(con, item_id, slot=item.get("slot") or v.slot, score=v.score, verdict=v.action)
    return v


def read_snapshot(snap_id: int):
    """Run Claude on a snapshot and file the result in the Inbox."""
    with db.connect() as con:
        snap = db.get_snapshot(con, snap_id)
        db.set_snapshot_status(con, snap_id, "reading")
    try:
        data = vision.read_tooltip(snap["path"])
    except vision.VisionError as e:
        with db.connect() as con:
            db.set_snapshot_status(con, snap_id, "failed", str(e))
        return None
    with db.connect() as con:
        item_id = db.add_item(con, name=data["name"], type=data["type"], quality=data["quality"],
                              affixes=data["affixes"], raw_text=data["raw_text"],
                              notes=data["legendary_power"], location="Inbox", snapshot=snap["path"])
        _evaluate_and_store(con, item_id)
        db.set_snapshot_status(con, snap_id, "read")
    return item_id


@app.context_processor
def globals_():
    return {"build": active_build(), "slot_labels": builds.SLOT_LABELS,
            "vision_on": config.vision_enabled(), "label": affixes.label, "hotkey": config.HOTKEY}


@app.route("/")
def dashboard():
    build = active_build()
    with db.connect() as con:
        equipped = db.equipped_by_slot(con)
        items = db.list_items(con)
        cube = db.cube_powers(con)
    rows = []
    for slot in builds.SLOTS:
        spec = build["slots"].get(slot, {})
        target = spec.get("item")
        eq = equipped.get(slot)
        owned = [i for i in items if target and i["name"].lower() == target.lower() and not i["equipped"]]
        if eq and target and eq["name"].lower() == target.lower():
            status = "equipped"
        elif eq and not target:
            status = "equipped"
        elif owned:
            status = "owned"
        else:
            status = "missing"
        rows.append({"slot": slot, "spec": spec, "equipped": eq, "owned": owned, "status": status})
    done = sum(r["status"] == "equipped" for r in rows)
    return render_template("dashboard.html", rows=rows, done=done, cube=cube)


@app.post("/cube/toggle")
def cube_toggle():
    with db.connect() as con:
        db.toggle_cube(con, request.form["name"])
    return redirect(url_for("dashboard"))


@app.route("/check", methods=["GET", "POST"])
def check():
    """Quick 'keep or salvage?' without saving."""
    result, item = None, None
    if request.method == "POST":
        item = {"name": request.form.get("name", ""), "type": request.form.get("type", ""),
                "quality": request.form.get("quality", "normal"),
                "affixes": affixes.parse(request.form.get("affixes", ""))}
        with db.connect() as con:
            result = evaluate(active_build(), item, db.equipped_by_slot(con), db.cube_powers(con))
        if request.form.get("save"):
            with db.connect() as con:
                item_id = db.add_item(con, name=item["name"], type=item["type"], quality=item["quality"],
                                      affixes=item["affixes"], raw_text=request.form.get("affixes", ""),
                                      location=request.form.get("location") or "Inbox",
                                      slot=result.slot, score=result.score, verdict=result.action)
            flash(f"Saved {item['name']}.")
            return redirect(url_for("item_detail", item_id=item_id))
    return render_template("check.html", result=result, item=item, form=request.form)


@app.route("/items")
def items():
    q, loc = request.args.get("q", ""), request.args.get("location", "")
    with db.connect() as con:
        rows = db.list_items(con, q, loc)
        locs = db.locations(con)
    return render_template("items.html", items=rows, q=q, location=loc, locations=locs)


@app.route("/items/<int:item_id>", methods=["GET", "POST"])
def item_detail(item_id):
    with db.connect() as con:
        item = db.get_item(con, item_id)
        if not item:
            abort(404)
        if request.method == "POST":
            action = request.form.get("action")
            if action == "delete":
                db.delete_item(con, item_id)
                flash("Deleted.")
                return redirect(url_for("items"))
            if action == "equip":
                db.set_equipped(con, item_id, request.form["slot"])
            else:
                raw = request.form.get("affixes", "")
                db.update_item(con, item_id, name=request.form["name"], type=request.form.get("type", ""),
                               quality=request.form.get("quality", "normal"), raw_text=raw,
                               affixes=affixes.parse(raw), location=request.form.get("location") or "Stash",
                               notes=request.form.get("notes", ""))
            _evaluate_and_store(con, item_id)
            flash("Saved.")
            return redirect(url_for("item_detail", item_id=item_id))
        verdict = _evaluate_and_store(con, item_id)
        item = db.get_item(con, item_id)
        locs = db.locations(con)
    return render_template("item.html", item=item, verdict=verdict, locations=locs, slots=builds.SLOTS)


@app.route("/snapshots")
def snapshots():
    with db.connect() as con:
        snaps = db.list_snapshots(con)
    return render_template("snapshots.html", snaps=snaps)


@app.post("/snapshots/take")
def snapshots_take():
    from . import capture
    try:
        capture.snapshot_and_record()
        flash("Snapshot saved.")
    except Exception as e:
        flash(f"Screenshot failed: {e}")
    return redirect(url_for("snapshots"))


@app.post("/snapshots/<int:snap_id>/read")
def snapshots_read(snap_id):
    item_id = read_snapshot(snap_id)
    if item_id:
        return redirect(url_for("item_detail", item_id=item_id))
    with db.connect() as con:
        flash(db.get_snapshot(con, snap_id)["error"])
    return redirect(url_for("snapshots"))


@app.route("/snapshots/<int:snap_id>.png")
def snapshot_image(snap_id):
    with db.connect() as con:
        snap = db.get_snapshot(con, snap_id)
    if not snap or not Path(snap["path"]).resolve().is_relative_to(config.SNAP_DIR.resolve()):
        abort(404)
    return send_file(snap["path"], mimetype="image/png")


@app.route("/import", methods=["GET", "POST"])
def import_gear():
    heroes, error = [], None
    tag = request.values.get("battletag", "")
    if not blizzard.enabled():
        return render_template("import.html", disabled=True, heroes=[], tag=tag, error=None)
    try:
        if request.method == "POST" and request.form.get("hero_id"):
            imported = blizzard.hero_items(tag, int(request.form["hero_id"]))
            with db.connect() as con:
                for it in imported:
                    item_id = db.add_item(con, name=it["name"], type=it["type"], quality=it["quality"],
                                          raw_text=it["raw_text"], affixes=affixes.parse(it["raw_text"]),
                                          location="Equipped", slot=it["slot"])
                    db.set_equipped(con, item_id, it["slot"])
                    _evaluate_and_store(con, item_id)
            flash(f"Imported {len(imported)} equipped items.")
            return redirect(url_for("dashboard"))
        if tag:
            heroes = blizzard.list_heroes(tag)
    except blizzard.BlizzardError as e:
        error = str(e)
    except Exception as e:
        error = f"Import failed: {e}"
    return render_template("import.html", disabled=False, heroes=heroes, tag=tag, error=error)
