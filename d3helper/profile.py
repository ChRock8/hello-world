"""The screen profile: layout assumptions, in data files instead of code.

Defaults: d3helper/screen_profile.json. Your overrides: data/screen_profile.json.
"""
import copy
import json
from pathlib import Path

from . import config

DEFAULT_PATH = Path(__file__).resolve().parent / "screen_profile.json"
_cache = None
_version = 0


def user_path() -> Path:
    return config.DATA_DIR / "screen_profile.json"


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def load() -> dict:
    global _cache
    if _cache is None:
        _cache = deep_merge(_read(DEFAULT_PATH), _read(user_path()))
    return _cache


def version() -> int:
    """Bumps whenever the profile is reloaded, so compiled rules know to rebuild."""
    load()
    return _version


def reload() -> dict:
    global _cache, _version
    _cache = None
    _version += 1
    return load()


def save_override(keys: list, value):
    """Set one value in data/screen_profile.json, e.g. (["resources", "gold", "region"], [..])."""
    data = _read(user_path())
    node = data
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value
    user_path().parent.mkdir(parents=True, exist_ok=True)
    user_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    reload()
