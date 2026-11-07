"""Start D3 Helper:  python -m d3helper"""
import threading
import webbrowser

from . import capture, config
from .web import app, read_snapshot


def main():
    config.ensure_dirs()
    on_saved = read_snapshot if (config.vision_enabled() and config.AUTO_READ) else None
    capture.start_hotkey(on_saved)
    url = f"http://localhost:{config.PORT}"
    print(f"D3 Helper running at {url}  (Ctrl+C to stop)")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=config.PORT, debug=False)


if __name__ == "__main__":
    main()
