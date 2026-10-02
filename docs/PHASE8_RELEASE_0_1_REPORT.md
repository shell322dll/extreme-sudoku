# Phase 8 / Release 0.1 — certified production puzzles in the frontend

Date: 2026-10-02. Scope: `web/`, `scripts/`, `.github/workflows/pages.yml`, README/docs. Generator, solvers,
rating, evolution and certification code were not changed or run (only the read-only validator).

## Baseline (before any change)

| Check | Result |
| --- | --- |
| Frontend unit tests (`node --test`) | 16 / 16 pass |
| Browser regression (Chromium + WebKit) | 14 check groups (7 per engine) pass |
| Responsive layouts | 56 (14 viewports x 2 themes x 2 engines) pass |
| `validate_production_database` (generator.certification.io) | OK, 1 puzzle, 1.8 s (no CLI existed; see `scripts/validate_production_database.py`) |
| Python tests (`unittest discover -s generator/tests`) | 413 OK, 176 s |

## Final test results

| Check | Result |
| --- | --- |
| Frontend unit tests | **31 / 31** (16 original unchanged + 13 in `web/tests/production.test.js` + 2 in `web/tests/build.test.js`) |
| Browser regression | **26 check groups pass** (13 per engine: 7 adapted originals + 6 new; completion test now also covers Details -> back to completion), 0 failures |
| Responsive layouts | **56 / 56** pass (new assertions: badge not clipped/overlapping, badge >= 44 px) |
| Production DB validator | OK, 1 puzzle (2.2 s) |
| Python tests (sanity, generator untouched) | 413 OK, 157.5 s (final run after the remediation pass) |

The original 14 browser groups were kept but had to be adapted: they previously read the demo
`data/puzzles.json` and used the difficulty picker; they now read the production file, the
`extreme-sudoku.progress.v2` store and the single-puzzle New Game flow. Their assertions are otherwise unchanged.

## Changed / added files

Changed: `web/app.js`, `web/index.html`, `web/styles.css`, `web/lib/data.js`, `web/lib/game.js`, `web/lib/storage.js`,
`web/package.json` (1.0.0 -> 0.1.0, `build` script), `web/tests/browser_regression.py`, `web/README.md`,
`web/VALIDATION.md` (superseded notice), `README.md` (Phase 8 section), `.gitignore` (`dist/`).
Added: `web/tests/production.test.js`, `web/tests/build.test.js`, `scripts/output_dir.mjs`, `scripts/build_pages.mjs`, `scripts/validate_production_database.py`,
`.github/workflows/pages.yml`, this report. `web/artifacts/*` regenerated (screenshots + `browser-results.json`).
`web/tests/game.test.js` and `certification.test.js` are untouched.

## Production data loading architecture

`index.html` has `<meta name="puzzle-database" content="../data/production/puzzles.json">`; `app.js` resolves it against
`document.baseURI` and calls `loadProductionPuzzles(url)` (no default URL, no fallback, no mock). The generic
`parseDatabase`/`loadPuzzles` remain only for fixtures. In the built site the build script rewrites that one meta tag
to `./data/production/puzzles.json` (asserted to occur exactly once). Load or parse failure ->
"Не удалось загрузить базу Sudoku. Попробуйте обновить страницу." plus a retry button; the game stays hidden.
Version is read from `web/package.json` at runtime (single source; shown in Puzzle Details).

## Certification filtering

`parseProductionDatabase`: root must be an object with `schemaVersion === 1` (else error naming the version),
`datasetKind === "production-certified"` (else error) and a `puzzles` array. Each record must pass the structural
checks (id, 81-char puzzle/solution, digits, clue count == givens, givens == solution, valid Sudoku solution,
known difficulty, `unique === true`) **and** `certification.status` in {CERTIFIED_EXTREME, CERTIFIED_ULTRA_EXTREME}
with the matching difficulty (Extreme / Ultra Extreme). PRELIMINARY, INCONCLUSIVE, SEARCH_*, REJECTED, UNRATED,
missing certification, duplicates and broken records are skipped with `console.warn` (verified in unit and browser
tests). Unknown fields are ignored. Zero playable records -> "Сейчас нет доступных сертифицированных Sudoku." (no crash).

## Single-puzzle handling

With one puzzle, New Game (menu, desktop button, completion screen) opens a dialog with "Все доступные Certified
Sudoku уже сыграны. Можно решить эту задачу ещё раз." and a "Решить ещё раз" button (fresh start; a note says current
progress is reset). No difficulty picker, no "1 of 1 remaining". With several puzzles: a picker of difficulties that still
have unsolved puzzles ("solved" = completion list); when all are solved, the same message with a replay button. The
completion screen button reads "Available Puzzles" for one puzzle, "New Game" otherwise.

## localStorage strategy

Key `extreme-sudoku.progress.v2`: `{storageSchemaVersion: 2, activePuzzleId, games: {<puzzleId>: snapshot}}`.
Each puzzle keeps its own values, notes, selection, timer, mistakes, hints, status, undo history. Snapshots are still
validated by `SudokuGame.restore` (fingerprint, givens, notes). Corrupt JSON, other storage versions, wrong shapes or
mismatched IDs read as empty. After the database loads, `reconcileStorage` adopts a pre-0.1 single-slot save
(`extreme-sudoku.game.v1`) into the per-puzzle store and deletes the legacy key. Saves of IDs missing from the database are
**kept**; only saves untouched for 90 days are discarded (never when the database is empty). The parsed store is cached in
memory keyed by the exact stored string, so a tap does not re-parse it (an external change is detected automatically). Settings (theme, error mode, auto-remove notes) keep their v1 key. Solved IDs reuse
`extreme-sudoku.recent.v1`. Limits: a future storage version is treated as empty and then overwritten; saved undo history
is capped at 100 frames per puzzle in the saved snapshot (200 in memory).

Timer (wall-clock): derived from timestamps (`elapsedMs + now - startedAt`); the 1 s interval only repaints. The timer keeps running while
the page is hidden/backgrounded; the save is flushed on `visibilitychange`/`pagehide`. On restore of a playing game the time since the save
(`savedAt`) is added, so reload or a closed/discarded Safari tab does not lose time. A system clock moved backwards never reduces elapsed
time (live: the jump is absorbed; restore: increment clamped to 0). Only explicit Pause and completion freeze it (a paused save stays frozen
across reload). Selection taps defer the save (400 ms) to keep taps instant; everything else saves immediately.

## Loaded puzzle and displayed data

ID `puzzle-8e2b144cecb50551d96b`: 22 clues, difficulty Extreme, project rating 35, status CERTIFIED_EXTREME, tier EXTREME,
3 genuine bottlenecks, certification version 1. Main screen: "Certified Extreme" badge, "22 clues", timer. Badge tap (or
menu -> Puzzle Details) shows ID, difficulty, certification, clues, rating (labelled as the project's own scale), tier,
hardest recorded step ("Grouped AIC (35)"), bottlenecks, certification version, app version, technique counts and the
required sentence "Эта задача прошла проверку уникальности, логических доказательств и альтернативных путей в текущей версии системы Extreme Sudoku."
`hardestTechnique` is not exported by the generator (a level proof does not make one technique mandatory), so the UI states
"Hardest step in certified path", derived from `certification.evidence.certified_path` (dev) or the compact `hardestStep`
(built site). Completion: "Solved!", Certified Extreme, 22 clues, Time, Mistakes, Hints, Puzzle Details, Restart,
Available Puzzles. Completion fires only when the board equals the solution; givens are immutable (tests, all error modes).
Hint is unchanged (basic reveal with confirmation); no new solver exists in the frontend.

## Mobile layouts (measured, WebKit engine = Chromium geometry; dense 6-9 notes in every empty cell)

| Viewport | Board | Cell | Note font | Controls bottom | Layout |
| --- | ---: | ---: | ---: | ---: | --- |
| iPhone 13 portrait 390x844 | **370 px** | **40.66 px** | **11.7 px** | 725 / 844 | header, badge row, board, 5+4 number pad, Undo/Erase/Notes/Hint, no scroll |
| iPhone landscape 844x390 | 318 | 34.88 | 10 px | 319 / 390 | board left, info + pad + actions right, no scroll |
| iPad portrait 810x1080 | 600 | 66.22 | 17 px | 920 / 1080 | centered board, one-row pad below |
| iPad landscape 1080x810 | 600 | 66.22 | 17 px | 575 / 810 | board left; info, 3x3 pad, actions, New Game right |
| 375x667 / 430x932 | 355 / 410 | 39 / 45.11 | 11.25 / 12.9 | 646 / 765 | portrait |
| 1366x768 / 1920x1080 | 600 | 66.22 | 17 | 575 | two columns |

Number Pad: 5+4 on phones (wide-screen: 9-in-a-row on tablet portrait, 3x3 on landscape tablet/desktop); on phones taller
than 780 px keys grow to 58 px and actions to 64 px (previously 52/59). Primary actions: Undo, Erase, Notes, Hint always
visible; Notes shows "Notes on" text, a filled background and dashed pad keys (not colour alone). Restart, Settings, Details,
New Game live in the menu. Header is 48 px; the badge row is 36 px tall (44 px tap target via negative margin).
Safe area: `.app` padding uses all four `env(safe-area-inset-*)`; landscape board size subtracts left/right insets; dialogs
keep a bottom inset margin. Insets are 0 in these desktop engines, so this is verified by code review only.
Safari viewport: `viewport-fit=cover`, zoom allowed (no `user-scalable=no`), `100vh -> 100svh -> 100dvh` fallbacks for the body,
`svh` for the short-landscape board, `dvh` for dialogs. Touch: cells are `<button>`s (no input, no keyboard), `user-select:none`,
`-webkit-touch-callout:none`, `touch-action:manipulation`, board `contextmenu` suppressed; tests cover tap, repeated tap,
800 ms long press (no text selection), scroll attempts, no horizontal scroll, rotate-and-reload keeping the game.
Accessibility: `focus-visible` outlines, desktop keys (arrows, 1-9, N, Backspace, Ctrl+Z), ARIA labels per cell, selected-note contrast >= 4.5:1.

Screenshots (`web/artifacts/{chromium,webkit}-{iphone,ipad}-{portrait,landscape}-{light,dark}.png`, plus
`*-details-390.png`, `*-completion-390.png`) were inspected for: board size, clipped Number Pad, note legibility, badge
overlap, header height, controls below the fold, dark contrast, horizontal scroll. Findings fixed: spare vertical space on tall phones
(larger keys), badge row height regression on short screens (restored to the previous overflow of 5/9/53 px at 1366x768 / 375x667 / 320x568 — unchanged from baseline).
Open observation: 10 px notes in phone landscape are small but legible.

## GitHub Pages base path, build and deploy

`node scripts/build_pages.mjs [--out DIR]` (`--out` is allow-listed: `dist`, a sub-path of `dist/`, or a sub-folder of the OS temp dir; anything else, e.g. `data/production`, is refused and tested) produces `dist/`: `index.html`, `styles.css`, `app.js`, `lib/`, `package.json`,
`data/production/puzzles.json`, `.nojekyll`. The JSON is derived, not copied by hand: `certification.evidence` and `config` are removed and
`hardestStep` added, root marked `derived: true` (documented in DATA_FORMAT section 56; such a file is not valid input for `validate_production_database`) (392 745 -> 1 208 bytes for one puzzle; scales to a few KB per puzzle). The script refuses to publish invalid/uncertified
records and fails on any root-absolute URL (`src/href="/…"`, `url(/…)`, `from '/…'`, `fetch('/…')`) in published html/css/js. The browser suite
builds `dist/` and serves it under `/repo-name/`, verifying: app starts, every request stays under the prefix, no 4xx/failed request,
no console errors, JSON transfer 1 508 bytes. Workflow `.github/workflows/pages.yml`: checkout -> setup-node 20 -> `npm test` ->
setup-python + `validate_production_database.py` (fail on invalid) -> `build_pages.mjs` -> configure-pages -> upload-pages-artifact (`dist`) -> deploy-pages.
No generator/certification step; no remote URL invented. Not executed on GitHub (no repository/remote here); YAML parses, steps were run locally.
Required one-off setting: repository Settings -> Pages -> Source = GitHub Actions. The project is not a git repository, so branch name `main` is an assumption.

## Production DB validation

`scripts/validate_production_database.py [path]` calls `generator.certification.io.validate_production_database` (fresh re-certification of every
record, metadata comparison, stats check). Exit 0 valid (empty is valid), 1 invalid, 2 unreadable. Current database: OK.

## Browser / E2E / performance

New browser groups (per engine): production load + certification display + Puzzle Details; real-puzzle E2E (select, enter, notes, auto-remove +
atomic undo, erase, givens, timer, reload resume, hidden-time keeps counting, restart); wall-clock restore (a 30 s old save resumes +30 s, paused save stays frozen); completion (wrong full board does not complete, exact solution does,
reload restores the completed screen, replay); touch/selection/callout/zoom; loader errors (empty, only PRELIMINARY/INCONCLUSIVE/…, unsupported schema, wrong
kind, invalid JSON, HTTP 404, mixed valid+invalid); unknown/legacy puzzle IDs; dist under sub-path.
Performance (local, 390x844, production file, one run; DEV layout loads the full 392 KB JSON):

| | Chromium | WebKit |
| --- | ---: | ---: |
| DOMContentLoaded | 26 ms | 24 ms |
| JSON fetch + parse (dev, 392 KB) | 14 ms | 13 ms |
| First render of game | 40 ms | 39 ms |
| Cell select -> next frame, median / p95 | 16.5 / 17.5 ms | 8 / 11 ms |
| Built-site JSON | 1 508 B transferred | 1 508 B |

These are desktop numbers, not iPhone numbers.

## Known limitations

- No real iOS Safari/iPhone/iPad was available. WebKit in Playwright (desktop, Windows) is a proxy: real safe-area insets, dynamic toolbar resizing,
  OLED contrast, pinch zoom, and on-device long-press/callout/keyboard behaviour are NOT verified.
- GitHub Actions workflow was not run on GitHub; Pages deployment and the public URL are untested.
- Only one puzzle exists; multi-puzzle picking/"solved" logic is unit-light (covered by code paths, not by an E2E with several puzzles).
- Timer is wall-clock by user requirement: leaving a game open in the background keeps counting; there is no automatic pause.
- Legacy `data/puzzles.json` and `web/VALIDATION.md` numbers describe the previous demo build.
- Generator observation (not changed): `hardestTechnique` is intentionally not exported; the UI therefore shows the hardest step of the recorded path.

## Readiness for iPhone 13

Functionally ready: the certified puzzle loads, can be started, played (numbers, notes, undo, erase, hint, pause), survives reload/rotation and
completes with the specified screen; layouts and touch behaviour pass in Chromium and WebKit emulation at 390x844. The final confirmation requires a
manual pass on a physical iPhone 13 and iPad (safe areas, toolbar, touch) after the first Pages deploy.

## Exact commands

```console
# local run (open http://localhost:8000/web/)
python -m http.server 8000
# unit tests (from web/; Node 20+)
npm test
# production database validation
python scripts/validate_production_database.py
# production build, then preview exactly as Pages would serve it
node scripts/build_pages.mjs
python -m http.server 8000 --directory dist
# browser/E2E/responsive (Playwright; builds dist itself)
python web/tests/browser_regression.py [--browser chromium|webkit]
# Pages deploy: commit, push to main; repository Settings -> Pages -> Source: GitHub Actions
# python sanity (unchanged generator)
python -m unittest discover -s generator/tests
```

## Critical review

Independent reviewer results: Python 413 OK (156 s) and the production validator OK (on a copy with a PRELIMINARY record
it exits 1); static review of loader, filter, storage, timer, CSS and workflow; generator unchanged by mtime. Findings:
(1) medium: `--out` could wipe `data/production`, generator, docs or scripts; (2) `reconcileStorage` deleted saves of unknown IDs;
(3) the whole store was re-parsed on every tap; (4) multi-puzzle replay reset a random puzzle without warning; (5) pause button was
44x36; (6) the derived dist JSON was undocumented/unmarked; (7) Puzzle Details opened from the completion screen did not return to it.
All seven were fixed in a remediation pass (allow-listed output dir + tests; unknown saves kept, 90-day expiry; store cache and
100-frame history; explicit reset warning; 44x44 pause with negative margin, page heights unchanged; `derived: true` + docs;
completion screen restored on close) and the full suite was re-run. Reviewer limits: no node or Playwright, so unit/browser tests were
not re-run by the reviewer (those results rest on the coder's runs); a real iPhone/iPad and a real Pages deploy were not checked.
