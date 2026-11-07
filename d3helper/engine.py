"""The hover loop: mouse rests -> screenshot -> OCR -> find tooltip -> verdict -> overlay.

Runs in a background thread and talks to the overlay through a queue of
("show", Reading, mode) / ("hide",) / ("toast", text) / ("plan", Plan, session) messages.
"""
import collections
import threading
import time
from dataclasses import dataclass, field

from . import (builds, capture, captures, config, db, ocr, planner, profile, screen_resources,
               tooltip, vision, winutil)
from .evaluator import Verdict, canonical_name, evaluate, merged_goals

JITTER_PX = 4      # ignore tiny mouse wobble
MOVE_HIDE_PX = 12  # moved this far from where we read -> hide the card


@dataclass
class Reading:
    item: dict
    verdict: Verdict
    box: tuple                 # tooltip position on screen (x, y, w, h)
    screen: tuple = (1920, 1080)
    source: str = "ocr"        # "ocr" or "claude"
    compare: list = field(default_factory=list)  # equipped items seen on screen


class Session:
    """What happened since the app started: items checked, upgrades, farming rates."""

    def __init__(self, resources: dict | None = None):
        self.started = time.time()
        self.seen: dict = {}
        self.upgrades: list = []
        self.res_start = dict(resources or {})
        self.res_now = dict(resources or {})

    def record(self, r: Reading) -> bool:
        key = (r.verdict.name or r.item.get("name"), r.item.get("quality"),
               tuple(sorted((r.item.get("affixes") or {}).items(), key=str)))
        if key in self.seen:
            return False
        self.seen[key] = r.verdict.action
        if r.verdict.action in ("UPGRADE", "EQUIP"):
            self.upgrades.append(r.verdict.name or r.item.get("name"))
        return True

    def update_resources(self, values: dict):
        for k, v in values.items():
            self.res_start.setdefault(k, v)
            self.res_now[k] = v

    def summary(self) -> dict:
        minutes = (time.time() - self.started) / 60
        counts = collections.Counter(self.seen.values())
        rates = []
        for k, now in self.res_now.items():
            delta = now - self.res_start.get(k, now)
            if delta and k != "highest_gr":
                per_hour = round(delta / (minutes / 60)) if minutes >= 5 else None
                rates.append((planner.RES_LABEL.get(k, k), delta, per_hour))
        return {"minutes": round(minutes), "checked": len(self.seen), "counts": dict(counts),
                "upgrades": list(self.upgrades), "rates": rates}


class Engine:
    def __init__(self, ui_queue, grab=capture.grab_screen, read_text=ocr.recognize,
                 cursor=winutil.cursor_pos, focused_title=winutil.foreground_title):
        self.q = ui_queue
        self.grab, self.read_text = grab, read_text
        self.cursor, self.focused_title = cursor, focused_title
        self.mode = config.CARD_MODE if config.CARD_MODE in ("simple", "full") else "simple"
        self.enabled = True
        self.current: Reading | None = None
        self.last: captures.Capture | None = None
        self.history = collections.deque(maxlen=40)  # recent reads, for the Debug page
        with db.connect() as con:
            self.session = Session(db.get_resources(con))
        self._stop = threading.Event()
        self._ocr_warned = False

    # ---- reading the screen ----------------------------------------------
    def capture_screen(self, cursor) -> captures.Capture:
        t0 = time.perf_counter()
        img = self.grab()
        scale = config.OCR_SCALE or profile.load()["ocr"]["scale"]
        lines = self.read_text(img, scale)
        tooltip.annotate_colors(lines, img)
        cap = captures.Capture((img.width, img.height), cursor, lines, img,
                               int((time.perf_counter() - t0) * 1000))
        self.last = cap
        return cap

    def analyze(self, img_or_cap, cursor=None) -> Reading | None:
        if isinstance(img_or_cap, captures.Capture):
            cap = img_or_cap
        else:  # a PIL image (tests / tools)
            img = img_or_cap
            lines = self.read_text(img, config.OCR_SCALE or profile.load()["ocr"]["scale"])
            tooltip.annotate_colors(lines, img)
            cap = captures.Capture((img.width, img.height), cursor, lines, img)
            self.last = cap
        tips = tooltip.find_tooltips(cap.lines, cap.screen[1])
        hovered, compares = tooltip.pick(tips, cap.cursor)
        reading = None
        if hovered:
            reading = self.judge(hovered.to_item(), [c.to_item() for c in compares],
                                 hovered.box, cap.screen, learn=True)
        self.history.appendleft({
            "time": time.strftime("%H:%M:%S"), "ms": cap.ms, "lines": len(cap.lines),
            "tooltips": len(tips), "name": reading.verdict.name if reading else None,
            "action": reading.verdict.action if reading else None})
        if config.DEBUG:
            captures.save(cap, config.data_subdir("debug") / time.strftime("%Y%m%d_%H%M%S"))
            for old in captures.list_folders(config.data_subdir("debug"))[20:]:
                _rmtree(old)
        return reading

    # ---- judging -------------------------------------------------------
    def judge(self, item: dict, compare: list, box, screen, source="ocr", learn=False) -> Reading:
        build = builds.load_build(config.ACTIVE_BUILD)
        with db.connect() as con:
            cube = db.cube_powers(con)
            goals = merged_goals(build, db.goal_overrides(con))
            # What the game shows as equipped right now beats what we stored.
            for ci in compare:
                cv = evaluate(build, ci, {}, cube, goals)
                if not cv.slot:
                    continue
                target = build["slots"][cv.slot].get("item")
                if learn and config.LEARN_EQUIPPED and target and canonical_name(build, ci["name"]) == target:
                    if db.learn_equipped(con, cv.slot, {**ci, "name": target}) == "new":
                        self.q.put(("toast", f"Learned your {builds.SLOT_LABELS[cv.slot].lower()}: {target}"))
            equipped = db.equipped_by_slot(con)
            for ci in compare:
                cv = evaluate(build, ci, {}, cube, goals)
                if cv.slot:
                    equipped[cv.slot] = {**ci, "score": cv.score}
        return Reading(item, evaluate(build, item, equipped, cube, goals), box, screen, source, compare)

    def plan(self) -> planner.Plan:
        build = builds.load_build(config.ACTIVE_BUILD)
        with db.connect() as con:
            return planner.make_plan(build, db.equipped_by_slot(con), db.list_items(con), db.cube_powers(con),
                                     db.get_resources(con), merged_goals(build, db.goal_overrides(con)))

    # ---- loop ----------------------------------------------------------
    def stop(self):
        self._stop.set()

    def _hide(self):
        self.current = None
        self.q.put(("hide",))

    def run(self):
        last, still_since, read_at = None, 0.0, None
        while not self._stop.wait(0.08):
            if not self.enabled:
                continue
            if config.REQUIRE_GAME and winutil.IS_WINDOWS and config.GAME_TITLE.lower() not in self.focused_title().lower():
                if self.current:
                    self._hide()
                read_at = None
                continue
            pos = self.cursor()
            if pos is None:
                continue
            now = time.monotonic()
            if last is None or _dist(pos, last) > JITTER_PX:
                last, still_since = pos, now
                if read_at and _dist(pos, read_at) > MOVE_HIDE_PX:
                    read_at = None
                    if self.current:
                        self._hide()
                continue
            if read_at is None and now - still_since >= config.HOVER_MS / 1000:
                read_at = pos
                self._read(pos)

    def _read(self, pos):
        try:
            reading = self.analyze(self.capture_screen(pos))
        except ocr.OcrUnavailable as e:
            if not self._ocr_warned:
                self._ocr_warned = True
                self.q.put(("toast", f"{e} Hover reading is off; F9 still works."))
            self.enabled = False
            return
        except Exception as e:
            print(f"[overlay] read failed: {e}")
            return
        if reading:
            self.current = reading
            if self.session.record(reading) and config.SOUND and reading.verdict.action in ("UPGRADE", "EQUIP"):
                winutil.chime()
            self.q.put(("show", reading, self.mode))
        elif self.current:
            self._hide()

    # ---- hotkeys -------------------------------------------------------
    def toggle(self):
        """F8 cycles: simple card -> detailed card -> overlay off."""
        if not self.enabled:
            self.enabled, self.mode = True, "simple"
        elif self.mode == "simple":
            self.mode = "full"
        else:
            self.enabled = False
        self._hide()
        msg = {"simple": "Overlay: simple", "full": "Overlay: details"}[self.mode] if self.enabled else "Overlay off (F8 to turn back on)"
        self.q.put(("toast", msg))

    def show_plan(self):
        self.q.put(("plan", self.plan(), self.session.summary()))

    def read_resources(self):
        """F6: read gold, shards and materials off the screen and save them."""
        try:
            cap = self.capture_screen(self.cursor())
        except ocr.OcrUnavailable as e:
            self.q.put(("toast", str(e)))
            return {}
        folder = config.data_subdir("captures") / time.strftime("resources_%Y%m%d_%H%M%S")
        captures.save(cap, folder)
        for old in captures.list_folders(config.data_subdir("captures"))[10:]:
            _rmtree(old)
        found = screen_resources.read_resources(cap.lines, cap.screen)
        if not found:
            self.q.put(("toast", "Couldn't find gold, shards or materials. Open your inventory, "
                                 "or mark where they are on the dashboard's Calibrate page."))
            return {}
        with db.connect() as con:
            db.set_resources(con, found)
        self.session.update_resources(found)
        shown = ", ".join(f"{planner.RES_LABEL.get(k, k)} {v:,}" for k, v in list(found.items())[:4])
        more = f" +{len(found) - 4} more" if len(found) > 4 else ""
        self.q.put(("toast", f"Updated: {shown}{more}"))
        return found

    def report_wrong(self):
        """F12: save exactly what the app saw, so it can be fixed (and become a test)."""
        cap = self.last
        if cap is None or cap.img is None:
            try:
                cap = self.capture_screen(self.cursor())
            except ocr.OcrUnavailable:
                img = self.grab()
                cap = captures.Capture((img.width, img.height), self.cursor(), [], img)
        r = self.current
        extra = {"app_read": captures.read(cap) if cap.lines else None,
                 "verdict": ({"action": r.verdict.action, "headline": r.verdict.headline, "slot": r.verdict.slot}
                             if r else None)}
        folder = captures.save(cap, config.data_subdir("feedback") / time.strftime("%Y%m%d_%H%M%S"), extra)
        self.q.put(("toast", f"Saved for fixing: data\\feedback\\{folder.name}. See the Debug page."))
        return folder

    def _store(self, equip: bool):
        r = self.current
        if not r:
            self.q.put(("toast", "Hover an item first."))
            return
        it = r.item
        with db.connect() as con:
            item_id = db.add_item(con, name=r.verdict.name or it["name"], type=it.get("type", ""),
                                  quality=it.get("quality", "normal"), affixes=it.get("affixes", {}),
                                  raw_text=it.get("raw_text", ""), notes=it.get("legendary_power", ""),
                                  location="Stash", slot=r.verdict.slot, score=r.verdict.score,
                                  verdict=r.verdict.action)
            if equip and r.verdict.slot:
                db.set_equipped(con, item_id, r.verdict.slot)
        name = r.verdict.name or it["name"]
        if equip and r.verdict.slot:
            self.q.put(("toast", f"{name} marked as equipped ({builds.SLOT_LABELS[r.verdict.slot]})"))
        else:
            self.q.put(("toast", f"Saved {name} to your stash list"))

    def save_hovered(self):
        self._store(equip=False)

    def equip_hovered(self):
        self._store(equip=True)

    def ask_claude(self):
        img = self.grab()
        r = self.current
        if r:  # just the tooltip area, so Claude reads the right item
            x, y, w, h = r.box
            pad = 40
            img = img.crop((max(0, x - pad), max(0, y - pad), min(img.width, x + w + pad), min(img.height, y + h + pad)))
        path = capture.save_image(img)
        with db.connect() as con:
            snap_id = db.add_snapshot(con, path)
        if not config.vision_enabled():
            self.q.put(("toast", "Snapshot saved. Add ANTHROPIC_API_KEY to have Claude read it."))
            return
        self.q.put(("toast", "Asking Claude…"))
        threading.Thread(target=self._claude, args=(snap_id, path, r), daemon=True).start()

    def _claude(self, snap_id, path, previous):
        try:
            item = vision.read_tooltip(path)
        except vision.VisionError as e:
            with db.connect() as con:
                db.set_snapshot_status(con, snap_id, "failed", str(e))
            self.q.put(("toast", str(e)))
            return
        with db.connect() as con:
            db.set_snapshot_status(con, snap_id, "read")
        box = previous.box if previous else (100, 100, 400, 600)
        screen = previous.screen if previous else (1920, 1080)
        compare = previous.compare if previous else []
        self.current = self.judge(item, compare, box, screen, source="claude")
        self.q.put(("show", self.current, "full"))


def _dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)
