# D3 Helper

A Diablo 3 companion for Windows. **Hover an item in game and a card pops up next to it** telling you
what to do with it for your build.

![card](docs/overlay-card.png)

- **Overlay**: rest the mouse on an item and a card says what to do in one line:
  *"Wear it - ancient beats your normal one"*, *"Salvage - your gloves slot is done"*,
  *"Spare - Enchant Vitality → Attack Speed at the Mystic to beat yours"*.
  It compares against the "Equipped" tooltip the game shows, so upgrades work with no setup.
- **Next steps (F7)**: your top 3 to-dos on screen, e.g. *"Get Pauldrons of the Wastes - Kadala shoulders,
  25 shards a try, can do ×25"*, plus what to farm when you're short (*"Farm Arreat War Tapestry: Act III
  bounties. Need 2 more for Extract Ambo's Pride"*). Warns when your blood shards are near the cap.
- **Stat goals**: the lowest roll you'll accept per slot (defaults provided, edit on the Goals page). An ancient
  item that meets every goal marks the slot **done**, and from then on copies of it are just salvage.
- **Reads your stuff (F6)**: open your inventory and press F6. Gold, blood shards and materials it can see are
  saved and the plan updates. If it misses one, show it where the number is on the **Calibrate** page (two clicks).
- **Learns what you wear**: when the game shows its "Equipped" comparison tooltip, the app remembers that item.
  No setup needed for upgrade calls or the plan.
- **Session stats**: items checked, upgrades found, and farming rates (Death's Breath per hour, etc.) on the
  dashboard and the F7 card. A chime plays when an upgrade shows up.
- **Clean up**: the Stash page lists saved items that turned into salvage once a slot was done.
- **Hotkeys**:

  | Key | Does |
  |---|---|
  | F6 | Read gold / shards / materials from the screen |
  | F7 | Show / hide next steps |
  | F8 | Card: simple → details → off |
  | F9 | Ask Claude to read the hovered tooltip (needs an API key), or just save a screenshot |
  | F10 | Save the hovered item to your stash list |
  | F11 | "I'm wearing this": remembers the hovered item as equipped |
  | F12 | **That's wrong**: saves exactly what the app saw so it can be fixed |

- **Dashboard** (opens in your browser): next steps, session, build checklist, **My stuff**, **Goals**,
  Kanai's Cube tracker, stash list, **Debug**, snapshots.

Hover reading uses the OCR built into Windows: free, offline, nothing leaves your PC.

## Setup

1. Install Python 3.12 or 3.13 from python.org (tick "Add Python to PATH").
2. Download this repo (Code → Download ZIP) and unzip it.
3. Double-click `run.bat`. The first run installs everything.
4. In Diablo 3: **Options → Video → Display Mode → Windowed Fullscreen**. In plain Fullscreen, Windows can't draw
   the overlay on top of the game.

If the overlay says the English OCR language pack is missing, open PowerShell as administrator and run:

```
Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"
```

## When it gets something wrong

Press **F12** right then. The app saves the screen plus every bit of text it read, with positions and colours,
to `data\feedback`. Then either:

- open the **Debug** page to see what it read, and click **Make it a test case**, or
- hand the folder to Claude Code (`CLAUDE.md` explains the workflow). Each saved screen becomes a test in
  `tests/screens/`, so once something is fixed it stays fixed: `python -m d3helper.fixtures check`.

Most fixes are a word or number in `d3helper/screen_profile.json` (tooltip size, item type words, colours,
where your gold is), not code.

Other knobs:
- **Card never shows**: Diablo III must be the focused window and in Windowed Fullscreen.
  `D3H_DEBUG=1` in `.env` saves every read to `data\debug`.
- **Names/stats misread**: try `"scale": 1.5` under `ocr` in `screen_profile.json`, or press F9 to ask Claude.
- **Card covers something**: pin it with `D3H_CARD_POS=40,40`.

All settings are in `.env.example` (copy it to `.env`).

## Optional extras

| Setting | What it unlocks | Cost |
|---|---|---|
| `ANTHROPIC_API_KEY` | F9: Claude reads the hovered tooltip | a few cents per read |
| `BLIZZARD_CLIENT_ID` / `_SECRET` | Import equipped gear by BattleTag on the dashboard | free ([develop.battle.net](https://develop.battle.net/access/clients)) |

## Your build and game data

Cube recipe costs, Kadala prices and farming spots are in `d3helper/game_data.json`; entries marked `verify`
should be checked in game. The build lives in `d3helper/builds/ww_rend_barb.json`. Slots marked `"verify": true` are a best guess; check them
against a current guide (Maxroll / Icy Veins) for your season. Edit item names or stat weights
(3 = must have, 2 = strong, 1 = nice) and restart.

## Development

```
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest
python -m d3helper            # --no-overlay for dashboard only
```
