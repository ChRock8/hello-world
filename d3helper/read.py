"""See what the overlay sees in a screenshot. Handy for tuning on your PC.

    python -m d3helper.read data\\snapshots\\snap_xxx.png --cursor 1500,600
    python -m d3helper.read data\\feedback\\20261107_120000      (a saved capture, no OCR needed)
"""
import argparse
import json
import queue
from pathlib import Path

from . import ocr, tooltip
from .engine import Engine


def main():
    p = argparse.ArgumentParser(prog="d3helper.read")
    p.add_argument("path", help="screenshot .png, a saved capture folder, or a .json with OCR lines")
    p.add_argument("--cursor", default="", help="mouse position x,y (default: right side of screen)")
    p.add_argument("--height", type=int, default=1080, help="screen height (for .json input)")
    args = p.parse_args()

    path = Path(args.path)
    img = None
    if path.is_dir():  # a saved capture folder (data/feedback/..., tests/screens/...)
        from .captures import load
        cap, _ = load(path)
        lines, (width, height) = cap.lines, cap.screen
        cursor = cap.cursor or (int(width * 0.8), height // 2)
        args.cursor = args.cursor or f"{cursor[0]},{cursor[1]}"
    elif path.suffix.lower() == ".json":
        lines = [ocr.OcrLine(**d) for d in json.loads(path.read_text())["lines"]]
        height, width = args.height, int(args.height * 16 / 9)
    else:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        lines = ocr.recognize(img)
        width, height = img.size
    cursor = tuple(int(n) for n in args.cursor.split(",")) if args.cursor else (int(width * 0.8), height // 2)

    print(f"OCR found {len(lines)} lines")
    if img is not None:
        tooltip.annotate_colors(lines, img)
    tips = tooltip.find_tooltips(lines, height)
    if not tips:
        print("No item tooltip found. Text seen:")
        for l in lines:
            print(f"  ({l.x},{l.y}) {l.text}")
        return
    hovered, compares = tooltip.pick(tips, cursor)
    for t in tips:
        tag = "HOVERED" if t is hovered else ("EQUIPPED" if t.equipped else "other")
        print(f"\n[{tag}] {t.name} | {t.type} | {t.quality} {t.rarity}")
        for a in t.affix_lines:
            print(f"   {a}")
        if t.legendary_power:
            print(f"   power: {t.legendary_power}")
    r = Engine(queue.Queue()).judge(hovered.to_item(), [c.to_item() for c in compares], hovered.box, (width, height))
    v = r.verdict
    print(f"\nVerdict: {v.action} {v.score}/100 ({v.slot}) - {v.headline}")
    for line in v.reasons + ([f"Missing: {', '.join(v.missing)}"] if v.missing else []) + ([v.reroll] if v.reroll else []):
        print(f"  {line}")


if __name__ == "__main__":
    main()
