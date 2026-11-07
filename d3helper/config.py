"""Settings, read from environment variables or a .env file next to the app."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("D3H_DATA_DIR", ROOT / "data"))
SNAP_DIR = DATA_DIR / "snapshots"
DEBUG_DIR = DATA_DIR / "debug"
DB_PATH = DATA_DIR / "d3helper.sqlite"
BUILDS_DIR = Path(__file__).resolve().parent / "builds"


def _load_dotenv():
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_dotenv()

PORT = int(os.environ.get("D3H_PORT", "5173"))
ACTIVE_BUILD = os.environ.get("D3H_BUILD", "ww_rend_barb")

# Overlay: hover an item, get a verdict on top of the game.
OVERLAY = os.environ.get("D3H_OVERLAY", "1") == "1"
HOVER_MS = int(os.environ.get("D3H_HOVER_MS", "350"))      # mouse rest time before reading
REQUIRE_GAME = os.environ.get("D3H_REQUIRE_GAME", "1") == "1"  # only read while D3 is focused
GAME_TITLE = os.environ.get("D3H_GAME_TITLE", "Diablo III")
OCR_SCALE = float(os.environ.get("D3H_OCR_SCALE", "1.0"))  # try 1.5 if names are misread
CARD_POS = os.environ.get("D3H_CARD_POS", "auto")          # "auto" or fixed "x,y"
CARD_MODE = os.environ.get("D3H_CARD_MODE", "simple")      # simple (one line) or full (all details)
DEBUG = os.environ.get("D3H_DEBUG", "0") == "1"            # save what the overlay saw to data/debug

# Hotkeys (pynput format).
HOTKEY = os.environ.get("D3H_HOTKEY", "<f9>")              # snapshot / ask Claude
KEY_PLAN = os.environ.get("D3H_KEY_PLAN", "<f7>")          # show next steps in game
KEY_TOGGLE = os.environ.get("D3H_KEY_TOGGLE", "<f8>")      # simple -> full -> off
KEY_SAVE = os.environ.get("D3H_KEY_SAVE", "<f10>")
KEY_EQUIP = os.environ.get("D3H_KEY_EQUIP", "<f11>")

# Optional: Claude reads item tooltips from screenshots.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("D3H_CLAUDE_MODEL", "claude-opus-5-5")
AUTO_READ = os.environ.get("D3H_AUTO_READ", "0") == "1"

# Optional: Blizzard API, for importing equipped gear (develop.battle.net).
BLIZZARD_CLIENT_ID = os.environ.get("BLIZZARD_CLIENT_ID", "")
BLIZZARD_CLIENT_SECRET = os.environ.get("BLIZZARD_CLIENT_SECRET", "")
BLIZZARD_REGION = os.environ.get("BLIZZARD_REGION", "us")


def vision_enabled() -> bool:
    return bool(ANTHROPIC_API_KEY)


def ensure_dirs():
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
