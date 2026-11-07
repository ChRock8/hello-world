# D3 Helper

A local companion app for Diablo 3 (Windows). It runs on your PC and opens in your browser.

- **Build checklist**: every slot of your target build, what's equipped, what's in your stash, what's missing. Kanai's Cube tracker.
- **Keep or salvage?**: enter an item (or let Claude read it from a screenshot) and get a verdict (EQUIP / UPGRADE / KEEP / CUBE / SALVAGE), a 0–100 roll score, and which stat to reroll at the Mystic.
- **Stash**: every item you've logged, searchable, tagged by location ("Stash tab 2", "Equipped", …).
- **Snapshots**: press **F9** in game to save a screenshot. With an Anthropic API key, Claude reads the hovered item's tooltip for you.
- **Import**: pull your hero's equipped gear from Blizzard's API (optional).

## Setup (Windows)

1. Install Python 3.11+ from python.org (tick "Add Python to PATH").
2. Download this repo (Code → Download ZIP) and unzip it.
3. Double-click `run.bat`. First run installs everything, then opens http://localhost:5173.

In Diablo 3, set **Display → Windowed Fullscreen**. Fullscreen mode can make screenshots come out black.

### Optional features

Copy `.env.example` to `.env` and fill in:

| Setting | What it unlocks | Cost |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude reads item tooltips from F9 snapshots | ~a few cents per read |
| `D3H_AUTO_READ=1` | Read every snapshot automatically instead of on click | same |
| `BLIZZARD_CLIENT_ID` / `_SECRET` | Import equipped gear by BattleTag | free ([develop.battle.net](https://develop.battle.net/access/clients)) |

Without either, everything still works; you type item stats yourself.

## Typing items quickly

The stats box takes shorthand: `chc chd str ias socket`. You can also paste tooltip lines like
`Critical Hit Chance Increased by 9.5%`.

Shorthand: `str vit chc chd ias cdr rcr life phys ww rend socket socket x2 dmg elite area allres armor loh`

## Your build

The build lives in `d3helper/builds/ww_rend_barb.json`. Slots marked `"verify": true` are my best guess and
should be checked against a current guide (Maxroll / Icy Veins) for your season. Edit item names
or affix weights (3 = must have, 2 = strong, 1 = nice) and restart.

To add another build, copy the file, change it, and set `D3H_BUILD=<filename without .json>` in `.env`.

## Development

```
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest
python -m d3helper
```
