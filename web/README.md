# Extreme Sudoku — web

A mobile-first static Sudoku application with no frontend build step or runtime dependencies. Release 0.1 plays only the certified puzzles in `../data/production/puzzles.json` (statuses `CERTIFIED_EXTREME` / `CERTIFIED_ULTRA_EXTREME`); the demo `../data/puzzles.json` is test-fixture data and is never loaded by the app. There is no mock or silent fallback: a failed load shows an error message, an empty database shows "no certified puzzles".

Serve the repository root with a static HTTP server and open `/web/`:

```sh
python -m http.server 8000
```

Open `http://localhost:8000/web/`. ES modules and JSON fetch require HTTP; `file://` is not supported. The database URL comes from `<meta name="puzzle-database">` in `index.html` (relative to the page).

## GitHub Pages

Run `node ../scripts/build_pages.mjs` (from the project root: `node scripts/build_pages.mjs`) to produce `dist/`: the web files at its root plus `data/production/puzzles.json` (proof evidence stripped, meta tag rewritten to `./data/...`). All URLs are relative, so `https://<owner>.github.io/<repo>/` works. `.github/workflows/pages.yml` runs tests, validates the database, builds and deploys. See the root README.

## Layout and controls

- Phones: compact title and information, near-full-width board, 5 + 4 number pad, permanently visible Undo / Erase / Notes / Hint. Secondary actions live in the menu.
- Short landscape: board limited by the safe viewport height; information and controls sit to its right.
- Tablet portrait: a 600 px board above a single-row number pad and actions.
- Tablet landscape and desktop: a board up to 600 px beside the control panel.
- Safe-area padding covers all four edges. `svh` stabilizes the short-landscape board while `dvh` constrains dialogs. Content can scroll vertically on unusually short screens; page zoom remains available.

Keyboard: arrows to select, 1–9 to enter, N for pencil notes, Backspace / Delete / 0 to erase, Ctrl or Command + Z to undo, Escape to close dialogs. The board uses buttons with roving focus, so selecting cells does not open a mobile keyboard.

Settings include Light / Dark / System, immediate / full-board / disabled mistake checking, and automatic peer-note removal. Pause conceals the board and stops the timer. The timer is wall-clock (derived from timestamps, not timers): it keeps running while the page is hidden or Safari is in the background, a reload adds the time elapsed since the last save, and only the explicit Pause (or completion) freezes it. Progress is stored per puzzle ID (`extreme-sudoku.progress.v2`, `storageSchemaVersion` 2) and preferences in localStorage; storage failure displays a nonblocking status.

Hints explicitly confirm revealing one correct cell. These are basic reveals, not logical technique deductions. The certification badge opens Puzzle Details (ID, certification, clues, project rating, hardest recorded step, bottlenecks, techniques, versions). Generator, Human Solver, and the data contract are independent and unchanged.

## Files

- `index.html`, `styles.css`, `app.js`: accessible page, responsive styles, DOM rendering and interaction.
- `lib/game.js`: game state and operations.
- `lib/data.js`: data loading and validation.
- `lib/storage.js`: persistence.
- `tests/` and `VALIDATION.md`: automated checks and browser verification, when present.

The viewport matrix and measured board / cell / note sizes are recorded in `VALIDATION.md`. Desktop WebKit emulation checks layout and engine behavior; physical iOS Safari testing remains a separate device check.
