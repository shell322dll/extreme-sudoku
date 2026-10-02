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
import threading

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "web" / "artifacts"
PRODUCTION = json.loads((ROOT / "data" / "production" / "puzzles.json").read_text(encoding="utf-8-sig"))
REAL = PRODUCTION["puzzles"][0]
STORE = "extreme-sudoku.progress.v2"
DB_ROUTE = "**/data/production/puzzles.json"
PREFIX = "/extreme-sudoku"
DIST = ROOT / "dist"


def production_payload(*puzzles):
    return {**{k: v for k, v in PRODUCTION.items() if k != "puzzles"}, "puzzles": list(puzzles)}


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


def load(page, url):
    page.goto(url)
    page.locator('#board [data-index]').nth(80).wait_for()


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
    page.locator('#board [data-index]').nth(80).wait_for()


def run_browser(browser, origin, engine, results):
    context = browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True, device_scale_factor=2)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    load(page, origin + '/web/')
    functional_checks(page, origin, results, engine)
    context.close()
    extended_checks(browser, origin, engine, results)
    production_checks(browser, origin, engine, results)

    for theme in ('light', 'dark'):
        context = browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True, device_scale_factor=2, color_scheme=theme)
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


def extended_checks(browser, origin, engine, results):
    chosen_difficulty = REAL['difficulty']
    context = browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True)
    page = context.new_page()
    load(page, origin + '/web/')
    page.locator('#menu-button').tap()
    page.locator('[data-menu="settings"]').tap()
    modal_fits(page)
    page.locator('[data-theme-choice="dark"]').tap()
    page.locator('[data-error-mode="off"]').tap()
    page.locator('#auto-notes').tap()
    check(page.locator('html').get_attribute('data-theme') == 'dark', 'dark theme not applied')
    page.locator('#close-sheet').tap()
    page.wait_for_function("document.activeElement.id === 'menu-button'")
    page.reload()
    page.locator('#menu-button').wait_for()
    check(page.locator('html').get_attribute('data-theme') == 'dark', 'theme lost after reload')
    settings = page.evaluate("JSON.parse(localStorage.getItem('extreme-sudoku.settings.v1'))")
    check(settings == {'theme': 'dark', 'errorMode': 'off', 'autoRemoveNotes': False}, 'settings not persisted')
    for target, width, height in TARGETS[:4] + [TARGETS[8]]:
        page.set_viewport_size({'width': width, 'height': height})
        for menu in ('new', 'settings', 'details', 'help'):
            page.locator('#menu-button').tap()
            page.locator(f'[data-menu="{menu}"]').tap()
            modal_fits(page)
            if menu == 'new':
                check(page.locator('#all-played-message').inner_text() == 'Все доступные Certified Sudoku уже сыграны. Можно решить эту задачу ещё раз.', 'single-puzzle message')
                check(page.locator('[data-difficulty]').count() == 0, 'single puzzle must not offer a difficulty picker')
            page.locator('#close-sheet').tap()
    page.set_viewport_size({'width': 390, 'height': 844})
    before = saved(page)
    page.locator('#hint-button').tap()
    modal_fits(page)
    page.locator('#cancel-hint').tap()
    check(saved(page)['hintsUsed'] == before['hintsUsed'], 'hint counted before confirmation')
    page.locator('#hint-button').tap()
    page.locator('#confirm-hint').tap()
    check(saved(page)['hintsUsed'] == before['hintsUsed'] + 1, 'confirmed hint not counted')
    page.locator('#menu-button').tap()
    page.locator('[data-menu="restart"]').tap()
    page.locator('#cancel-restart').tap()
    check(saved(page)['hintsUsed'] == 1, 'cancel restart reset state')
    page.locator('#menu-button').tap()
    page.locator('[data-menu="restart"]').tap()
    page.locator('#confirm-restart').tap()
    check(saved(page)['hintsUsed'] == 0 and not any(saved(page)['notes']), 'restart did not clear state')
    page.locator('#menu-button').tap()
    page.locator('[data-menu="new"]').tap()
    page.locator('#replay-puzzle').tap()
    check(page.locator('#difficulty').inner_text() == chosen_difficulty, 'replay kept a different puzzle')
    check(saved(page)['puzzleId'] == REAL['id'] and saved(page)['hintsUsed'] == 0, 'replay did not start fresh')
    base = saved(page)
    context.close()
    results['checks'].append({'browser': engine, 'test': 'settings-themes-modals-focus-hint-restart-newgame', 'status': 'passed'})

    puzzle = REAL
    editable = [i for i, digit in enumerate(puzzle['puzzle']) if digit == '0']
    for mode in ('immediate', 'completion', 'off'):
        state = dict(base)
        state['values'] = list(map(int, puzzle['solution']))
        wrong, last = editable[:2]
        state['values'][wrong] = int(puzzle['solution'][wrong]) % 9 + 1
        state['values'][last] = 0
        state['selectedCell'] = last
        state['notesMode'] = False
        context = browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True)
        context.add_init_script(seed(state, {'errorMode': mode}))
        page = context.new_page()
        load(page, origin + '/web/')
        page.locator(f'.number-button[data-digit="{puzzle["solution"][last]}"]').tap()
        check(saved(page)['status'] == 'playing', f'{mode}: incorrect full board completed')
        check(page.locator('.cell.error').count() == (0 if mode == 'off' else 1), f'{mode}: incorrect errors display')
        page.locator(f'.cell[data-index="{wrong}"]').tap()
        page.locator(f'.number-button[data-digit="{puzzle["solution"][wrong]}"]').tap()
        check(saved(page)['status'] == 'completed', f'{mode}: correct board not completed')
        check(page.locator('#sheet').is_visible(), f'{mode}: missing completion dialog')
        modal_fits(page)
        context.close()
    results['checks'].append({'browser': engine, 'test': 'valid-invalid-completion-all-three-error-modes', 'status': 'passed'})

    # Isolated failure contexts must retain a usable page instead of throwing.
    context = browser.new_context()
    context.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new DOMException('Blocked', 'SecurityError')}})")
    page = context.new_page()
    load(page, origin + '/web/')
    check(page.locator('#save-status').inner_text() == 'Progress cannot be saved', 'blocked-storage fallback missing')
    page.locator('.number-button').first.click()
    context.close()
    context = browser.new_context()
    context.add_init_script("localStorage.setItem('" + STORE + "', '{broken');localStorage.setItem('extreme-sudoku.game.v1', '{also broken');localStorage.setItem('extreme-sudoku.settings.v1', 'null')")
    page = context.new_page()
    load(page, origin + '/web/')
    check(saved(page)['status'] == 'playing', 'corrupt save prevented fresh game')
    context.close()
    for payload in (None, production_payload({'id': 'broken'}, puzzle)):
        context = browser.new_context()
        page = context.new_page()
        if payload is None:
            page.route(DB_ROUTE, lambda route: route.fulfill(status=503, body='Unavailable'))
            page.goto(origin + '/web/')
            page.locator('#retry-loading').wait_for()
            check(page.locator('.load-message').inner_text() == 'Не удалось загрузить базу Sudoku. Попробуйте обновить страницу.', 'load error text')
            check(not page.locator('#game').is_visible(), 'game visible after load failure (silent mock fallback?)')
            page.unroute(DB_ROUTE)
            page.locator('#retry-loading').click()
            page.locator('#game').wait_for()
        else:
            page.route(DB_ROUTE, lambda route: route.fulfill(content_type='application/json', body=json.dumps(payload)))
            load(page, origin + '/web/')
            check(saved(page)['puzzleId'] == puzzle['id'], 'mixed malformed database lost valid entry')
        context.close()
    results['checks'].append({'browser': engine, 'test': 'blocked-corrupt-storage-network-retry-malformed-database', 'status': 'passed'})

    # Deliberately synthetic label/metadata fixture: never written to production data.
    stress_puzzle = dict(puzzle, difficulty='Ultra Extreme', rating='bad optional value', techniques=['unexpected'], difficultyData={'advancedSteps': {'bad': True}},
                         certification={**puzzle['certification'], 'status': 'CERTIFIED_ULTRA_EXTREME', 'genuineBottlenecks': 'bad'})
    stress_state = dict(base, values=list(map(int, puzzle['puzzle'])), elapsedMs=3723000, selectedCell=editable[0], notesMode=True)
    stress_state['notes'] = [list(range(1, 10)) if digit == '0' else [] for digit in puzzle['puzzle']]
    for theme in ('light', 'dark'):
        context = browser.new_context(viewport={'width': 320, 'height': 568}, color_scheme=theme)
        context.add_init_script(seed(stress_state))
        page = context.new_page()
        page.route(DB_ROUTE, lambda route: route.fulfill(content_type='application/json', body=json.dumps(production_payload(stress_puzzle))))
        load(page, origin + '/web/')
        for width in (320, 390):
            page.set_viewport_size({'width': width, 'height': 844 if width == 390 else 568})
            info = page.locator('.puzzle-meta').bounding_box()
            time = page.locator('.time-group').bounding_box()
            check(info['x'] + info['width'] <= time['x'], 'long difficulty/hour timer overlap')
            check(page.locator('#timer').inner_text().count(':') == 2, 'hour timer not displayed')
            check(page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'stress metadata overflow')
            page.screenshot(path=str(ARTIFACTS / f'{engine}-synthetic-long-label-{width}-{theme}.png'), full_page=True, scale='css')
        page.locator('#menu-button').click()
        page.locator('[data-menu="details"]').click()
        modal_fits(page)
        check('bad optional value' not in page.locator('#sheet-content').inner_text(), 'malformed rating rendered')
        context.close()
    results['checks'].append({'browser': engine, 'test': 'synthetic-long-label-hour-timer-dense-notes-malformed-metadata', 'status': 'passed'})


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
    page.locator('#board [data-index]').nth(80).wait_for()
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
    page.locator('#resume-button').wait_for()
    check(saved(page)['status'] == 'paused' and saved(page)['elapsedMs'] == paused, 'paused timer advanced across reload')
    page.locator('#resume-button').tap()
    check(saved(page)['status'] == 'playing', 'resume failed')
    results['checks'].append({'browser': engine, 'test': 'touch-keyboard-notes-undo-givens-rotation-reload-pause', 'status': 'passed'})

    # A project Pages prefix must preserve asset and database paths on a fresh load.
    prefix = page.context.new_page()
    load(prefix, origin + '/extreme-sudoku/web/')
    check(prefix.locator('.cell').count() == 81, 'project-prefix data/asset loading failed')
    prefix.close()
    results['checks'].append({'browser': engine, 'test': 'github-pages-project-prefix', 'status': 'passed'})


CORRECT_PATH_MESSAGES = {
    'load': 'Не удалось загрузить базу Sudoku. Попробуйте обновить страницу.',
    'empty': 'Сейчас нет доступных сертифицированных Sudoku.',
}


def phone(browser, **kwargs):
    return browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True, device_scale_factor=2, **kwargs)


def real_cells():
    empty = [i for i, d in enumerate(REAL['puzzle']) if d == '0']
    given = [i for i, d in enumerate(REAL['puzzle']) if d != '0']
    return empty, given


def production_checks(browser, origin, engine, results):
    empty, given = real_cells()
    solution = REAL['solution']
    cell = lambda page, i: page.locator(f'.cell[data-index="{i}"]')
    digit = lambda page, v: page.locator(f'.number-button[data-digit="{v}"]')

    # --- Production loading, certification display, Puzzle Details -----------------------------
    context = phone(browser)
    page = context.new_page()
    messages, requests = [], []
    page.on('console', lambda m: messages.append((m.type, m.text)))
    page.on('requestfinished', lambda r: requests.append(r.url))
    load(page, origin + '/web/')
    check(any(u.endswith('/data/production/puzzles.json') for u in requests), 'production JSON not requested')
    check(not any(u.endswith('/data/puzzles.json') for u in requests), 'legacy demo database was requested')
    check(saved(page)['puzzleId'] == 'puzzle-8e2b144cecb50551d96b', 'wrong puzzle loaded')
    check(' '.join(page.locator('#cert-badge').inner_text().split()) == 'Certified Extreme', 'badge text')
    check(page.locator('#clues').inner_text() == '22 clues', 'clue text')
    check([c for c in range(81) if cell(page, c).get_attribute('aria-readonly') == 'true'] == [i for i in range(81) if REAL['puzzle'][i] != '0'], 'givens not read-only')
    check('Row 1, column 1' in cell(page, 0).get_attribute('aria-label'), 'cell aria-label')
    page.locator('#cert-badge').tap()
    modal_fits(page)
    details = page.locator('#sheet-content').inner_text()
    for needle in ('puzzle-8e2b144cecb50551d96b', 'Extreme', 'Certified Extreme', '22', '35', 'Grouped AIC', 'Genuine bottlenecks', '3', 'Certification version', '0.1.0',
                   'Эта задача прошла проверку уникальности, логических доказательств и альтернативных путей в текущей версии системы Extreme Sudoku.', 'Naked Single'):
        check(needle in details, f'details missing {needle!r}')
    check('hardest in the world' not in details.lower(), 'marketing claim')
    page.screenshot(path=str(ARTIFACTS / f'{engine}-details-390.png'), scale='css')
    page.locator('#close-sheet').tap()
    check(page.locator('#sheet').is_hidden(), 'details did not close')
    check(not [m for m in messages if m[0] == 'error'], f'console errors {messages}')
    context.close()

    # --- Real-puzzle E2E: select, enter, notes, auto-remove, undo, erase, restart, reload resume --
    context = phone(browser)
    page = context.new_page()
    load(page, origin + '/web/')
    a, b = empty[0], next(i for i in empty if i != empty[0] and (i // 9 == empty[0] // 9 or i % 9 == empty[0] % 9))
    cell(page, a).tap()
    check(cell(page, a).get_attribute('aria-selected') == 'true' and 'selected' in cell(page, a).get_attribute('class'), 'selection')
    check(page.evaluate('document.activeElement && document.activeElement.tagName') != 'INPUT', 'tap focused an input')
    digit(page, solution[a]).tap()
    check(saved(page)['values'][a] == int(solution[a]), 'number entry')
    check(cell(page, a).inner_text() == solution[a], 'number rendering')
    page.locator('#notes-button').tap()
    check('Notes on' in page.locator('#notes-button').inner_text() and page.locator('#notes-button').get_attribute('aria-pressed') == 'true', 'notes state not textual')
    cell(page, b).tap()
    for v in (solution[a], '1', '9'):
        digit(page, v).tap()
    check(sorted(saved(page)['notes'][b]) == sorted({int(solution[a]), 1, 9}), 'notes entry')
    page.locator('#notes-button').tap()
    # entering a value in a peer removes that note from b; undo restores it
    peer_value = next(v for v in range(1, 10) if v in saved(page)['notes'][b])
    place = next(i for i in empty if i not in (a, b) and i // 9 == b // 9)
    page.locator('#undo-button').tap()
    undo_target = saved(page)
    cell(page, place).tap()
    digit(page, solution[place]).tap()
    check(saved(page)['values'][place] == int(solution[place]), 'second entry')
    with_notes = int(solution[place]) in undo_target['notes'][b]
    if with_notes:
        check(int(solution[place]) not in saved(page)['notes'][b], 'auto-remove notes')
    page.locator('#undo-button').tap()
    check(saved(page)['values'][place] == 0, 'undo value')
    check(saved(page)['notes'][b] == undo_target['notes'][b], 'undo did not restore removed note')
    cell(page, place).tap()
    digit(page, solution[place]).tap()
    page.locator('#erase-button').tap()
    check(saved(page)['values'][place] == 0, 'erase')
    cell(page, given[0]).tap()
    check(page.locator('#erase-button').is_disabled(), 'erase enabled on a given')
    # timer advances and survives reload
    page.wait_for_timeout(2100)
    t0 = saved(page)['elapsedMs']
    before = saved(page)
    page.reload()
    page.locator('#board [data-index]').nth(80).wait_for()
    after = saved(page)
    for key in ('values', 'notes', 'mistakes', 'hintsUsed', 'status', 'selectedCell'):
        check(before[key] == after[key], f'resume lost {key}')
    check(after['elapsedMs'] >= 2000 and after['elapsedMs'] >= t0, f'timer {t0} -> {after["elapsedMs"]}')
    check(page.locator('#timer').inner_text() != '00:00', 'timer display not restored')
    # backgrounding: wall-clock time keeps running while hidden / on pagehide, independent of the render loop
    page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange')); window.dispatchEvent(new Event('pagehide'))")
    hidden_at = saved(page)['elapsedMs']
    page.wait_for_timeout(1500)
    page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(300)
    resumed = saved(page)['elapsedMs']
    check(resumed - hidden_at >= 1400, f'hidden time not counted: {resumed - hidden_at}')
    # restart
    page.locator('#menu-button').tap()
    page.locator('[data-menu="restart"]').tap()
    page.locator('#confirm-restart').tap()
    check(not any(saved(page)['notes']) and saved(page)['values'] == [int(d) for d in REAL['puzzle']] and saved(page)['elapsedMs'] < 1500, 'restart')
    context.close()

    # --- Completion: only the exact solution completes; givens immutable ----------------------
    context = phone(browser)
    page = context.new_page()
    load(page, origin + '/web/')
    page.evaluate("localStorage.setItem('extreme-sudoku.settings.v1', JSON.stringify({errorMode: 'completion'}))")
    page.reload()
    page.locator('#board [data-index]').nth(80).wait_for()
    cell(page, given[0]).tap()
    digit(page, 9 if solution[given[0]] != '9' else 8).tap()
    check(saved(page)['values'][given[0]] == int(REAL['puzzle'][given[0]]), 'given changed')
    for i in empty[:-1]:
        cell(page, i).tap()
        digit(page, solution[i]).tap()
    check(saved(page)['status'] == 'playing' and page.locator('#sheet').is_hidden(), 'completed early')
    last = empty[-1]
    cell(page, last).tap()
    digit(page, int(solution[last]) % 9 + 1).tap()
    check(saved(page)['status'] == 'playing' and page.locator('#sheet').is_hidden(), 'wrong full board completed')
    digit(page, solution[last]).tap()
    page.locator('#sheet').wait_for(state='visible')
    check(saved(page)['status'] == 'completed', 'not completed')
    text = page.locator('#sheet').inner_text()
    for needle in ('Solved!', 'Certified Extreme', '22 clues', 'Time', 'Mistakes', 'Hints', 'Puzzle Details', 'Restart', 'Available Puzzles'):
        check(needle in text, f'completion missing {needle}')
    modal_fits(page)
    page.screenshot(path=str(ARTIFACTS / f'{engine}-completion-390.png'), scale='css')
    page.reload()
    page.locator('#sheet').wait_for(state='visible')
    check('Solved!' in page.locator('#sheet').inner_text(), 'completed state not restored')
    page.locator('#result-details').tap()
    check('Puzzle Details' in page.locator('#sheet-title').inner_text(), 'details from completion')
    page.locator('#close-sheet').tap()
    page.locator('#sheet-title').filter(has_text='Solved!').wait_for()
    check(page.locator('#sheet').is_visible(), 'closing details did not return to completion')
    page.locator('#result-new').tap()
    check(page.locator('#all-played-message').inner_text() == 'Все доступные Certified Sudoku уже сыграны. Можно решить эту задачу ещё раз.', 'single puzzle message after completion')
    page.locator('#replay-puzzle').tap()
    check(saved(page)['status'] == 'playing' and saved(page)['values'][last] == 0, 'replay after completion')
    context.close()
    results['checks'].append({'browser': engine, 'test': 'production-real-puzzle-e2e-completion-details-resume', 'status': 'passed'})

    # --- Wall-clock restore: a save made 30 s ago resumes with those 30 s added; pause stays frozen --
    for status, expect_added in (('playing', True), ('paused', False)):
        base = {**saved_snapshot_template(), 'puzzleId': REAL['id'], 'status': status, 'elapsedMs': 2000}
        context = phone(browser)
        context.add_init_script(seed({**base, 'savedAt': 0}))
        context.add_init_script("(() => { const k = '" + STORE + "'; if (window.__patched) return; window.__patched = true; const s = JSON.parse(localStorage.getItem(k)); if (s) { s.games['" + REAL['id'] + "'].savedAt = Date.now() - 30000; localStorage.setItem(k, JSON.stringify(s)); } })()")
        page = context.new_page()
        page.goto(origin + '/web/')
        page.locator('#timer').wait_for()
        page.wait_for_function("document.querySelector('#game') && !document.querySelector('#game').hidden")
        elapsed = saved(page)['elapsedMs']
        if expect_added:
            check(32000 <= elapsed < 40000, f'reload did not add wall-clock time: {elapsed}')
            check(page.locator('#timer').inner_text() in ('00:32', '00:33', '00:34'), 'timer text ' + page.locator('#timer').inner_text())
        else:
            check(elapsed == 2000, f'paused time changed across reload: {elapsed}')
        context.close()
    results['checks'].append({'browser': engine, 'test': 'timer-wall-clock-restore-and-pause', 'status': 'passed'})

    # --- Touch behaviours -----------------------------------------------------------------
    context = phone(browser)
    page = context.new_page()
    load(page, origin + '/web/')
    box = cell(page, empty[0]).bounding_box()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.mouse.down(); page.wait_for_timeout(800); page.mouse.up()
    check(page.evaluate("window.getSelection().toString()") == '', 'long press selected text')
    styles = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('#board')); return [s.userSelect || s.webkitUserSelect, s.webkitTouchCallout]; })()")
    check(styles[0] == 'none', f'board user-select {styles}')
    check(page.evaluate("document.querySelector('meta[name=viewport]').content").find('user-scalable') < 0, 'zoom disabled')
    prevented = page.evaluate("(() => { const e = new MouseEvent('contextmenu', {bubbles: true, cancelable: true}); document.querySelector('.cell').dispatchEvent(e); return e.defaultPrevented; })()")
    check(prevented, 'board contextmenu not suppressed')
    for _ in range(3):
        cell(page, empty[1]).tap()
    page.evaluate('scrollBy(0, 400); scrollBy(300, 0)')
    check(page.evaluate('scrollX') == 0 and page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'horizontal scroll')
    focusable = page.evaluate("document.querySelectorAll('input, textarea, select, [contenteditable]').length")
    check(focusable == 0, 'text-entry element exists in the page')
    context.close()
    results['checks'].append({'browser': engine, 'test': 'touch-selection-callout-scroll-zoom', 'status': 'passed'})

    # --- Error / empty databases -------------------------------------------------------------
    def with_payload(payload, status=200):
        ctx = phone(browser)
        pg = ctx.new_page()
        logs = []
        pg.on('console', lambda m: logs.append((m.type, m.text)))
        pg.on('pageerror', lambda e: logs.append(('pageerror', str(e))))
        pg.route(DB_ROUTE, lambda route: route.fulfill(status=status, content_type='application/json', body=payload if isinstance(payload, str) else json.dumps(payload)))
        pg.goto(origin + '/web/')
        pg.locator('.load-message, #game:not([hidden])').first.wait_for()
        return ctx, pg, logs

    for name, payload, key in (
        ('empty', production_payload(), 'empty'),
        ('only-preliminary', production_payload(*[{**REAL, 'id': f'p{i}', 'certification': {**REAL['certification'], 'status': s}} for i, s in enumerate(['PRELIMINARY', 'SEARCH_INCONCLUSIVE', 'SEARCH_TIMEOUT', 'REJECTED', 'UNRATED'])]), 'empty'),
        ('unsupported-schema', {**production_payload(REAL), 'schemaVersion': 2}, 'load'),
        ('wrong-kind', {**production_payload(REAL), 'datasetKind': 'demo'}, 'load'),
        ('invalid-json', '{not json', 'load'),
    ):
        ctx, pg, logs = with_payload(payload)
        check(pg.locator('.load-message').inner_text() == CORRECT_PATH_MESSAGES[key], f'{name}: message')
        check(not pg.locator('#game').is_visible(), f'{name}: game visible')
        check(not [l for l in logs if l[0] == 'pageerror'], f'{name}: page error {logs}')
        if name == 'only-preliminary':
            check(len([l for l in logs if l[0] == 'warning']) == 5, f'{name}: diagnostics {logs}')
        ctx.close()
    ctx, pg, logs = with_payload(None, status=404)
    check(pg.locator('.load-message').inner_text() == CORRECT_PATH_MESSAGES['load'], 'HTTP 404 message')
    ctx.close()
    ctx, pg, logs = with_payload(production_payload({**REAL, 'id': 'prelim', 'certification': {**REAL['certification'], 'status': 'PRELIMINARY'}}, REAL, {'id': 'junk'}))
    pg.locator('#game').wait_for()
    check(saved(pg)['puzzleId'] == REAL['id'], 'certified puzzle not chosen next to PRELIMINARY')
    check(len([l for l in logs if l[0] == 'warning']) == 2, f'diagnostics {logs}')
    ctx.close()
    results['checks'].append({'browser': engine, 'test': 'production-loader-errors-empty-and-uncertified', 'status': 'passed'})

    # --- Per-puzzle storage: unknown ids / legacy saves ---------------------------------------
    ctx = phone(browser)
    ctx.add_init_script(seed({**saved_snapshot_template(), 'puzzleId': 'old-demo-puzzle'}) + "localStorage.setItem('extreme-sudoku.game.v1', JSON.stringify({version: 1, puzzleId: 'old-demo-puzzle', values: []}));")
    pg = ctx.new_page()
    load(pg, origin + '/web/')
    check(saved(pg)['puzzleId'] == REAL['id'], 'unknown-ID save not replaced')
    check(pg.evaluate("localStorage.getItem('extreme-sudoku.game.v1')") is None, 'legacy save not cleaned up')
    check(sorted(pg.evaluate("Object.keys(JSON.parse(localStorage.getItem('" + STORE + "')).games)")) == sorted([REAL['id'], 'old-demo-puzzle']), 'unknown-ID save must be kept')
    check(pg.evaluate("JSON.parse(localStorage.getItem('" + STORE + "')).storageSchemaVersion") == 2, 'schema version')
    ctx.close()
    results['checks'].append({'browser': engine, 'test': 'storage-unknown-legacy-puzzle-ids', 'status': 'passed'})

    # --- Built dist served below a project sub-path (GitHub Pages) ----------------------------
    ctx = phone(browser)
    pg = ctx.new_page()
    failures, urls = [], []
    pg.on('response', lambda r: (urls.append(r.url), failures.append(r.url) if r.status >= 400 else None))
    pg.on('requestfailed', lambda r: failures.append(r.url))
    logs = []
    pg.on('console', lambda m: logs.append((m.type, m.text)))
    pg.goto(origin + '/repo-name/')
    pg.locator('#board [data-index]').nth(80).wait_for()
    check(saved(pg)['puzzleId'] == REAL['id'] and pg.locator('#cert-badge').is_visible(), 'dist app did not start')
    check(not failures, f'dist failing requests {failures}')
    check(any(u.endswith('/repo-name/data/production/puzzles.json') for u in urls), 'dist JSON path')
    check(all('/repo-name/' in u for u in urls), f'dist request escaped the sub-path {urls}')
    check(not [l for l in logs if l[0] in ('error',)], f'dist console errors {logs}')
    pg.locator('#cert-badge').tap()
    check('0.1.0' in pg.locator('#sheet-content').inner_text() and 'Grouped AIC' in pg.locator('#sheet-content').inner_text(), 'dist details (slim JSON + version)')
    size = pg.evaluate("performance.getEntriesByType('resource').find(e => e.name.endsWith('puzzles.json')).transferSize")
    check(size < 20000, f'published JSON too large: {size}')
    results.setdefault('dist', {})[engine] = {'jsonTransferBytes': size, 'requests': len(urls)}
    ctx.close()
    results['checks'].append({'browser': engine, 'test': 'dist-served-from-project-subpath', 'status': 'passed'})

    # --- Baseline performance (production data, 390x844) -----------------------------------
    ctx = phone(browser)
    pg = ctx.new_page()
    pg.goto(origin + '/web/')
    pg.locator('#board [data-index]').nth(80).wait_for()
    pg.wait_for_function("performance.getEntriesByName('es:first-render').length > 0")
    perf = pg.evaluate("""async () => {
      const nav = performance.getEntriesByType('navigation')[0];
      const m = n => performance.getEntriesByName('es:' + n)[0].startTime;
      const res = performance.getEntriesByType('resource').find(e => e.name.endsWith('puzzles.json'));
      const cells = [...document.querySelectorAll('.cell')];
      const times = [];
      for (let i = 0; i < 40; i++) {
        const t = performance.now();
        cells[(i * 7) % 81].click();
        await new Promise(r => requestAnimationFrame(() => r()));
        times.push(performance.now() - t);
      }
      times.sort((a, b) => a - b);
      return {domContentLoadedMs: nav.domContentLoadedEventEnd, loadEventMs: nav.loadEventEnd,
        jsonFetchAndParseMs: m('json-end') - m('json-start'), jsonFetchMs: res.responseEnd - res.startTime,
        firstRenderMs: m('first-render'), jsonBytes: res.encodedBodySize,
        selectMedianMs: times[20], selectP95Ms: times[38]};
    }""")
    results.setdefault('performance', {})[engine] = perf
    ctx.close()


def saved_snapshot_template():
    return {'version': 1, 'puzzleFingerprint': REAL['puzzle'], 'values': [int(d) for d in REAL['puzzle']],
            'notes': [[] for _ in range(81)], 'selectedCell': 0, 'notesMode': False, 'elapsedMs': 1000,
            'status': 'playing', 'mistakes': 0, 'hintsUsed': 0, 'history': []}


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
    parser.add_argument("--browser", choices=("all", "chromium", "webkit"), default="all")
    args = parser.parse_args()
    ARTIFACTS.mkdir(exist_ok=True)
    build_dist()
    results = {"browsers": [], "checks": [], "layouts": []}
    with server() as origin, sync_playwright() as playwright:
        for name in ("chromium", "webkit"):
            if args.browser not in ("all", name):
                continue
            browser = getattr(playwright, name).launch()
            print(f'Running {name}', flush=True)
            results["browsers"].append({"engine": name, "version": browser.version})
            try:
                run_browser(browser, origin, name, results)
            finally:
                browser.close()
    (ARTIFACTS / "browser-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
