"""Load build templates (JSON files in d3helper/builds/)."""
import json
from functools import lru_cache

from . import config

SLOTS = ["head", "shoulders", "chest", "hands", "bracers", "waist", "legs", "feet",
         "neck", "ring1", "ring2", "main_hand", "off_hand"]
SLOT_LABELS = {"head": "Helm", "shoulders": "Shoulders", "chest": "Chest", "hands": "Gloves",
               "bracers": "Bracers", "waist": "Belt", "legs": "Pants", "feet": "Boots",
               "neck": "Amulet", "ring1": "Ring 1", "ring2": "Ring 2",
               "main_hand": "Main hand", "off_hand": "Off hand"}


def list_builds():
    return sorted(p.stem for p in config.BUILDS_DIR.glob("*.json"))


@lru_cache(maxsize=None)
def load_build(build_id: str) -> dict:
    path = config.BUILDS_DIR / f"{build_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def build_path(build_id: str):
    return config.BUILDS_DIR / f"{build_id}.json"
