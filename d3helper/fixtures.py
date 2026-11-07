"""Screenshot regression tests - the fast way to fix and keep things fixed.

Each case is a folder in tests/screens/:
    capture.json   what the app saw (OCR text + positions + colours)
    expected.json  what's really on screen - check it against screen.png and fix it
    screen.png     the screenshot, for humans (optional)

    python -m d3helper.fixtures add data\\feedback\\20261107_201500 --name gloves_inventory
    python -m d3helper.fixtures add shot.png --cursor 1500,600      (Windows: runs OCR)
    python -m d3helper.fixtures check                               (what's wrong right now)

`pytest` runs every case too, so once a misread is fixed it stays fixed.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from . import builds, captures, config
from .evaluator import _norm, canonical_name

CASES_DIR = config.ROOT / "tests" / "screens"
TODO = "Check every value against screen.png, fix any mistakes, then delete this line."
TOL = 0.051


def _round(item):
    if not item:
        return item
    return {**item, "affixes": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in item["affixes"].items()}}


def expected_from(reading: dict) -> dict:
    return {"_todo": TODO, "hovered": _round(reading["hovered"]),
            "equipped": [_round(e) for e in reading["equipped"]], "resources": reading["resources"]}


def make_case(cap: captures.Capture, name: str, root: Path | None = None) -> Path:
    name = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_") or "case"
    folder = (root or CASES_DIR) / name
    if folder.exists():
        raise FileExistsError(f"{folder} already exists - pick another --name")
    captures.save(cap, folder)
    (folder / "expected.json").write_text(json.dumps(expected_from(captures.read(cap)), indent=1), encoding="utf-8")
    return folder


def _same_name(expected: str, actual: str) -> bool:
    build = builds.load_build(config.ACTIVE_BUILD)
    return _norm(canonical_name(build, actual or "")) == _norm(canonical_name(build, expected or ""))


def _diff_item(where, exp, act) -> list:
    if exp is None:
        return [] if act is None else [f"{where}: expected no item, read {act['name']!r}"]
    if act is None:
        return [f"{where}: expected {exp.get('name')!r}, found no item"]
    out = []
    if "name" in exp and not _same_name(exp["name"], act["name"]):
        out.append(f"{where} name: expected {exp['name']!r}, read {act['name']!r}")
    for key in ("quality", "rarity"):
        if key in exp and exp[key] != act.get(key):
            out.append(f"{where} {key}: expected {exp[key]!r}, read {act.get(key)!r}")
    if "affixes" in exp:
        e, a = exp["affixes"], act["affixes"]
        for k in sorted(set(e) - set(a)):
            out.append(f"{where} stat missing: {k}")
        for k in sorted(set(a) - set(e)):
            out.append(f"{where} extra stat: {k} = {a[k]}")
        for k in sorted(set(e) & set(a)):
            if e[k] is not None and (a[k] is None or abs(e[k] - a[k]) > TOL):
                out.append(f"{where} {k}: expected {e[k]}, read {a[k]}")
    if exp.get("legendary_power") and exp["legendary_power"].lower() not in (act.get("legendary_power") or "").lower():
        out.append(f"{where} legendary power: expected {exp['legendary_power']!r}, read {act.get('legendary_power')!r}")
    return out


def diff(expected: dict, actual: dict) -> list:
    out = []
    if "hovered" in expected:
        out += _diff_item("hovered", expected["hovered"], actual["hovered"])
    if "equipped" in expected:
        exp, act = expected["equipped"], actual["equipped"]
        if len(exp) != len(act):
            out.append(f"equipped tooltips: expected {len(exp)}, read {len(act)}")
        for i, (e, a) in enumerate(zip(exp, act)):
            out += _diff_item(f"equipped[{i}]", e, a)
    for k, v in (expected.get("resources") or {}).items():
        got = actual["resources"].get(k)
        if got != v:
            out.append(f"resource {k}: expected {v}, read {got}")
    return out


def cases(root: Path | None = None) -> list[Path]:
    return sorted(p for p in (root or CASES_DIR).glob("*") if (p / "expected.json").exists())


def check_case(folder: Path) -> tuple[list, bool]:
    cap, _ = captures.load(folder)
    expected = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
    return diff(expected, captures.read(cap)), "_todo" not in expected


def _capture_from_image(path: Path, cursor) -> captures.Capture:
    from PIL import Image
    from . import ocr, profile, tooltip
    img = Image.open(path).convert("RGB")
    lines = ocr.recognize(img, profile.load()["ocr"]["scale"])
    tooltip.annotate_colors(lines, img)
    return captures.Capture((img.width, img.height), cursor or (int(img.width * 0.8), img.height // 2), lines, img)


def main(argv=None):
    p = argparse.ArgumentParser(prog="d3helper.fixtures")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="turn a feedback folder or screenshot into a test case")
    a.add_argument("source")
    a.add_argument("--name", default="")
    a.add_argument("--cursor", default="", help="x,y (screenshots only)")
    sub.add_parser("check", help="run every case and list what's wrong")
    args = p.parse_args(argv)

    if args.cmd == "add":
        src = Path(args.source)
        if src.is_dir():
            cap, _ = captures.load(src)
        else:
            cursor = tuple(int(n) for n in args.cursor.split(",")) if args.cursor else None
            cap = _capture_from_image(src, cursor)
        folder = make_case(cap, args.name or src.stem)
        if src.is_dir() and (src / "screen.png").exists() and not (folder / "screen.png").exists():
            shutil.copy(src / "screen.png", folder / "screen.png")
        print(f"Created {folder}\nOpen expected.json next to screen.png, fix anything wrong, delete the _todo line.")
        return 0

    bad = 0
    for folder in cases():
        problems, verified = check_case(folder)
        tag = "" if verified else "  (not checked by a human yet)"
        print(f"{'FAIL' if problems else 'ok  '} {folder.name}{tag}")
        for line in problems:
            print(f"       {line}")
        bad += bool(problems)
    print(f"\n{len(cases()) - bad}/{len(cases())} screens read correctly")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
