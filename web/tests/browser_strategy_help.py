"""Illustrated strategy regression using disposable browser profiles.

Requires the optional Playwright Python package and a managed browser (same as
browser_regression.py). Build first with node scripts/build_pages.mjs, then:
    python web/tests/browser_strategy_help.py --engine chromium --matrix
    python web/tests/browser_strategy_help.py --engine webkit --width 320
    python web/tests/browser_strategy_help.py --base-url https://example.test/
All artifacts stay in --artifacts; existing browser profiles are never used.
"""
import functools
import http.server
import json
import os
from pathlib import Path
import sys
import threading

import argparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-url', help='Existing dev or published page; default serves built dist locally')
parser.add_argument('--artifacts', type=Path, default=ROOT / 'web/artifacts/strategy-help')
parser.add_argument('--engine', choices=['chromium', 'firefox', 'webkit'], default='chromium')
parser.add_argument('--width', type=int, default=390)
parser.add_argument('--height', type=int, default=900)
parser.add_argument('--theme', choices=['light', 'dark'], default='dark')
parser.add_argument('--difficulty', choices=['Easy', 'Medium', 'Hard', 'Expert', 'Extreme'], default='Easy')
parser.add_argument('--matrix', action='store_true', help='All six desktop/mobile theme combinations')
parser.add_argument('--release', default='working-tree')
args = parser.parse_args()
HERE = args.artifacts.resolve()
HERE.mkdir(parents=True, exist_ok=True)
os.environ.pop('NODE_TLS_REJECT_UNAUTHORIZED', None)
release = args.release
mode = 'remote' if args.base_url else 'local'
server = None
if not args.base_url:
    if not (ROOT / 'dist/index.html').is_file():
        parser.error('Build the site first: node scripts/build_pages.mjs')
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT / 'dist')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}/'
else:
    base = args.base_url.rstrip('/') + '/'

STRATEGIES = ['full-house', 'naked-single', 'hidden-single', 'pointing', 'claiming', 'naked-pair', 'hidden-pair', 'x-wing', 'xy-wing']
STORE = 'extreme-sudoku.progress.v2'
checks = []
layouts = []

def saved(page):
    return page.evaluate("() => { const s = JSON.parse(localStorage.getItem('extreme-sudoku.progress.v2')); return s.games[s.activePuzzleId]; }")

def storage_without_progress(page):
    return page.evaluate("() => Object.fromEntries(['extreme-sudoku.profile.v1','extreme-sudoku.activity.v1','extreme-sudoku.recent.v1'].map(k => [k,localStorage.getItem(k)]))")

def game_payload(state):
    return {key: value for key, value in state.items() if key not in ['status', 'elapsedMs', 'lastSeen', 'updatedAt', 'savedAt']}

def assert_layout(page, name):
    metrics = page.evaluate("""() => {
      const d = document.querySelector('#sheet');
      const svgs = [...d.querySelectorAll('svg')].filter(e => e.getBoundingClientRect().width > 100);
      return {viewport:innerWidth, documentWidth:document.documentElement.scrollWidth,
        dialog:{x:d.getBoundingClientRect().x, right:d.getBoundingClientRect().right, width:d.clientWidth, scrollWidth:d.scrollWidth},
        diagrams:svgs.map(s => ({width:s.getBoundingClientRect().width,height:s.getBoundingClientRect().height,text:s.querySelectorAll('text').length,label:s.getAttribute('aria-label')||s.querySelector('title')?.textContent}))};
    }""")
    assert metrics['documentWidth'] <= metrics['viewport'] + 1, (name, metrics)
    assert metrics['dialog']['scrollWidth'] <= metrics['dialog']['width'] + 1, (name, metrics)
    assert metrics['dialog']['x'] >= -1 and metrics['dialog']['right'] <= metrics['viewport'] + 1, (name, metrics)
    layouts.append({'name': name, **metrics})

try:
    with sync_playwright() as playwright:
        browser = getattr(playwright, args.engine).launch()
        matrix = [(320, 'light'), (390, 'dark'), (1280, 'light'), (1280, 'dark'), (320, 'dark'), (390, 'light')] if args.matrix else [(args.width, args.theme)]
        errors = []
        outside_requests = []
        for width, theme in matrix:
            context = browser.new_context(viewport={'width': width, 'height': args.height}, color_scheme=theme)
            try:
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: outside_requests.append(request.url) if request.url.startswith('http') and not request.url.startswith(base) else None)
                response = page.goto(base + '?release=' + release)
                assert response.status == 200
                assert page.evaluate('isSecureContext && Boolean(navigator.locks?.request)')
                page.locator('#profile-form').wait_for()
                progress_before_help = page.evaluate("localStorage.getItem('extreme-sudoku.progress.v2')")
                page.locator('#home-strategy-help').focus()
                page.keyboard.press('Enter')
                page.locator('#sheet.strategy-sheet').wait_for()
                assert page.locator('[data-strategy-id]').count() == len(STRATEGIES)
                page.keyboard.press('Escape')
                page.locator('#sheet').wait_for(state='hidden')
                assert page.evaluate('document.activeElement.id') == 'home-strategy-help'
                assert page.evaluate("localStorage.getItem('extreme-sudoku.progress.v2')") == progress_before_help
                page.locator('#player-name').fill('Disposable strategy check')
                page.locator('#player-preparation').select_option('experienced')
                page.locator('#save-profile').click()
                page.locator('#home-strategy-help').click()
                page.locator('#sheet.strategy-sheet').wait_for()
                assert page.locator('[data-strategy-id]').count() == len(STRATEGIES)
                page.keyboard.press('Escape')
                page.locator('#home-new').click()
                page.locator(f'[data-difficulty="{args.difficulty}"]').click()
                page.locator('#start-game').click()
                page.locator('#game').wait_for()
                assert 'Открыть цифру' in page.locator('#hint-button').inner_text()
                state = saved(page)
                index = state['values'].index(0)
                page.locator(f'.cell[data-index="{index}"]').click()
                page.locator('#notes-button').click()
                page.locator('.number-button[data-digit="3"]').click()
                before = saved(page)
                activity_before = storage_without_progress(page)
                page.locator('#strategy-help-button').click()
                page.locator('#sheet.strategy-sheet').wait_for()
                after_open = saved(page)
                assert after_open['status'] == 'paused'
                assert game_payload(before) == game_payload(after_open), 'Opening help changed game data'
                assert_layout(page, f'{width}-{theme}-catalog')
                # Modal keyboard actions must not reach the active Sudoku board.
                page.keyboard.press('7')
                page.keyboard.press('n')
                page.keyboard.press('ArrowRight')
                assert game_payload(saved(page)) == game_payload(after_open)
                for strategy in STRATEGIES:
                    page.locator(f'[data-strategy-id="{strategy}"]').click()
                    page.locator('#strategy-step-heading').wait_for()
                    assert page.locator('#strategy-previous').is_disabled()
                    steps = 0
                    while True:
                        steps += 1
                        assert steps < 12
                        assert_layout(page, f'{width}-{theme}-{strategy}-{steps}')
                        count_text = page.locator('#strategy-step-count').inner_text().split()
                        if count_text[1] == count_text[3]:
                            break
                        page.locator('#strategy-next').click()
                    assert steps >= 3
                    page.locator('#strategy-previous').click()
                    assert 'Следующий' in page.locator('#strategy-next').inner_text()
                    if strategy == 'x-wing':
                        page.locator('#strategy-zoom').click()
                        assert_layout(page, f'{width}-{theme}-{strategy}-zoom')
                        page.screenshot(path=str(HERE / f'{mode}-{width}-{theme}-x-wing.png'), full_page=True)
                    page.locator('#strategy-back').click()
                    assert page.locator('[data-strategy-id]').count() == len(STRATEGIES)
                page.locator('#strategy-keyboard').click()
                assert 'Escape' in page.locator('#sheet-content').inner_text()
                page.keyboard.press('Escape')
                page.locator('#resume-button').wait_for()
                assert page.evaluate('document.activeElement.id') == 'strategy-help-button'
                assert saved(page)['status'] == 'paused'
                assert storage_without_progress(page) == activity_before, 'Help changed local profile or statistics'
                assert game_payload(saved(page)) == game_payload(before), 'Help changed values, notes, hints, settings or history'
                page.locator('#resume-button').click()
                assert saved(page)['status'] == 'playing'
                checks.append(f'{width}px {theme}: catalogue, all 9 step lessons, zoom, keyboard, paused return, unchanged game/statistics')
            finally:
                context.close()
        assert not errors, errors
        assert not outside_requests, outside_requests
        report = {'status': 'passed', 'mode': mode, 'url': base, 'releaseCommit': release, 'engine': args.engine, 'browser': browser.version, 'checks': checks, 'layoutCases': layouts, 'javascriptErrors': errors, 'externalAssetRequests': outside_requests}
        (HERE / f'{mode}-smoke.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps({**report, 'layoutCases': len(layouts)}, ensure_ascii=False, indent=2))
        browser.close()
finally:
    if server:
        server.shutdown()
        server.server_close()
