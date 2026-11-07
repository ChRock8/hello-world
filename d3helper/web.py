"""Local web UI (Flask). Open http://localhost:5173 while you play."""
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for

import re

import json

from . import affixes, blizzard, builds, captures, config, db, fixtures, planner, profile, screen_resources, state, vision
from .evaluator import check_goals, evaluate, merged_goals, qrank

app = Flask(__name__)
app.secret_key = "d3helper-local"


def active_build():
    return builds.load_build(config.ACTIVE_BUILD)


def goals_for(con):
    return merged_goals(active_build(), db.goal_overrides(con))


def _evaluate_and_store(con, item_id):
    item = db.get_item(con, item_id)
    equipped = db.equipped_by_slot(con)
    if item.get("equipped"):
        equipped.pop(item.get("slot"), None)  # don't compare an item with itself
    v = evaluate(active_build(), item, equipped, db.cube_powers(con), goals_for(con))
    if item.get("equipped"):
        v.action = "EQUIPPED"
        done = qrank(item) >= 1 and v.meets_goals
        v.headline = "You're wearing this - slot done ✓" if done else "You're wearing this."
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
        goals = goals_for(con)
        resources = db.get_resources(con)
    plan = planner.make_plan(build, equipped, items, cube, resources, goals)
    rows = []
    for slot in builds.SLOTS:
        spec = build["slots"].get(slot, {})
        target = spec.get("item")
        eq = equipped.get(slot)
        owned = [i for i in items if target and i["name"].lower() == target.lower() and not i["equipped"]]
        if eq and (not target or eq["name"].lower() == target.lower()):
            ok = qrank(eq) >= 1 and check_goals(spec.get("affixes", {}), eq.get("affixes") or {}, goals.get(slot, {}))[0]
            status = "done" if ok else "equipped"
        elif owned:
            status = "owned"
        else:
            status = "missing"
        rows.append({"slot": slot, "spec": spec, "equipped": eq, "owned": owned, "status": status})
    done = sum(r["status"] == "done" for r in rows)
    session = state.engine.session.summary() if state.engine else None
    return render_template("dashboard.html", rows=rows, done=done, cube=cube, plan=plan,
                           short_text=planner.short_text, has_resources=bool(resources), session=session)


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
            result = evaluate(active_build(), item, db.equipped_by_slot(con), db.cube_powers(con), goals_for(con))
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


def parse_amount(text: str) -> int:
    """'1,234' / '2.5m' / '300k' / '1.2b' -> int."""
    t = (text or "").strip().lower().replace(",", "").replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb]?)", t)
    if not m:
        return 0
    mult = {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[m.group(2)]
    return int(float(m.group(1)) * mult)


@app.route("/stuff", methods=["GET", "POST"])
def stuff():
    with db.connect() as con:
        if request.method == "POST":
            values = {r["key"]: parse_amount(request.form.get(r["key"], "")) for r in planner.RESOURCES}
            db.set_resources(con, values)
            if state.engine:
                state.engine.session.update_resources(values)
            flash("Saved. Next steps updated.")
            return redirect(url_for("dashboard"))
        values = db.get_resources(con)
    groups: dict = {}
    for r in planner.RESOURCES:
        groups.setdefault(r["group"], []).append(r)
    return render_template("stuff.html", groups=groups, values=values)


@app.route("/goals", methods=["GET", "POST"])
def goals_page():
    build = active_build()
    with db.connect() as con:
        if request.method == "POST":
            if request.form.get("reset"):
                db.clear_goals(con)
                flash("Goals reset to defaults.")
            else:
                for key, val in request.form.items():
                    if "|" in key:
                        slot, affix = key.split("|", 1)
                        db.set_goal(con, slot, affix, float(val) if val.strip() else None)
                flash("Goals saved.")
            return redirect(url_for("goals_page"))
        goals = goals_for(con)
    rows = []
    for slot in builds.SLOTS:
        spec = build["slots"].get(slot, {})
        fields = [(k, w, affixes.roll_range(k, slot), goals.get(slot, {}).get(k))
                  for k, w in spec.get("affixes", {}).items() if w >= 2 and affixes.roll_range(k, slot)]
        if fields:
            rows.append((slot, spec, fields))
    return render_template("goals.html", rows=rows)


# ---- stash cleanup -----------------------------------------------------

@app.route("/cleanup", methods=["GET", "POST"])
def cleanup():
    build = active_build()
    with db.connect() as con:
        if request.method == "POST":
            ids = [int(i) for i in request.form.getlist("id")]
            for item_id in ids:
                db.delete_item(con, item_id)
            flash(f"Removed {len(ids)} items from your list.")
            return redirect(url_for("cleanup"))
        equipped, cube, goals = db.equipped_by_slot(con), db.cube_powers(con), goals_for(con)
        junk = []
        for it in db.list_items(con):
            if it["equipped"]:
                continue
            v = evaluate(build, it, equipped, cube, goals)
            if v.action == "SALVAGE":
                junk.append((it, v))
    return render_template("cleanup.html", junk=junk)


# ---- debug: what did the app see? ----------------------------------------

def _folders():
    return {"feedback": captures.list_folders(config.data_subdir("feedback")),
            "captures": captures.list_folders(config.data_subdir("captures")),
            "debug": captures.list_folders(config.data_subdir("debug"))}


def _folder(kind: str, name: str):
    if kind not in ("feedback", "captures", "debug") or "/" in name or "\\" in name or ".." in name:
        abort(404)
    folder = config.data_subdir(kind) / name
    if not (folder / "capture.json").exists():
        abort(404)
    return folder


@app.route("/debug")
def debug_page():
    rows = []
    for kind, folders in _folders().items():
        for folder in folders[:15]:
            data = json.loads((folder / "capture.json").read_text(encoding="utf-8"))
            app_read = (data.get("app_read") or {}).get("hovered")
            rows.append({"kind": kind, "name": folder.name, "taken": data.get("taken", ""),
                         "lines": len(data.get("lines", [])), "read": app_read,
                         "image": (folder / "screen.png").exists()})
    history = list(state.engine.history) if state.engine else []
    return render_template("debug.html", rows=rows, history=history, cases=fixtures.cases())


@app.route("/debug/<kind>/<name>", methods=["GET", "POST"])
def debug_detail(kind, name):
    folder = _folder(kind, name)
    cap, data = captures.load(folder)
    if request.method == "POST":
        try:
            case = fixtures.make_case(cap, request.form.get("case") or name)
            if (folder / "screen.png").exists() and not (case / "screen.png").exists():
                import shutil
                shutil.copy(folder / "screen.png", case / "screen.png")
            flash(f"Test case created: {case}. Fix expected.json if anything is wrong.")
        except FileExistsError as e:
            flash(str(e))
        return redirect(url_for("debug_detail", kind=kind, name=name))
    now = captures.read(cap)  # re-read with the current rules
    return render_template("debug_detail.html", kind=kind, name=name, cap=cap, data=data, now=now,
                           before=data.get("app_read"), lines=sorted(cap.lines, key=lambda l: (l.y, l.x)))


@app.route("/debug/<kind>/<name>.png")
def debug_image(kind, name):
    folder = _folder(kind, name)
    if not (folder / "screen.png").exists():
        abort(404)
    return send_file(folder / "screen.png", mimetype="image/png")


# ---- calibrate: show the app where your numbers are ------------------------

@app.route("/calibrate", methods=["GET", "POST"])
def calibrate():
    if request.method == "POST":
        key = request.form["key"]
        region = [round(float(request.form[k]), 4) for k in ("x0", "y0", "x1", "y1")]
        profile.save_override(["resources", key, "region"], region)
        flash(f"Saved where {planner.RES_LABEL.get(key, key)} is. Press F6 in game to test.")
        return redirect(url_for("calibrate", src=request.form.get("src", "")))
    sources = [(f"{kind}/{f.name}", f"{kind}: {f.name}") for kind, folders in _folders().items()
               for f in folders if (f / "screen.png").exists()]
    src = request.args.get("src") or (sources[0][0] if sources else "")
    found, prof = {}, profile.load()
    if src:
        cap, _ = captures.load(_folder(*src.split("/", 1)))
        if cap.lines:
            found = screen_resources.read_resources(cap.lines, cap.screen)
    regions = {k: v.get("region") for k, v in prof["resources"].items() if isinstance(v, dict)}
    return render_template("calibrate.html", sources=sources, src=src, found=found,
                           resources=planner.RESOURCES, regions=regions, res_label=planner.RES_LABEL)
