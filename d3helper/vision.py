"""Optional: have Claude read an item tooltip out of a screenshot.

Only runs when ANTHROPIC_API_KEY is set. One call per screenshot.
"""
import base64
import io
from typing import Literal

from pydantic import BaseModel

from . import affixes, config

PROMPT = """This is a Diablo 3 screenshot. If an item tooltip is visible (the box that appears \
when hovering an item), transcribe it. If several tooltips are shown (hovered item plus \
'equipped' comparison), read only the hovered one, not the one labelled as equipped.

- name: the item name at the top of the tooltip.
- item_type: the type line, e.g. "Ancient Set Helm", "Legendary Ring", "Mighty Weapon".
- quality: "primal" if it says Primal Ancient, "ancient" if it says Ancient, else "normal".
- rarity: legendary, set, rare, magic or normal (from the name colour / type line).
- affix_lines: every primary and secondary stat line exactly as written, one per entry. \
Include one "Empty Socket" entry per empty socket. Skip the set bonus list, flavour text, \
legendary power description, item level and durability.
- legendary_power: the orange legendary power text, if any.

If no item tooltip is visible, set is_item_tooltip to false and leave the rest empty."""


class ItemReading(BaseModel):
    is_item_tooltip: bool
    name: str
    item_type: str
    quality: Literal["normal", "ancient", "primal"]
    rarity: Literal["legendary", "set", "rare", "magic", "normal", "unknown"]
    affix_lines: list[str]
    legendary_power: str


class VisionError(Exception):
    pass


def _encode(path: str, max_edge: int = 2400) -> str:
    from PIL import Image
    img = Image.open(path).convert("RGB")
    if max(img.size) > max_edge:
        img.thumbnail((max_edge, max_edge))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def read_tooltip(path: str) -> dict:
    """Return {name, type, quality, affixes, raw_text, legendary_power} for the item in the image."""
    if not config.vision_enabled():
        raise VisionError("Set ANTHROPIC_API_KEY to read screenshots automatically.")
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        # fallbacks="default": if a request is ever declined, the API retries it on
        # a fallback model in the same call.
        resp = client.beta.messages.parse(
            model=config.CLAUDE_MODEL,
            max_tokens=4000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_format=ItemReading,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _encode(path)}},
                {"type": "text", "text": PROMPT},
            ]}],
        )
    except anthropic.AuthenticationError as e:
        raise VisionError("Anthropic API key was rejected. Check ANTHROPIC_API_KEY.") from e
    except anthropic.RateLimitError as e:
        raise VisionError("Rate limited by the Anthropic API. Try again in a minute.") from e
    except anthropic.APIStatusError as e:
        raise VisionError(f"Anthropic API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise VisionError("Couldn't reach the Anthropic API. Check your connection.") from e

    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise VisionError("Claude couldn't read this screenshot.")
    r = resp.parsed_output
    if not r.is_item_tooltip:
        raise VisionError("No item tooltip found. Hover an item, then press the hotkey.")
    raw = "\n".join(r.affix_lines)
    return {
        "name": r.name.strip(),
        "type": r.item_type.strip(),
        "quality": r.quality,
        "affixes": affixes.parse(raw),
        "raw_text": raw,
        "legendary_power": r.legendary_power.strip(),
    }
