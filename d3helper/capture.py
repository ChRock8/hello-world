"""Screenshots and global hotkeys.

Run Diablo 3 in 'Windowed Fullscreen' so screenshots and the overlay work.
"""
import threading
from datetime import datetime

from . import config, db


def grab_screen():
    """Primary monitor as a PIL image."""
    import mss
    from PIL import Image

    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        return Image.frombytes("RGB", shot.size, shot.rgb)


def save_image(img, prefix="snap") -> str:
    config.ensure_dirs()
    path = config.SNAP_DIR / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S_%f}.png"
    img.save(path)
    return str(path)


def take_snapshot() -> str:
    return save_image(grab_screen())


def snapshot_and_record(on_saved=None) -> int:
    path = take_snapshot()
    with db.connect() as con:
        snap_id = db.add_snapshot(con, path)
    if on_saved:
        threading.Thread(target=on_saved, args=(snap_id,), daemon=True).start()
    return snap_id


def start_hotkeys(mapping: dict):
    """mapping: {"<f9>": callback}. Returns the listener, or None if unavailable."""
    try:
        from pynput import keyboard
    except Exception as e:  # no display / not installed
        print(f"[hotkeys] disabled: {e}")
        return None

    def safe(fn):
        def run():
            try:
                fn()
            except Exception as e:
                print(f"[hotkeys] {e}")
        return run

    listener = keyboard.GlobalHotKeys({k: safe(f) for k, f in mapping.items()})
    listener.daemon = True
    listener.start()
    return listener


def start_hotkey(on_saved=None):
    """Snapshot-only mode (no overlay): the hotkey just saves a screenshot."""
    listener = start_hotkeys({config.HOTKEY: lambda: print(f"[hotkey] saved snapshot #{snapshot_and_record(on_saved)}")})
    if listener:
        print(f"[hotkey] press {config.HOTKEY} in game to save a snapshot")
    return listener
