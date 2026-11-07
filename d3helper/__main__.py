"""Start D3 Helper:  python -m d3helper  [--no-overlay]"""
import argparse
import queue
import signal
import threading
import webbrowser

from . import capture, config, winutil
from .web import app, read_snapshot


def start_web(open_browser: bool):
    url = f"http://localhost:{config.PORT}"
    t = threading.Thread(target=lambda: app.run(host="127.0.0.1", port=config.PORT, debug=False,
                                                use_reloader=False), daemon=True)
    t.start()
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    return url


def run_overlay():
    from .engine import Engine
    from .overlay import Overlay

    q = queue.Queue()
    engine = Engine(q)
    hint = (f"{_k(config.KEY_SAVE)} save · {_k(config.KEY_EQUIP)} I'm wearing it · "
            f"{_k(config.HOTKEY)} ask Claude · {_k(config.KEY_TOGGLE)} hide")
    overlay = Overlay(q, hint)
    capture.start_hotkeys({
        config.KEY_TOGGLE: engine.toggle,
        config.HOTKEY: engine.ask_claude,
        config.KEY_SAVE: engine.save_hovered,
        config.KEY_EQUIP: engine.equip_hovered,
    })
    threading.Thread(target=engine.run, daemon=True).start()
    signal.signal(signal.SIGINT, lambda *_: overlay.quit())
    q.put(("toast", "D3 Helper overlay on. Hover an item in game."))
    _keepalive(overlay)
    overlay.run()
    engine.stop()


def _keepalive(overlay):
    # Lets Ctrl+C reach Python while Tk's loop is running.
    overlay.root.after(250, lambda: _keepalive(overlay))


def _k(key: str) -> str:
    return key.strip("<>").upper()


def main():
    p = argparse.ArgumentParser(prog="d3helper")
    p.add_argument("--no-overlay", action="store_true", help="web app + snapshot hotkey only")
    p.add_argument("--no-browser", action="store_true", help="don't open the dashboard on start")
    args = p.parse_args()

    winutil.init_dpi()
    config.ensure_dirs()
    url = start_web(open_browser=not args.no_browser)
    print(f"D3 Helper dashboard: {url}  (Ctrl+C to stop)")

    if config.OVERLAY and not args.no_overlay:
        run_overlay()
    else:
        on_saved = read_snapshot if (config.vision_enabled() and config.AUTO_READ) else None
        capture.start_hotkey(on_saved)
        threading.Event().wait()


if __name__ == "__main__":
    main()
