"""Import a hero's equipped gear from Blizzard's Diablo 3 profile API.

Needs a free client ID/secret from https://develop.battle.net/access/clients.
Your profile must be public in-game. Blizzard's D3 API has had outages over the
years, so the app works fine without it.
"""
import requests

from . import config

SLOT_MAP = {"head": "head", "shoulders": "shoulders", "torso": "chest", "hands": "hands",
            "bracers": "bracers", "waist": "waist", "legs": "legs", "feet": "feet",
            "neck": "neck", "leftFinger": "ring1", "rightFinger": "ring2",
            "mainHand": "main_hand", "offHand": "off_hand"}


class BlizzardError(Exception):
    pass


def enabled() -> bool:
    return bool(config.BLIZZARD_CLIENT_ID and config.BLIZZARD_CLIENT_SECRET)


def _token() -> str:
    r = requests.post("https://oauth.battle.net/token", data={"grant_type": "client_credentials"},
                      auth=(config.BLIZZARD_CLIENT_ID, config.BLIZZARD_CLIENT_SECRET), timeout=15)
    if r.status_code != 200:
        raise BlizzardError(f"Blizzard login failed ({r.status_code}). Check client ID/secret.")
    return r.json()["access_token"]


def _get(path: str, token: str) -> dict:
    url = f"https://{config.BLIZZARD_REGION}.api.blizzard.com/d3/profile/{path}"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                     params={"locale": "en_US"}, timeout=20)
    if r.status_code == 404:
        raise BlizzardError("Profile/hero not found. Check the BattleTag and that your profile is public.")
    if r.status_code != 200:
        raise BlizzardError(f"Blizzard API returned {r.status_code}.")
    return r.json()


def _tag(battletag: str) -> str:
    return battletag.strip().replace("#", "-")


def list_heroes(battletag: str) -> list:
    token = _token()
    data = _get(f"{_tag(battletag)}/", token)
    return [{"id": h["id"], "name": h["name"], "class": h.get("class", ""),
             "level": h.get("level"), "seasonal": h.get("seasonal", False)}
            for h in data.get("heroes", [])]


def parse_items(items: dict) -> list:
    """Turn the API's slot->item dict into our item dicts."""
    out = []
    for api_slot, it in (items or {}).items():
        slot = SLOT_MAP.get(api_slot)
        if not slot or not isinstance(it, dict):
            continue
        attrs = it.get("attributes") or {}
        lines = [a.get("text", a) if isinstance(a, dict) else str(a)
                 for group in ("primary", "secondary") for a in attrs.get(group, [])]
        lines += ["Empty Socket"] * sum(1 for g in it.get("gems", []) or [] if not g)
        type_name = it.get("typeName") or ""
        quality = "normal"
        joined = f"{type_name} {it.get('displayColor', '')}".lower()
        if "primal" in joined:
            quality = "primal"
        elif "ancient" in joined:
            quality = "ancient"
        out.append({"slot": slot, "name": it.get("name", "?"), "type": type_name or "",
                    "quality": quality, "raw_text": "\n".join(lines)})
    return out


def hero_items(battletag: str, hero_id: int) -> list:
    token = _token()
    data = _get(f"{_tag(battletag)}/hero/{hero_id}/items", token)
    return parse_items(data)
