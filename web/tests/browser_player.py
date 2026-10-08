"""Current player-flow regression scenarios shared by real browser engines.

The older harness supplies HTTP serving, production data, visual checks and the
unchanged core Sudoku interaction tests. No real browser profile is used.
"""
import json

PROFILE = 'extreme-sudoku.profile.v1'
ACTIVITY = 'extreme-sudoku.activity.v1'


def run_player_checks(browser, origin, engine, results, h):
    def passed(name):
        results['checks'].append({'browser': engine, 'test': name, 'status': 'passed'})

    def context(init=None, records=None):
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True)
        if init:
            ctx.add_init_script(init)
        if records is not None:
            body = json.dumps(h.production_payload(*records))
            ctx.route(h.DB_ROUTE, lambda route: route.fulfill(content_type='application/json', body=body))
        return ctx

    def profile(page, name='Player <test>', preparation='experienced'):
        page.locator('#player-name').fill(name)
        page.locator('#player-preparation').select_option(preparation)
        page.locator('#save-profile').click()
        page.locator('#home-new').wait_for()

    def begin(page, difficulty):
        if page.locator('#home-new').is_visible():
            page.locator('#home-new').click()
        else:
            page.locator('#menu-button').click()
            page.locator('[data-menu="new"]').click()
        page.locator(f'[data-difficulty="{difficulty}"]').click()
        page.locator('#start-game').click()
        page.locator('#game').wait_for()

    def home(page):
        page.locator('#home-button').click()
        page.locator('#home-new').wait_for()

    def activity(page):
        return page.evaluate(f"JSON.parse(localStorage.getItem('{ACTIVITY}') || '{{}}')")

    def complete(page, puzzle):
        for index, given in enumerate(puzzle['puzzle']):
            if given == '0':
                page.locator(f'.cell[data-index="{index}"]').click()
                page.locator(f'.number-button[data-digit="{puzzle["solution"][index]}"]').click()
        page.locator('#result-stats').wait_for()

    # New visits must collect a local profile, without starting the timer or a puzzle.
    ctx = context()
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(origin + '/web/')
    page.locator('#profile-form').wait_for()
    page.screenshot(path=str(h.ARTIFACTS / f'{engine}-profile.png'), full_page=True)
    h.check(not page.locator('#game').is_visible(), 'first visit started a puzzle')
    page.locator('#player-name').fill('   ')
    page.locator('#player-preparation').select_option('experienced')
    page.locator('#save-profile').click()
    h.check(page.locator('#profile-error').inner_text(), 'whitespace profile accepted')
    profile(page)
    h.check('Player <test>' in page.locator('#home').inner_text(), 'profile name was not escaped/rendered')
    h.check(page.locator('#home test').count() == 0, 'profile name became markup')
    page.locator('#home-new').click()
    available = sorted({p['difficulty'] for p in h.PRODUCTION['puzzles']})
    offered = sorted(page.locator('[data-difficulty]').evaluate_all('(els) => els.map(e => e.dataset.difficulty)'))
    h.check(offered == available, 'picker omits verified levels or offers empty levels')
    h.check(page.locator('[data-difficulty="Hard"]').get_attribute('aria-pressed') == 'true', 'experienced recommendation is not Hard')
    page.locator('#close-sheet').click()
    page.locator('#edit-profile').click()
    page.locator('#player-name').fill('Updated player')
    page.locator('#player-preparation').select_option('beginner')
    page.locator('#save-profile').click()
    page.reload()
    page.locator('#home-new').wait_for()
    h.check('Updated player' in page.locator('#home').inner_text(), 'profile change lost after reload')
    h.check(not errors, f'profile errors: {errors}')
    page.screenshot(path=str(h.ARTIFACTS / f'{engine}-home.png'), full_page=True)
    ctx.close()
    passed('mandatory-local-profile-edit-reload-preparation-all-levels')

    # Real production Hard/Expert and all remaining categories: explicit start,
    # isolated notes, metadata, reload home, paused restore, permanent seen IDs.
    ctx = context()
    page = ctx.new_page()
    page.goto(origin + '/web/')
    profile(page)
    snapshots = {}
    for difficulty in available:
        begin(page, difficulty)
        current = h.saved(page)
        puzzle = next(p for p in h.PRODUCTION['puzzles'] if p['id'] == current['puzzleId'])
        h.check(puzzle['difficulty'] == difficulty, f'wrong {difficulty} selection')
        page.locator('#cert-badge').click()
        details = page.locator('#sheet-content').inner_text()
        h.check(puzzle['id'] in details and difficulty in details, 'details describe another puzzle')
        if difficulty != 'Extreme':
            h.check('Certified Extreme' not in details, 'standard puzzle claims Extreme certification')
        h.modal_fits(page)
        page.locator('#close-sheet').click()
        index = puzzle['puzzle'].index('0')
        page.locator(f'.cell[data-index="{index}"]').click()
        page.locator('#notes-button').click()
        page.locator('.number-button[data-digit="1"]').click()
        snapshots[puzzle['id']] = h.saved(page)
        home(page)
    page.reload()
    page.locator('#home-new').wait_for()
    h.check(page.locator('[data-continue]').count() == len(available), 'unfinished collection lost games')
    for pid, previous in snapshots.items():
        page.locator(f'[data-continue="{pid}"]').click()
        page.locator('#resume-button').wait_for()
        current = h.saved(page)
        h.check(current['status'] == 'paused', 'restore auto-resumed timer')
        for key in ('values', 'notes', 'hintsUsed', 'mistakes', 'attemptId'):
            h.check(current[key] == previous[key], f'{pid}: restore lost {key}')
        home(page)
    ctx.close()
    passed('all-production-levels-details-isolation-explicit-paused-resume')

    # Small real fixture makes exhaustion exact and repeat detection deterministic.
    pair = [p for p in h.PRODUCTION['puzzles'] if p['difficulty'] == 'Easy'][:2]
    ctx = context(records=pair)
    page = ctx.new_page()
    page.goto(origin + '/web/')
    profile(page, preparation='beginner')
    begin(page, 'Easy')
    first = h.saved(page)['puzzleId']
    page.wait_for_timeout(1150)
    page.evaluate("Object.defineProperty(document, 'hidden', {configurable:true, get:()=>true}); document.dispatchEvent(new Event('visibilitychange'))")
    paused = h.saved(page)
    h.check(paused['status'] == 'paused' and paused['elapsedMs'] >= 1000, 'hidden page did not pause active time')
    page.wait_for_timeout(1150)
    page.evaluate("Object.defineProperty(document, 'hidden', {configurable:true, get:()=>false}); document.dispatchEvent(new Event('visibilitychange'))")
    h.check(h.saved(page)['elapsedMs'] == paused['elapsedMs'], 'hidden time was charged')
    h.check(h.saved(page)['status'] == 'paused', 'visibility restore auto-resumed')
    page.locator('#resume-button').click()
    home(page)
    begin(page, 'Easy')
    second = h.saved(page)['puzzleId']
    h.check(second != first, 'new game repeated an already started puzzle')
    home(page)
    page.locator('#home-new').click()
    h.check(page.locator('#start-game').is_disabled(), 'exhausted category can start a repeat')
    h.check(page.locator('#exhausted-message').inner_text(), 'exhaustion lacks a message')
    h.check(page.locator('#replay-puzzle').count() == 0, 'replay returned after exhaustion')
    page.locator('#continue-games').click()
    page.locator(f'[data-continue="{first}"]').click()
    h.check(h.saved(page)['puzzleId'] == first, 'explicit continue picked another game')
    ctx.close()
    passed('active-time-hidden-pause-new-only-exhaustion-explicit-continue')

    # Each completion is immutable and recorded once; restart preserves an
    # unfinished attempt, including its assistance counters.
    ctx = context(records=pair)
    page = ctx.new_page()
    page.goto(origin + '/web/')
    profile(page, preparation='beginner')
    begin(page, 'Easy')
    page.locator('#hint-button').click()
    page.locator('#confirm-hint').click()
    page.locator('#undo-button').click()
    h.check(h.saved(page)['hintsUsed'] == 1, 'Undo erased reveal assistance')
    before_restart = h.saved(page)['attemptId']
    page.locator('#menu-button').click()
    page.locator('[data-menu="restart"]').click()
    page.locator('#confirm-restart').click()
    h.check(h.saved(page)['attemptId'] != before_restart, 'restart reused attempt ID')
    h.check(activity(page)['results'][before_restart]['status'] == 'restarted', 'restart discarded attempt history')
    puzzle = next(p for p in pair if p['id'] == h.saved(page)['puzzleId'])
    complete(page, puzzle)
    completed_id = h.saved(page)['attemptId']
    h.check(activity(page)['results'][completed_id]['status'] == 'completed', 'completion missing from history')
    h.check(page.locator('#result-restart').count() == 0, 'completion offers a replay')
    h.modal_fits(page)
    page.screenshot(path=str(h.ARTIFACTS / f'{engine}-completion.png'), full_page=True)
    page.locator('#result-stats').click()
    h.check('1 recorded completions' in page.locator('#sheet-content').inner_text(), 'statistics omit completion')
    for width, height in ((320, 568), (844, 390), (810, 1080)):
        page.set_viewport_size({'width': width, 'height': height})
        h.modal_fits(page)
        h.check(page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'statistics horizontal page overflow')
    page.screenshot(path=str(h.ARTIFACTS / f'{engine}-statistics.png'), full_page=True)
    page.reload()
    page.locator('#home-new').wait_for()
    h.check(page.locator(f'[data-continue="{puzzle["id"]}"]').count() == 0, 'completed game appears unfinished')
    page.locator('#home-stats').click()
    h.check('1 recorded completions' in page.locator('#sheet-content').inner_text(), 'reload double-counted completion')
    h.check(len(activity(page)['results']) == 2, 'attempt history changed on reload')
    ctx.close()
    passed('reveal-undo-restart-attempt-history-completion-idempotent-statistics-layout')

    # The second tab cannot migrate or write until the owner closes.
    ctx = context()
    owner = ctx.new_page()
    owner.goto(origin + '/web/')
    profile(owner)
    begin(owner, 'Hard')
    waiting = ctx.new_page()
    waiting.goto(origin + '/web/')
    waiting.locator('#load-state .load-message').wait_for()
    h.check(not waiting.locator('#home').is_visible(), 'second tab acquired an existing writer lock')
    initial = waiting.evaluate('JSON.stringify(Object.entries(localStorage).sort())')
    waiting.wait_for_timeout(300)
    h.check(waiting.evaluate('JSON.stringify(Object.entries(localStorage).sort())') == initial, 'waiting tab mutated saved data')
    owner.goto('about:blank')
    waiting.locator('#home-new').wait_for()
    h.check(waiting.locator('[data-continue]').count() == 1, 'writer takeover lost owner game')
    waiting.locator('[data-continue]').click()
    h.check(h.saved(waiting)['status'] == 'paused', 'writer takeover auto-resumed stale timer')
    owner.go_back()
    owner.locator('#load-state .load-message').wait_for()
    h.check(not owner.locator('#home').is_visible(), 'back navigation bypassed current writer')
    waiting.close()
    owner.locator('#home-new').wait_for()
    ctx.close()
    passed('exclusive-writer-wait-navigation-back-close-reread-takeover')

    # All checking modes must reject an incorrect full board and recognize only
    # the true solution. Seeding a nearly solved state avoids solver execution.
    puzzle = pair[0]
    empty = [i for i, digit in enumerate(puzzle['puzzle']) if digit == '0']
    wrong, last = empty[:2]
    for mode in ('immediate', 'completion', 'off'):
        state = h.saved_snapshot_template(puzzle=puzzle)
        state['values'] = list(map(int, puzzle['solution']))
        state['values'][wrong] = int(puzzle['solution'][wrong]) % 9 + 1
        state['values'][last] = 0
        state['selectedCell'] = last
        ctx = context(init=h.seed(state, {'errorMode': mode}), records=pair)
        page = ctx.new_page()
        h.load(page, origin + '/web/')
        page.locator(f'.number-button[data-digit="{puzzle["solution"][last]}"]').click()
        h.check(h.saved(page)['status'] == 'playing', f'{mode}: wrong complete board accepted')
        h.check(page.locator('.cell.error').count() == (0 if mode == 'off' else 1), f'{mode}: incorrect error display')
        page.locator(f'.cell[data-index="{wrong}"]').click()
        page.locator(f'.number-button[data-digit="{puzzle["solution"][wrong]}"]').click()
        page.locator('#result-stats').wait_for()
        h.check(h.saved(page)['status'] == 'completed', f'{mode}: valid completion not recognized')
        ctx.close()
    passed('incorrect-correct-full-board-all-three-error-modes')

    # Actual legacy completed state is migrated, while missing details stay unknown.
    legacy = h.saved_snapshot_template(puzzle=pair[0])
    legacy.update(values=list(map(int, pair[0]['solution'])), status='completed')
    init = f"localStorage.setItem('extreme-sudoku.game.v1', {json.dumps(json.dumps(legacy))});"
    ctx = context(init=init, records=pair)
    page = ctx.new_page()
    page.goto(origin + '/web/')
    profile(page)
    page.locator('#home-stats').click()
    text = page.locator('#sheet-content').inner_text()
    h.check('1 recorded completions' in text and 'Date unknown' in text and 'legacy / mixed time' in text, 'legacy details fabricated or completion lost')
    h.check('No comparable active-time records yet' in text, 'legacy completion became an active-time record')
    h.check(page.evaluate("localStorage.getItem('extreme-sudoku.game.v1')") is None, 'legacy source not removed after successful migration')
    ctx.close()
    passed('legacy-completion-migration-unknown-metadata-no-new-time-record')

    # Failed storage and absent secure-context locking must fail closed, not create
    # a profile whose progress silently disappears. Broken data remains recoverable.
    for init, label in (("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Blocked','SecurityError')}})", 'blocked-storage'),
                        ("Object.defineProperty(navigator,'locks',{value:undefined})", 'unavailable-locks')):
        ctx = context(init=init)
        page = ctx.new_page()
        page.goto(origin + '/web/')
        page.locator('#load-state .load-message').wait_for()
        h.check(not page.locator('#game').is_visible() and not page.locator('#profile-form').is_visible(), f'{label}: unsafe writing permitted')
        ctx.close()
    ctx = context(init=f"localStorage.setItem('{h.STORE}','{{broken');localStorage.setItem('{ACTIVITY}','{{broken');")
    page = ctx.new_page()
    page.goto(origin + '/web/')
    profile(page)
    begin(page, 'Easy')
    h.check(h.saved(page)['status'] == 'playing', 'corrupt local state blocked a new game')
    ctx.close()
    passed('blocked-storage-missing-web-locks-corrupt-state-recovery')

    # Network retry and no-silent-fallback retain the existing production contract.
    ctx = context()
    page = ctx.new_page()
    page.route(h.DB_ROUTE, lambda route: route.fulfill(status=503, body='Unavailable'))
    page.goto(origin + '/web/')
    page.locator('#retry-loading').wait_for()
    h.check(not page.locator('#game').is_visible(), 'network failure silently loaded demo data')
    page.unroute(h.DB_ROUTE)
    page.locator('#retry-loading').click()
    page.locator('#profile-form').wait_for()
    ctx.close()
    ctx = context(records=[])
    page = ctx.new_page()
    page.goto(origin + '/web/')
    page.locator('#load-state .load-message').wait_for()
    h.check(not page.locator('#game').is_visible(), 'empty production silently loaded demo data')
    ctx.close()
    passed('production-network-retry-empty-database-no-fallback')

    # Built Pages layout, not just /web/, is playable under a project prefix.
    ctx = context()
    page = ctx.new_page()
    h.load(page, origin + '/repo-name/')
    h.check(page.locator('.cell').count() == 81, 'built Pages subpath failed')
    ctx.close()
    passed('built-pages-project-prefix-profile-playable')
