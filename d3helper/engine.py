"""The hover loop: mouse rests -> screenshot -> OCR -> find tooltip -> verdict -> overlay.

Runs in a background thread and talks to the overlay through a queue of
("show", Reading) / ("hide",) / ("toast", text) messages.
"""
import json
import threading
import time
from dataclasses import dataclass, field

from . import builds, capture, config, db, ocr, tooltip, vision, winutil
from .evaluator import Verdict, evaluate

JITTER_PX = 4    # ignore tiny mouse wobble
MOVE_HIDE_PX = 12  # moved this far from where we read -> hide the card


@dataclass
class Reading:
    item: dict
    verdict: Verdict
    box: tuple                 # tooltip position on screen (x, y, w, h)
    screen: tuple = (1920, 1080)
    source: str = "ocr"        # "ocr" or "claude"
    compare: list = field(default_factory=list)  # equipped items seen on screen


class Engine:
    def __init__(self, ui_queue, grab=capture.grab_screen, read_text=ocr.recognize,
                 cursor=winutil.cursor_pos, focused_title=winutil.foreground_title):
        self.q = ui_queue
        self.grab, self.read_text = grab, read_text
        self.cursor, self.focused_title = cursor, focused_title
        self.enabled = True
        self.current: Reading | None = None
        self._stop = threading.Event()
        self._ocr_warned = False

    # ---- judging -------------------------------------------------------
    def judge(self, item: dict, compare: list, box, screen, source="ocr") -> Reading:
        build = builds.load_build(config.ACTIVE_BUILD)
        with db.connect() as con:
            equipped = db.equipped_by_slot(con)
            cube = db.cube_powers(con)
        # What the game shows as equipped right now beats what we stored.
        for ci in compare:
            cv = evaluate(build, ci, {}, cube)
            if cv.slot:
                equipped[cv.slot] = {**ci, "score": cv.score}
        return Reading(item, evaluate(build, item, equipped, cube), box, screen, source, compare)

    def analyze(self, img, cursor) -> Reading | None:
        lines = self.read_text(img, config.OCR_SCALE)
        tips = tooltip.find_tooltips(lines, img.height, tooltip.color_sampler(img))
        hovered, compares = tooltip.pick(tips, cursor)
        if config.DEBUG:
            self._dump(img, lines, hovered)
        if not hovered:
            return None
        return self.judge(hovered.to_item(), [c.to_item() for c in compares],
                          hovered.box, (img.width, img.height))

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
            reading = self.analyze(self.grab(), pos)
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
            self.q.put(("show", reading))
        elif self.current:
            self._hide()

    # ---- hotkeys -------------------------------------------------------
    def toggle(self):
        self.enabled = not self.enabled
        self._hide()
        self.q.put(("toast", "Overlay on" if self.enabled else "Overlay off (F8 to turn back on)"))

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
        self.q.put(("show", self.current))

    # ---- debugging -----------------------------------------------------
    def _dump(self, img, lines, hovered):
        config.DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        img.save(config.DEBUG_DIR / f"{stamp}.png")
        (config.DEBUG_DIR / f"{stamp}.json").write_text(json.dumps({
            "lines": [l.to_dict() for l in lines],
            "hovered": hovered.__dict__ if hovered else None}, indent=1, default=str))
        old = sorted(config.DEBUG_DIR.glob("*.png"))[:-20]
        for p in old:
            p.unlink(missing_ok=True)
            p.with_suffix(".json").unlink(missing_ok=True)


def _dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
