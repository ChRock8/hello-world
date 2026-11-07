"""Read text off the screen with the OCR engine built into Windows 10/11.

Free, offline, and usually well under a second for a full screen.
"""
import asyncio
from dataclasses import dataclass, asdict


@dataclass
class OcrLine:
    text: str
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def bottom(self):
        return self.y + self.h

    def to_dict(self):
        return asdict(self)


class OcrUnavailable(Exception):
    pass


def available() -> bool:
    try:
        import winocr  # noqa: F401
        return True
    except Exception:
        return False


async def _await(awaitable):
    return await awaitable


def recognize(img, scale: float = 1.0, lang: str = "en") -> list[OcrLine]:
    """OCR a PIL image. Returns one OcrLine per text line, in screen pixels."""
    try:
        import winocr
    except Exception as e:
        raise OcrUnavailable("Windows OCR isn't available (pip install winocr; Windows 10/11 only).") from e
    if scale != 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    try:
        result = asyncio.run(_await(winocr.recognize_pil(img, lang)))
    except AssertionError as e:
        raise OcrUnavailable(
            "English OCR language pack missing. In an admin PowerShell run: "
            'Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"') from e
    lines = []
    for line in result.lines:
        rects = [w.bounding_rect for w in line.words]
        if not rects:
            continue
        x0 = min(r.x for r in rects)
        y0 = min(r.y for r in rects)
        x1 = max(r.x + r.width for r in rects)
        y1 = max(r.y + r.height for r in rects)
        lines.append(OcrLine(line.text, int(x0 / scale), int(y0 / scale),
                             int((x1 - x0) / scale), int((y1 - y0) / scale)))
    return lines
