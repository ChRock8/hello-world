"""A 'capture' is everything the app saw at one moment: the screenshot (optional),
the OCR text lines with their positions and colours, the screen size and the cursor.

Captures are saved as small folders (screen.png + capture.json). They power the
F12 "that's wrong" button, the Debug page, and the screenshot regression tests -
the JSON alone is enough to re-run the reader without Windows or OCR.
"""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import screen_resources, tooltip
from .ocr import OcrLine


@dataclass
class Capture:
    screen: tuple
    cursor: tuple | None
    lines: list
    img: object = None
    ms: int = 0
    taken: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    def to_json(self) -> dict:
        return {"screen": list(self.screen), "cursor": list(self.cursor) if self.cursor else None,
                "ms": self.ms, "taken": self.taken, "lines": [l.to_dict() for l in self.lines]}

    @classmethod
    def from_json(cls, data: dict, img=None) -> "Capture":
        return cls(tuple(data["screen"]), tuple(data["cursor"]) if data.get("cursor") else None,
                   [OcrLine(**l) for l in data["lines"]], img, data.get("ms", 0), data.get("taken", ""))


def read(cap: Capture) -> dict:
    """What the app reads from a capture, in a plain form tests can compare."""
    tips = tooltip.find_tooltips(cap.lines, cap.screen[1])
    hovered, compares = tooltip.pick(tips, cap.cursor)

    def item(t):
        it = t.to_item()
        return {"name": t.name, "type": t.type, "quality": t.quality, "rarity": t.rarity,
                "affixes": it["affixes"], "legendary_power": t.legendary_power}

    return {"hovered": item(hovered) if hovered else None,
            "equipped": [item(c) for c in compares],
            "resources": screen_resources.read_resources(cap.lines, cap.screen)}


def save(cap: Capture, folder: Path, extra: dict | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    if cap.img is not None:
        cap.img.save(folder / "screen.png")
    data = cap.to_json()
    data.update(extra or {})
    (folder / "capture.json").write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    return folder


def load(folder: Path) -> tuple[Capture, dict]:
    data = json.loads((folder / "capture.json").read_text(encoding="utf-8"))
    img = None
    if (folder / "screen.png").exists():
        try:
            from PIL import Image
            img = Image.open(folder / "screen.png")
        except Exception:
            img = None
    return Capture.from_json(data, img), data


def list_folders(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted((p for p in root.iterdir() if (p / "capture.json").exists()), reverse=True)
