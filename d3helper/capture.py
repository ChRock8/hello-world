"""Global hotkey that saves a screenshot of the game.

Run Diablo 3 in 'Windowed Fullscreen' so screenshots aren't black.
"""
import threading
from datetime import datetime

from . import config, db


def take_snapshot() -> str:
    import mss
    import mss.tools

    config.ensure_dirs()
    path = config.SNAP_DIR / f"snap_{datetime.now():%Y%m%d_%H%M%S_%f}.png"
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary monitor
        shot = sct.grab(monitor)
        mss.tools.to_png(shot.rgb, shot.size, output=str(path))
    return str(path)


def snapshot_and_record(on_saved=None) -> int:
    path = take_snapshot()
    with db.connect() as con:
        snap_id = db.add_snapshot(con, path)
    if on_saved:
        threading.Thread(target=on_saved, args=(snap_id,), daemon=True).start()
    return snap_id


def start_hotkey(on_saved=None):
    """Listen for the hotkey in the background. Returns the listener or None."""
    try:
        from pynput import keyboard
    except Exception as e:  # no display / not installed
        print(f"[hotkey] disabled: {e}")
        return None

    def fire():
        try:
            snap_id = snapshot_and_record(on_saved)
            print(f"[hotkey] saved snapshot #{snap_id}")
        except Exception as e:
            print(f"[hotkey] screenshot failed: {e}")

    listener = keyboard.GlobalHotKeys({config.HOTKEY: fire})
    listener.daemon = True
    listener.start()
    print(f"[hotkey] press {config.HOTKEY} in game to save a snapshot")
    return listener
