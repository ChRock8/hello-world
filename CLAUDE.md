# D3 Helper - notes for Claude

Diablo 3 companion app (Windows): an overlay that reads item tooltips with Windows OCR and
says what to do with each item, plus a Flask dashboard. Start: `python -m d3helper`.

## The fix loop (most work here)

The screen reader was written before anyone saw a real screenshot, so expect misreads.
1. The user presses **F12** in game when the overlay is wrong. That saves
   `data/feedback/<stamp>/` = `screen.png` + `capture.json` (every OCR line with position and colour,
   cursor, screen size, what the app read and decided).
2. See what was read: Debug page, or `python -m d3helper.read data/feedback/<stamp>`.
3. Make it a regression case: `python -m d3helper.fixtures add data/feedback/<stamp> --name <what>`
   then correct `tests/screens/<what>/expected.json` against `screen.png` and delete its `_todo` line.
4. Fix, preferring data over code:
   - layout/wording assumptions -> `d3helper/screen_profile.json` (tooltip width, type words, stop/skip
     patterns, colour thresholds, resource labels/regions). User overrides: `data/screen_profile.json`.
   - parsing logic -> `d3helper/tooltip.py` (tooltips), `d3helper/affixes.py` (stat lines),
     `d3helper/screen_resources.py` (gold/shards/materials).
   - game costs / farming text -> `d3helper/game_data.json`; build -> `d3helper/builds/ww_rend_barb.json`.
5. `python -m d3helper.fixtures check` and `python -m pytest`. Capture JSON is enough to re-run the
   reader, so all of this works without Windows or OCR (e.g. in a cloud session).

`tests/screens/synthetic_inventory_gloves` is made up (tests/fake_screen.py). Replace it with real
screens as they arrive.

## Map

- `engine.py` hover loop + hotkey actions (F6 resources, F7 plan, F8 card mode, F9 Claude, F10 save,
  F11 equipped, F12 feedback); `overlay.py` Tk click-through windows; `__main__.py` wiring.
- `evaluator.py` item verdicts (headline, score, goals, "slot done"); `planner.py` next steps + farming.
- `web.py` + `templates/` dashboard; `db.py` SQLite in `data/`.
- Windows-only bits are isolated in `winutil.py`, `ocr.py`, `capture.py`; everything else is testable on Linux.
