"""Run real-browser regression checks; requires the optional Playwright Python package.

    python -m pip install playwright
    python -m playwright install chromium webkit
    python web/tests/browser_regression.py

The test server is local, starts on a free port, and shuts down after the run.
No project dependencies, production JSON, or installed browser profiles are changed.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "web" / "artifacts"
PRODUCTION_PATH = ROOT / "data" / "production" / "puzzles.json"
REAL_ID = "puzzle-8e2b144cecb50551d96b"
APP_VERSION = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))["version"]
# Compact multi-puzzle fixture (slim copies of certified records) for the multi-puzzle E2E; never production input.
MULTI = json.loads((ROOT / "web" / "tests" / "fixtures" / "production_multi.json").read_text(encoding="utf-8"))
STORE = "extreme-sudoku.progress.v2"
# Matches the dev URL and the built URL with its content-hash query (?v=...).
DB_ROUTE = re.compile(r".*/data/production/puzzles\.json(\?.*)?$")
PREFIX = "/extreme-sudoku"
DIST = ROOT / "dist"
PRODUCTION = REAL = None


def use_production(path):
    """Load the production database the dev page will be served (data/production by default)."""
    global PRODUCTION_PATH, PRODUCTION, REAL
    PRODUCTION_PATH = Path(path)
    PRODUCTION = json.loads(PRODUCTION_PATH.read_text(encoding="utf-8-sig"))
    # Looked up by ID: with several puzzles the export order may change.
    REAL = next(p for p in PRODUCTION["puzzles"] if p["id"] == REAL_ID)


use_production(PRODUCTION_PATH)


def production_payload(*puzzles):
    return {**{k: v for k, v in PRODUCTION.items() if k != "puzzles"}, "puzzles": list(puzzles)}


def pin_real():
    """Init script: on a fresh profile, make the original puzzle the active (unstarted) game so flows that need
    its cells work with any number of production puzzles. Never overwrites existing storage."""
    store = {"storageSchemaVersion": 2, "activePuzzleId": REAL["id"], "games": {REAL["id"]: saved_snapshot_template(elapsed_ms=0)}}
    return f"try{{if(!localStorage.getItem('{STORE}'))localStorage.setItem('{STORE}', {json.dumps(json.dumps(store))});}}catch(e){{}}"


def single_database(context, puzzle=None):
    """Serve a one-record production database: for checks of the single-puzzle New Game wording."""
    body = json.dumps(production_payload(puzzle or REAL))
    context.route(DB_ROUTE, lambda route: route.fulfill(content_type='application/json', body=body))


def seed(state, settings=None):
    """Init script storing `state` as the active saved game once (reloads keep live progress)."""
    store = {"storageSchemaVersion": 2, "activePuzzleId": state["puzzleId"], "games": {state["puzzleId"]: state}}
    extra = f"localStorage.setItem('extreme-sudoku.settings.v1', {json.dumps(json.dumps(settings))});" if settings else ""
    return ("if(!localStorage.getItem('__seeded')){localStorage.setItem('__seeded','1');"
            f"localStorage.setItem('{STORE}', {json.dumps(json.dumps(store))});{extra}}}")
TARGETS = [
    ("iphone-portrait", 390, 844),
    ("iphone-landscape", 844, 390),
    ("ipad-portrait", 810, 1080),
    ("ipad-landscape", 1080, 810),
    ("small-phone", 375, 667),
    ("large-phone", 430, 932),
    ("laptop", 1366, 768),
    ("desktop", 1920, 1080),
    ("narrow-phone", 320, 568),
    ("safari-bars-proxy", 390, 700),
    ("moderate-landscape", 844, 650),
    ("small-tablet-landscape", 740, 620),
    ("wide-tablet-landscape", 900, 700),
    ("breakpoint-landscape", 959, 750),
]


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # /extreme-sudoku/web/... emulates a Pages prefix over the repository (dev layout);
        # /repo-name/... serves the built dist/ folder exactly as GitHub Pages would.
        if path.startswith("/repo-name/"):
            return str(DIST / path[len("/repo-name/"):].split("?")[0]) if DIST.exists() else str(ROOT / "__missing__")
        if path.startswith("/extreme-sudoku/"):
            path = path[len("/extreme-sudoku"):]
        if path.split("?")[0] == "/data/production/puzzles.json":
            return str(PRODUCTION_PATH)
        return super().translate_path(path)

    def log_message(self, format, *args):
        pass


@contextmanager
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(ROOT)))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def bounds(page, selector):
    return page.locator(selector).first.bounding_box()


def saved(page):
    return page.evaluate("(() => { const s = JSON.parse(localStorage.getItem('" + STORE + "')); return s && s.games[s.activePuzzleId]; })()")


def visual_metrics(page):
    return page.evaluate("""() => {
        const rect = element => {
            const {x, y, width, height, right, bottom} = element.getBoundingClientRect();
            return {x, y, width, height, right, bottom};
        };
        const board = document.querySelector('#board');
        const cell = board.querySelector('[data-index]');
        const note = board.querySelector('.pencil-grid span');
        const controls = [...document.querySelectorAll('#number-pad button, .actions button')];
        const selectedNote = board.querySelector('.selected .pencil-grid');
        const luminance = color => {
            const rgb = color.match(/[\\d.]+/g).slice(0, 3).map(x => Number(x) / 255).map(x => x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4);
            return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
        };
        let noteContrast = null;
        if (selectedNote) {
            const a = luminance(getComputedStyle(selectedNote).color), b = luminance(getComputedStyle(selectedNote.closest('.cell')).backgroundColor);
            noteContrast = (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
        }
        return {
            viewport: {width: innerWidth, height: innerHeight},
            document: {width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight},
            board: rect(board), cell: rect(cell), badge: rect(document.querySelector('#cert-badge')), pause: rect(document.querySelector('#pause-button')), meta: rect(document.querySelector('.puzzle-meta')), time: rect(document.querySelector('.time-group')),
            noteFont: note ? getComputedStyle(note).fontSize : null,
            cellFont: getComputedStyle(cell).fontSize,
            selectedNoteContrast: noteContrast,
            controls: controls.map(el => ({label: el.getAttribute('aria-label') || el.textContent.trim(), ...rect(el)})),
            boardUserSelect: getComputedStyle(board).userSelect,
            boardTouchAction: getComputedStyle(board).touchAction,
        };
    }""")


def assert_layout(metrics, label):
    viewport, board = metrics['viewport'], metrics['board']
    check(metrics['document']['width'] <= viewport['width'], f'{label}: horizontal overflow')
    check(abs(board['width'] - board['height']) < 1, f'{label}: board not square')
    check(board['x'] >= -1 and board['right'] <= viewport['width'] + 1, f'{label}: board clipped horizontally')
    check(board['y'] >= -1 and board['bottom'] <= viewport['height'] + 1, f'{label}: board below fold')
    badge, meta, time = metrics['badge'], metrics['meta'], metrics['time']
    check(badge['x'] >= -1 and badge['right'] <= viewport['width'] + 1 and badge['height'] >= 43.9, f'{label}: badge clipped or small {badge}')
    check(meta['right'] <= time['x'] + 1 and badge['right'] <= meta['right'] + 1, f'{label}: badge/info overlaps timer')
    check(not (min(badge['right'], board['right']) - max(badge['x'], board['x']) > 1 and min(badge['bottom'], board['bottom']) - max(badge['y'], board['y']) > 1), f'{label}: badge overlaps board')
    check(metrics['pause']['width'] >= 43.9 and metrics['pause']['height'] >= 43.9, f'{label}: pause button too small {metrics["pause"]}')
    check(len(metrics['controls']) >= 12, f'{label}: missing controls')
    for control in metrics['controls']:
        check(control['width'] >= 43.9 and control['height'] >= 43.9, f'{label}: small control {control}')
        check(control['x'] >= -1 and control['right'] <= viewport['width'] + 1, f'{label}: clipped control {control}')
        if viewport['width'] >= 375:
            check(control['bottom'] <= viewport['height'] + 1, f'{label}: primary control below fold {control}')
        overlap = min(board['right'], control['right']) - max(board['x'], control['x']) > 1 and min(board['bottom'], control['bottom']) - max(board['y'], control['y']) > 1
        check(not overlap, f'{label}: board/control overlap')
    check(float(metrics['noteFont'].replace('px', '')) >= 10, f'{label}: tiny notes')
    check(metrics['selectedNoteContrast'] >= 4.5, f'{label}: low selected-note contrast')


def enter_game(page, resume=True):
    """Traverse the real profile/home flow; never bypass the writer lock."""
    page.locator('#home').wait_for()
    if page.locator('#profile-form').count():
        page.locator('#player-name').fill('Regression player')
        page.locator('#player-preparation').select_option('expert')
        page.locator('#save-profile').click()
        page.locator('#home-new').wait_for()
    active = page.evaluate("JSON.parse(localStorage.getItem('" + STORE + "') || '{}').activePuzzleId")
    button = page.locator(f'[data-continue="{active}"]') if active else page.locator('[data-continue]').first
    if button.count() and button.is_enabled():
        button.click()
    elif page.locator('[data-continue]:enabled').count():
        page.locator('[data-continue]:enabled').first.click()
    else:
        page.locator('#home-new').click()
        page.locator('[data-difficulty]').first.click()
        page.locator('#start-game').click()
    if resume and page.locator('#resume-button').is_visible():
        page.locator('#resume-button').click()
    page.locator('#board [data-index]').nth(80).wait_for(state='attached')


def load(page, url):
    page.goto(url)
    enter_game(page)


def dense_notes(page):
    # Use the public saved-game format to create a deterministic visual stress state.
    # Production puzzle data stays untouched, and input behavior is checked separately.
    state = saved(page)
    count = 0
    for index, digit in enumerate(state['values']):
        if not digit:
            state['notes'][index] = list(range(1, 7 + count % 4))
            count += 1
    state['notesMode'] = True
    page.add_init_script(seed(state))
    page.evaluate("localStorage.removeItem('__seeded')")
    page.reload()
    enter_game(page)


def run_browser(browser, origin, engine, results):
    context = browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True, device_scale_factor=2)
    context.add_init_script(pin_real())
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    load(page, origin + '/web/')
    functional_checks(page, origin, results, engine)
    context.close()
    # Profile/home, active timing and permanent non-repeat replace the Phase 10
    # auto-start / wall-clock / replay scenarios.
    from browser_player import run_player_checks
    import sys
    run_player_checks(browser, origin, engine, results, sys.modules[__name__])

    for theme in ('light', 'dark'):
        context = browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True, device_scale_factor=2, color_scheme=theme)
        context.add_init_script(pin_real())
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        load(page, origin + '/web/')
        dense_notes(page)
        for target, width, height in TARGETS:
            page.set_viewport_size({'width': width, 'height': height})
            page.wait_for_timeout(100)
            metrics = visual_metrics(page)
            label = f'{engine}-{target}-{theme}'
            assert_layout(metrics, label)
            metrics.update({'browser': engine, 'target': target, 'theme': theme})
            results['layouts'].append(metrics)
            page.screenshot(path=str(ARTIFACTS / f'{label}.png'), full_page=True, scale='css')
        context.close()
    check(not errors, f'{engine}: unexpected JS errors {errors}')
    results['checks'].append({'browser': engine, 'test': f'responsive-light-dark-{len(TARGETS) * 2}-layouts', 'status': 'passed'})


def modal_fits(page):
    box = bounds(page, '#sheet')
    close = bounds(page, '#close-sheet')
    viewport = page.viewport_size
    check(box['x'] >= 0 and box['x'] + box['width'] <= viewport['width'] + 1, 'modal clipped horizontally')
    check(box['y'] >= 0 and box['y'] + box['height'] <= viewport['height'] + 1, 'modal clipped vertically')
    check(close['y'] >= 0 and close['y'] + close['height'] <= viewport['height'] + 1, 'modal close unreachable')




def functional_checks(page, origin, results, engine):
    puzzle = REAL
    check(saved(page)['puzzleId'] == REAL['id'], 'app did not load the production puzzle')
    empty = [i for i, digit in enumerate(puzzle['puzzle']) if digit == '0']
    given = next(i for i, digit in enumerate(puzzle['puzzle']) if digit != '0')
    cell = lambda index: page.locator(f'.cell[data-index="{index}"]')
    digit = lambda value: page.locator(f'.number-button[data-digit="{value}"]')
    index = empty[0]
    cell(given).tap()
    digit(1).tap()
    page.locator('#erase-button').click(force=True)
    check(saved(page)['values'][given] == int(puzzle['puzzle'][given]), 'given changed')
    cell(index).tap()
    page.locator('#notes-button').tap()
    check(page.locator('#notes-button').get_attribute('aria-pressed') == 'true', 'notes toggle unclear')
    for value in range(1, 10):
        digit(value).tap()
    check(saved(page)['notes'][index] == list(range(1, 10)), 'nine notes not entered')
    check(cell(index).locator('.pencil-grid span').count() == 9, 'notes do not have nine fixed positions')
    page.locator('#erase-button').tap()
    check(saved(page)['notes'][index] == [], 'erase notes failed')
    page.locator('#undo-button').tap()
    check(saved(page)['notes'][index] == list(range(1, 10)), 'undo notes failed')

    before = saved(page)
    page.set_viewport_size({'width': 844, 'height': 390})
    page.set_viewport_size({'width': 390, 'height': 844})
    page.reload()
    enter_game(page)
    after = saved(page)
    for key in ('puzzleId', 'values', 'notes', 'selectedCell', 'notesMode', 'mistakes', 'hintsUsed'):
        check(before[key] == after[key], f'rotation/reload lost {key}')
    check(after['elapsedMs'] >= before['elapsedMs'], 'elapsed time went backwards')

    # Final input removes the same note from peers and undo restores all affected cells.
    peer = next(i for i in empty if i != index and (i // 9 == index // 9 or i % 9 == index % 9 or (i // 27, i % 9 // 3) == (index // 27, index % 9 // 3)))
    value = int(puzzle['solution'][peer])
    cell(peer).tap()
    page.keyboard.press('n')
    page.keyboard.press(str(value))
    check(saved(page)['values'][peer] == value and value not in saved(page)['notes'][index], 'peer auto-remove failed')
    page.keyboard.press('Control+z')
    check(saved(page)['values'][peer] == 0 and saved(page)['notes'][index] == list(range(1, 10)), 'atomic undo failed')
    cell(index).tap()
    page.keyboard.press('ArrowRight')
    check(saved(page)['selectedCell'] == index + 1, 'arrow navigation failed')
    check(page.locator('#board input, #board textarea, #board [contenteditable=true]').count() == 0, 'cell can open software keyboard')

    page.locator('#pause-button').tap()
    check(saved(page)['status'] == 'paused', 'pause failed')
    paused = saved(page)['elapsedMs']
    page.wait_for_timeout(1100)
    page.reload()
    enter_game(page, resume=False)
    check(saved(page)['status'] == 'paused' and saved(page)['elapsedMs'] == paused, 'paused timer advanced across reload')
    page.locator('#resume-button').tap()
    check(saved(page)['status'] == 'playing', 'resume failed')
    results['checks'].append({'browser': engine, 'test': 'touch-keyboard-notes-undo-givens-rotation-reload-pause', 'status': 'passed'})

    # A project Pages prefix must preserve asset and database paths on a fresh load.
    load(page, origin + '/extreme-sudoku/web/')
    check(page.locator('.cell').count() == 81, 'project-prefix data/asset loading failed')
    results['checks'].append({'browser': engine, 'test': 'github-pages-project-prefix', 'status': 'passed'})


CORRECT_PATH_MESSAGES = {
    'load': 'Не удалось загрузить базу Sudoku. Попробуйте обновить страницу.',
    'empty': 'Сейчас нет доступных проверенных Sudoku.',
}












def saved_snapshot_template(elapsed_ms=1000, puzzle=None):
    puzzle = puzzle or REAL
    return {'version': 1, 'puzzleId': puzzle['id'], 'puzzleFingerprint': puzzle['puzzle'], 'values': [int(d) for d in puzzle['puzzle']],
            'notes': [[] for _ in range(81)], 'selectedCell': puzzle['puzzle'].index('0') if elapsed_ms == 0 else 0, 'notesMode': False,
            'elapsedMs': elapsed_ms, 'status': 'playing', 'mistakes': 0, 'hintsUsed': 0, 'history': []}


def build_dist():
    """Build dist/ with the project's own script (node from PATH, else Playwright's bundled node)."""
    import shutil, subprocess
    node = shutil.which('node')
    if not node:
        from playwright._impl._driver import compute_driver_executable
        node = str(compute_driver_executable()[0])
    subprocess.run([node, str(ROOT / 'scripts' / 'build_pages.mjs')], check=True, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", choices=("all", "chromium", "webkit", "firefox"), default="all")
    parser.add_argument("--artifacts", type=Path, help="write screenshots/results here instead of web/artifacts")
    parser.add_argument("--production-db", type=Path, help="serve this production database to the dev page instead of "
                        "data/production/puzzles.json (e.g. a merge rehearsal); dist/ is still built from data/production")
    args = parser.parse_args()
    global ARTIFACTS
    if args.artifacts:
        ARTIFACTS = args.artifacts.resolve()
    if args.production_db:
        use_production(args.production_db.resolve())
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    build_dist()
    results = {"browsers": [], "checks": [], "layouts": []}
    with server() as origin, sync_playwright() as playwright:
        for name in ("chromium", "webkit", "firefox"):
            if args.browser not in ("all", name):
                continue
            browser = getattr(playwright, name).launch()
            print(f'Running {name}', flush=True)
            results["browsers"].append({"engine": name, "version": browser.version})
            try:
                if name == 'firefox':
                    from browser_player import run_player_checks
                    import sys
                    run_player_checks(browser, origin, name, results, sys.modules[__name__])
                else:
                    run_browser(browser, origin, name, results)
            finally:
                browser.close()
    (ARTIFACTS / "browser-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
