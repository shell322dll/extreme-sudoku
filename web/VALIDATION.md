> **Current strategy-help verification (2026-10-09).** All 77 Node tests passed, including 14 independent checks of the lesson deductions and four renderer tests. The Pages build includes all 58 unchanged puzzles and the new modules. Chromium passed 174 lesson/layout checks across 320, 390 and 1280 pixels in both themes. Focused Chromium, Firefox 155 and WebKit 26.6 checks passed for SVG, zoom, keyboard focus, pre-profile access and returning to a paused game; 844 × 390 landscape also passed. Reading help preserves entries, notes, reveal counts and statistics. No external assets or JavaScript errors were observed. Physical Safari, Chrome and Edge were not available; managed engines were tested.
>
> Reproduce after `node scripts/build_pages.mjs` with `python web/tests/browser_strategy_help.py --engine chromium --matrix`. The optional Playwright Python package and corresponding browser are required. Use `--engine webkit` or `--engine firefox` for a focused run, `--base-url` for an existing site and `--artifacts` to choose the report directory. [Compact strategy-help report](../reports/phase13/strategy-help-validation.json).
>
> **Historical measurements below.** Earlier profile/active-time changes are covered by `tests/player.test.js`, updated game/selection tests and the broader browser regression suite. Historical screenshots and numbers below are not fresh validation of this strategy-help release.

# Frontend validation

The frontend directory was empty before this implementation. The delivered app uses
static HTML, CSS and ES modules; generator code and the production puzzle database
were not changed. There is no build step or runtime Python dependency.

## Final result

The completed run passed **15/15 unit tests, 14 browser scenario groups and
56 responsive cases** (14 viewports × 2 themes × 2 engines), with no unexpected
JavaScript errors in the main game and layout scenarios. Browser results were
written on 2026-09-28 at 21:33 local time, after the final app, CSS and test fixes.
Complete measurements: [browser-results.json](artifacts/browser-results.json).
There are 64 screenshots: 56 layout images and 8 synthetic long-label images.

Local preview: <http://127.0.0.1:8765/web/>. The server serves this repository only
and listens on loopback, so the URL is available on this computer.

## Measured layout

All dimensions below are CSS pixels. Geometry is the same in Chromium and WebKit
and in light/dark themes; rounding is to two decimals. Cell size is the actual
first cell including its border. Control dimensions give the minimum width and
height among number-pad and four primary action buttons. Horizontal overflow was
zero in every case.

| Viewport | Board | Cell | Note font | Minimum control W × H | Primary controls bottom | Layout |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 390 × 844 | 370 | 40.66 | 11.7 | 67.59 × 52 | 696 | Board above 5+4 keypad |
| 844 × 390 | 318 | 34.88 | 10 | 70 × 45 | 315 | Board left, 5+4 keypad right |
| 810 × 1080 | 600 | 66.22 | 17 | 59.55 × 52 | 912 | Centered board, one-row keypad below |
| 1080 × 810 | 600 | 66.22 | 17 | 81.25 × 59 | 570.89 | Board left, 3×3 keypad right |
| 375 × 667 | 355 | 39 | 11.25 | 64.59 × 46 | 638 | Compact portrait |
| 430 × 932 | 410 | 45.11 | 12.9 | 75.59 × 52 | 736 | Portrait |
| 1366 × 768 | 600 | 66.22 | 17 | 81.25 × 59 | 570.89 | Two columns |
| 1920 × 1080 | 600 | 66.22 | 17 | 81.25 × 59 | 570.89 | Two columns, capped board |
| 320 × 568 | 300 | 32.88 | 11 | 53.59 × 46 | 583 | Narrow portrait; small vertical scroll |
| 390 × 700 | 370 | 40.66 | 11.7 | 67.59 × 46 | 653 | Reduced-height portrait |
| 844 × 650 | 514 | 56.66 | 14.35 | 46.8 × 52 | 424 | Intermediate landscape, two columns |
| 740 × 620 | 410 | 45.11 | 12.58 | 51.59 × 52 | 372 | Intermediate landscape, two columns |
| 900 × 700 | 516 | 56.88 | 15 | 46.39 × 52 | 425 | Intermediate landscape, capped board |
| 959 × 750 | 516 | 56.88 | 15 | 46.39 × 52 | 425 | Breakpoint regression |

All eight requested viewports keep the board, number pad and primary actions in
view. At 375 × 667 only bottom spacing adds 9 px of document scroll; at
1366 × 768 it adds 5 px. At 320 × 568 the document is 621 px high and actions end
15 px below the initial viewport; this preserves readable notes and touch targets.
Selected-note contrast is **5.46:1 light / 4.79:1 dark**.

Representative WebKit evidence (matching Chromium images are also saved):

- [iPhone portrait light](artifacts/webkit-iphone-portrait-light.png) /
  [dark](artifacts/webkit-iphone-portrait-dark.png).
- [iPhone landscape light](artifacts/webkit-iphone-landscape-light.png) /
  [dark](artifacts/webkit-iphone-landscape-dark.png).
- [iPad portrait light](artifacts/webkit-ipad-portrait-light.png) /
  [dark](artifacts/webkit-ipad-portrait-dark.png).
- [iPad landscape light](artifacts/webkit-ipad-landscape-light.png) /
  [dark](artifacts/webkit-ipad-landscape-dark.png).

## Implementation and issues resolved

The compact header and metadata leave the board as the main element. Undo, Erase,
Notes and Hint stay beside the keypad, outside menus. Notes has both a visible
pressed background and the label `Notes on`. New puzzle, Restart, Settings,
Details and Help live in the menu; wide layouts also expose New puzzle.

The viewport meta includes `viewport-fit=cover` and permits zoom. App padding
uses all four `env(safe-area-inset-*)` values. `100svh` supplements the `100vh`
fallback for stable page/landscape sizing, while modal height uses `100dvh` and
safe-area deductions. Portrait keeps a wide board and compacts spacing/controls
when height is limited. Phone landscape caps board size by available height.

Review and browser testing found and corrected:

- Selected-note contrast in both palettes; notes now exceed 4.5:1.
- Optional malformed rating/technique metadata could break Details; the display
  now checks types and ignores invalid optional values.
- The intermediate 844 × 650 range retained a portrait stack, placing the keypad
  below the viewport. A two-column range and 516 px board cap preserve at least
  44 px controls up to the 960 px breakpoint.
- WebKit touch did not focus the menu opener automatically, so closing a nested
  dialog could lose focus. Explicit opener tracking now returns it correctly.
- Browser picker tests now derive available difficulties from the collection,
  allowing the independent generator to add Extreme puzzles without false failures.

## Files delivered

- `web/index.html`: semantic page shell, game controls and modal.
- `web/styles.css`: mobile-first sizing, themes, notes, safe areas and breakpoints.
- `web/app.js`: DOM rendering, input, dialogs, settings and persistence wiring.
- `web/lib/game.js`: independent game state and rules.
- `web/lib/data.js`: database contract validation and loading.
- `web/lib/storage.js`: guarded local saves, settings and recent puzzles.
- `web/package.json`: ES module declaration and unit-test command.
- `web/tests/game.test.js`: 15 game/data/storage unit tests.
- `web/tests/browser_regression.py`: browser interaction and visual regression suite.
- `web/README.md`, `web/VALIDATION.md`: usage, static hosting and this report.
- `web/artifacts/browser-results.json` and `web/artifacts/*.png`: measured evidence.

## Reproduce

From `web/`, run unit tests with Node 20 or newer:

```console
npm test
```

The browser suite starts its own temporary local HTTP server and shuts it down.
The optional Python Playwright dependency is test tooling only:

```console
python -m pip install playwright
python -m playwright install chromium webkit
python web/tests/browser_regression.py
```

Run that command from the repository root. `--browser chromium` and
`--browser webkit` can select one engine. Screenshots and measured layout data are
written to `web/artifacts/`. The test suite does not change `data/puzzles.json`.

The execution environment used Python 3.11.9, Playwright 1.63.0,
Chromium 153.0.8010.12 and WebKit 26.6. Node 24.21.0 was supplied by the isolated
Playwright installation because Node/npm were not installed on PATH. Test tooling
and browser downloads were placed in the OS temporary folder, without modifying
other projects or virtual environments.

Exact commands used in this Windows session (PowerShell, repository root):

```powershell
$env:PYTHONPATH = Join-Path $env:TEMP 'extreme-sudoku-qa\packages'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $env:TEMP 'extreme-sudoku-qa\browsers'
python web/tests/browser_regression.py
& "$env:TEMP\extreme-sudoku-qa\packages\playwright\driver\node.exe" --test web/tests/game.test.js
```

The retained local preview uses `python -m http.server 8765 --bind 127.0.0.1`
from the repository root. Both `/web/` and `/data/puzzles.json` returned HTTP 200.

## Coverage

- Actual touch and keyboard entry; immutable clues; nine note positions; note
  erasure; atomic undo including automatically removed peer notes.
- Rotation and reload preserve values, notes, selection, mode, counters and timer.
- Pause/resume and paused reload; saved settings, theme and error mode.
- Correct and incorrect complete grids in all three error modes.
- Hint and restart confirmation/cancellation; new puzzle selection and unavailable
  difficulty choices; modal bounds and keyboard focus restoration.
- Blocked storage, corrupt saves, failed fetch plus retry, mixed valid/invalid
  database records, malformed optional metadata.
- Relative assets and JSON under both `/web/` and `/extreme-sudoku/web/`.
- Every measured viewport in both themes and both engines; square board,
  no horizontal overflow, primary controls at least 44 CSS px, no board/control
  overlap, note readability and selected-note contrast.
- Synthetic browser-only stress fixtures with `Ultra Extreme`, a one-hour timer
  and dense notes. These fixtures test longer text and do not relabel real puzzles.

## Visual review and limitations

Screenshots show real rendered puzzle data, with 7–9 notes added to empty cells
through an isolated saved-game fixture. Main-target light and dark screenshots
were visually inspected for border clarity, candidate separation, highlighting,
clipping and control placement.

WebKit on Windows is a Safari-like engine check, not a physical iPhone/iPad Safari
test. The 390 × 700 case approximates reduced space from browser controls; it does
not reproduce iOS browser-toolbar animations. `env(safe-area-inset-*)` values are
zero in these desktop browser runs. Actual notch, home indicator, OLED appearance,
pinch zoom and on-device touch/long-press behavior need a physical-device check.
Cells are buttons rather than text inputs, so gameplay has no editable element
that requests the software keyboard. No claim is made that a real iOS keyboard
was observed during this desktop test.

The current collection has eight Easy, Medium and Expert puzzles. Extreme and
Ultra Extreme remain unavailable until the independent generator supplies them.
Hints explicitly reveal one correct cell and do not claim to explain a technique.

Static publishing is ready when the host exposes `web/` beside `data/` (see
`README.md`). Project-prefix URL loading was tested locally; no public deployment
or HTTPS production URL was created during this task.
