# Extreme Sudoku — web

A mobile-first static Sudoku application with no frontend build step or runtime dependencies. It admits verified Easy/Medium/Hard/Expert (`verification.status: VERIFIED`) and certified Extreme/Ultra Extreme from `../data/production/puzzles.json`; the demo `../data/puzzles.json` is test-fixture data and is never loaded by the app. There is no mock or silent fallback: a failed load shows an error message, an empty database shows "no verified puzzles".

The first visit requires a local profile: a trimmed name of 1–32 Unicode code points and preparation (Beginner → Easy, Amateur → Medium, Experienced → Hard, Expert → Expert). This suggests a default level; all categories with published puzzles remain selectable. Profile edits keep existing games and results. There are no accounts, network saves or device synchronization.

New Game selects only never-started puzzle IDs. Exhausted levels offer other levels or explicit continuation of an unfinished game, never replay. The home screen lists unfinished games. Completed games cannot be restarted; restarting an unfinished game requires confirmation and creates a new attempt. Progress remains isolated by puzzle ID. Standard Details show verification, rating, hardest technique and the logical technique summary without Extreme certification claims. Python validates full proof evidence before publishing; the browser checks compact metadata and never solves or re-rates puzzles.

Serve the repository root with a static HTTP server and open `/web/`:

```sh
python -m http.server 8000
```

Open `http://localhost:8000/web/`. Production requires HTTPS and a browser supporting Web Locks; loopback HTTP is suitable for local testing. ES modules and JSON fetch do not support `file://`. One tab holds the profile write lock; additional tabs wait without saving or migrating anything. Closing the owner releases the lock, after which the waiting tab reads current storage. Unsupported browsers receive an explanation without modifying data. The database URL comes from `<meta name="puzzle-database">` in `index.html` (relative to the page).

## GitHub Pages

Run `node ../scripts/build_pages.mjs` (from the project root: `node scripts/build_pages.mjs`) to produce `dist/`: the web files at its root plus `data/production/puzzles.json` (proof evidence stripped, meta tag rewritten to `./data/...`). All URLs are relative, so `https://<owner>.github.io/<repo>/` works. `.github/workflows/pages.yml` runs tests, validates the database, builds and deploys. See the root README.

## Layout and controls

- Phones: compact title and information, near-full-width board, 5 + 4 number pad, permanently visible Undo / Erase / Notes / Hint. Secondary actions live in the menu.
- Short landscape: board limited by the safe viewport height; information and controls sit to its right.
- Tablet portrait: a 600 px board above a single-row number pad and actions.
- Tablet landscape and desktop: a board up to 600 px beside the control panel.
- Safe-area padding covers all four edges. `svh` stabilizes the short-landscape board while `dvh` constrains dialogs. Content can scroll vertically on unusually short screens; page zoom remains available.

Keyboard: arrows to select, 1–9 to enter, N for pencil notes, Backspace / Delete / 0 to erase, Ctrl or Command + Z to undo, Escape to close dialogs. The board uses buttons with roving focus, so selecting cells does not open a mobile keyboard.

Settings include Light / Dark / System, immediate / full-board / disabled mistake checking, and automatic peer-note removal. Pause conceals the board and stops the timer. Time measures active play: hiding/leaving the page or going home pauses; returning, reloading and opening a saved game require explicit Resume. Reload never adds offline time. On abrupt termination without lifecycle events the last saved checkpoint is used (autosave every 10 seconds and after moves).

Progress retains the existing `extreme-sudoku.progress.v2` key and schema. The profile uses `extreme-sudoku.profile.v1`; permanent seen IDs and attempt results use `extreme-sudoku.activity.v1`. Completed results are idempotent by attempt ID. A restart summary embedded in the new progress snapshot repairs its history if a secondary write failed. Existing legacy and v2 progress are adopted without clearing unrelated data. Old elapsed time is preserved as `legacy-mixed`, dates/check settings are not invented, and old solved IDs without detailed records remain identifiable. The permanent seen set is not limited by the former 1,000-ID recent list or progress cleanup.

Statistics show unique solved puzzles, completed attempts without reveals, unfinished games, per-level completions/mean active time, attempt history and personal time records. Records separate reveals, check mode and automatic notes; mixed check modes and legacy times are excluded. Undo never refunds a reveal. Error counters depend on check mode; zero with checks off is not proof of an error-free solve. Results remain in this browser only and disappear when site data is cleared. Storage errors are visible; failed saves prevent leaving the current game for a new attempt until saving succeeds.

Hints explicitly confirm revealing one correct cell. These are basic reveals, not logical technique deductions. The certification badge opens Puzzle Details (ID, certification, clues, project rating, hardest recorded step, bottlenecks, techniques, versions). Generator, Human Solver, and the data contract are independent and unchanged.

## Files

- `index.html`, `styles.css`, `app.js`: accessible page, responsive styles, DOM rendering and interaction.
- `lib/game.js`: game state and operations.
- `lib/data.js`: data loading and validation.
- `lib/storage.js`: persistence.
- `tests/` and `VALIDATION.md`: automated checks and browser verification, when present.

The viewport matrix and measured board / cell / note sizes are recorded in `VALIDATION.md`. Desktop WebKit emulation checks layout and engine behavior; physical iOS Safari testing remains a separate device check.
