import { SudokuGame } from './lib/game.js';
import { loadProductionPuzzles, certificationLabel, hardestStep, DIFFICULTIES } from './lib/data.js';
import { loadSave, saveGame, activePuzzleId, reconcileStorage, loadSettings, saveSettings, loadRecent, rememberPuzzle } from './lib/storage.js';

const MESSAGES = Object.freeze({
  loadFailed: 'Не удалось загрузить базу Sudoku. Попробуйте обновить страницу.',
  noPuzzles: 'Сейчас нет доступных сертифицированных Sudoku.',
  allPlayed: 'Все доступные Certified Sudoku уже сыграны. Можно решить эту задачу ещё раз.',
  certificationNote: 'Эта задача прошла проверку уникальности, логических доказательств и альтернативных путей в текущей версии системы Extreme Sudoku.',
});
const mark = (name) => { try { performance.mark(`es:${name}`); } catch { /* optional instrumentation */ } };

const $ = (selector) => document.querySelector(selector);
const sheet = $('#sheet');
const sheetContent = $('#sheet-content');
const cells = [];
const numberButtons = [];
let puzzles = [];
let game;
let sheetReturnFocus;
let hintedCell = -1;
let storageAvailable = true;
let completionShown = false;
let appVersion = null;
let persistTimer = 0;
let reopenCompletion = false;
const settings = loadSettings();
const systemTheme = matchMedia('(prefers-color-scheme: dark)');
const isRecord = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const escapeHTML = (value) => String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const timeString = (seconds) => {
  const time = Math.max(0, Math.floor(seconds));
  const parts = [Math.floor(time / 60) % 60, time % 60];
  if (time >= 3600) parts.unshift(Math.floor(time / 3600));
  return parts.map((part) => String(part).padStart(2, '0')).join(':');
};
const coordinate = (index) => `r${Math.floor(index / 9) + 1}c${index % 9 + 1}`;

function applyTheme() {
  const theme = game?.state.settings.theme || settings.theme || 'system';
  const resolved = theme === 'system' ? (systemTheme.matches ? 'dark' : 'light') : theme;
  document.documentElement.dataset.theme = resolved;
  $('meta[name="theme-color"]').content = resolved === 'dark' ? '#17221f' : '#f5f5f0';
}
applyTheme();
systemTheme.addEventListener('change', applyTheme);

function announce(message) { $('#announcement').textContent = message; }
function persist() {
  clearTimeout(persistTimer);
  if (!game) return;
  if (!saveGame(game.snapshot())) {
    if (storageAvailable) announce('Device storage is unavailable. You can keep playing, but progress may not survive a reload.');
    storageAvailable = false;
  }
  $('#save-status').textContent = storageAvailable ? 'Saved on this device' : 'Progress cannot be saved';
}
// Selection taps only move the cursor: defer the (large) save so a tap stays instant. Flushed when hidden.
function persistSoon() { clearTimeout(persistTimer); persistTimer = setTimeout(persist, 400); }

for (let rowIndex = 0; rowIndex < 9; rowIndex++) {
  const row = document.createElement('div');
  row.className = 'board-row';
  row.setAttribute('role', 'row');
  row.setAttribute('aria-rowindex', rowIndex + 1);
  for (let column = 0; column < 9; column++) {
    const index = rowIndex * 9 + column;
    const cell = document.createElement('button');
    cell.className = 'cell';
    cell.dataset.index = index;
    cell.setAttribute('role', 'gridcell');
    cell.setAttribute('aria-colindex', column + 1);
    cell.tabIndex = index === 0 ? 0 : -1;
    cell.addEventListener('click', () => {
      if (game?.state.status !== 'playing') return;
      game.select(index);
      render();
      persistSoon();
    });
    cells.push(cell);
    row.append(cell);
  }
  $('#board').append(row);
}
for (let digit = 1; digit <= 9; digit++) {
  const button = document.createElement('button');
  button.className = 'number-button';
  button.dataset.digit = digit;
  button.textContent = digit;
  button.setAttribute('aria-label', `Enter ${digit}`);
  button.addEventListener('click', () => act(() => game.input(digit)));
  numberButtons.push(button);
  $('#number-pad').append(button);
}

function render() {
  const { puzzle, values, notes, selectedCell, notesMode, status, mistakes, history } = game.state;
  const selectedValue = values[selectedCell];
  const selectedRow = Math.floor(selectedCell / 9);
  const selectedColumn = selectedCell % 9;
  const checkErrors = game.state.settings.errorMode === 'immediate' || (game.state.settings.errorMode === 'completion' && values.every(Boolean));
  cells.forEach((cell, index) => {
    const value = values[index];
    const given = puzzle.puzzle[index] !== '0';
    const row = Math.floor(index / 9);
    const column = index % 9;
    const related = row === selectedRow || column === selectedColumn || (Math.floor(row / 3) === Math.floor(selectedRow / 3) && Math.floor(column / 3) === Math.floor(selectedColumn / 3));
    const wrong = checkErrors && value && value !== Number(puzzle.solution[index]);
    cell.className = ['cell', given && 'given', related && 'related', selectedValue && value === selectedValue && 'same-value', index === selectedCell && 'selected', wrong && 'error', index === hintedCell && 'hinted'].filter(Boolean).join(' ');
    cell.tabIndex = index === selectedCell ? 0 : -1;
    cell.setAttribute('aria-selected', String(index === selectedCell));
    cell.setAttribute('aria-readonly', String(given));
    const detail = value ? `${given ? 'given ' : ''}${value}${wrong ? ', incorrect' : ''}` : notes[index].length ? `notes ${notes[index].join(', ')}` : 'empty';
    cell.setAttribute('aria-label', `Row ${row + 1}, column ${column + 1}, ${detail}`);
    const content = value ? String(value) : notes[index].length ? `<span class="pencil-grid" aria-hidden="true">${Array.from({ length: 9 }, (_, n) => `<span>${notes[index].includes(n + 1) ? n + 1 : ''}</span>`).join('')}</span>` : '';
    if (cell.innerHTML !== content) cell.innerHTML = content;
  });
  $('#difficulty').textContent = puzzle.difficulty;
  $('#cert-prefix').hidden = !certificationLabel(puzzle);
  $('#cert-badge').setAttribute('aria-label', `${certificationLabel(puzzle) ?? puzzle.difficulty}. Show puzzle details`);
  $('#clues').textContent = `${puzzle.clues} clues`;
  $('#timer').textContent = timeString(game.elapsedSeconds());
  $('#mistakes').textContent = game.state.settings.errorMode === 'off' ? 'Mistake check off' : `Mistakes ${mistakes}`;
  $('#notes-button').setAttribute('aria-pressed', String(notesMode));
  $('#notes-label').textContent = notesMode ? 'Notes on' : 'Notes';
  $('#input-mode').textContent = status === 'completed' ? 'Solved!' : notesMode ? 'Pencil notes are on' : 'Enter a number';
  $('#selection-label').textContent = `r${selectedRow + 1} · c${selectedColumn + 1}`;
  $('#number-pad').classList.toggle('notes-active', notesMode);
  const paused = status === 'paused';
  $('#pause-overlay').hidden = !paused;
  $('#board').style.visibility = paused ? 'hidden' : '';
  $('#board').inert = paused;
  $('#pause-button').setAttribute('aria-label', paused ? 'Resume game' : 'Pause game');
  $('#pause-button').innerHTML = paused ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7V5Z"/></svg>' : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5v14M15 5v14"/></svg>';
  $('#pause-button').disabled = status === 'completed';
  $('#undo-button').disabled = status !== 'playing' || history.length === 0;
  $('#erase-button').disabled = status !== 'playing' || puzzle.puzzle[selectedCell] !== '0' || (!values[selectedCell] && notes[selectedCell].length === 0);
  $('#notes-button').disabled = status !== 'playing';
  $('#hint-button').disabled = status !== 'playing';
  numberButtons.forEach((button, n) => {
    const digit = n + 1;
    const completed = values.filter((value, i) => value === digit && value === Number(puzzle.solution[i])).length === 9;
    button.classList.toggle('complete', completed);
    button.disabled = status !== 'playing';
    button.setAttribute('aria-label', `${notesMode ? 'Toggle note' : 'Enter'} ${digit}${completed ? ', all nine placed correctly' : ''}`);
  });
  applyTheme();
}

function act(action) {
  if (!game || !action()) return;
  render();
  persist();
  if (game.state.status === 'completed' && !completionShown) {
    completionShown = true;
    rememberPuzzle(game.state.puzzle.id);
    announce('Puzzle solved!');
    showCompletion();
  }
}

function openSheet(title, content, opener) {
  if (!sheet.open) {
    const active = opener || document.activeElement;
    // Safari touch activation does not necessarily focus the pressed button.
    sheetReturnFocus = active && active !== document.body && active !== document.documentElement ? active : cells[game.state.selectedCell];
  }
  $('#sheet-title').textContent = title;
  sheetContent.innerHTML = content;
  if (!sheet.open) sheet.showModal();
  sheet.scrollTop = 0;
  $('#close-sheet').focus({ preventScroll: true });
}
function closeSheet() { sheet.close(); }
$('#close-sheet').addEventListener('click', closeSheet);
sheet.addEventListener('close', () => {
  // A confirmed hint can immediately open the completion dialog.
  if (sheet.open) return;
  if (sheetReturnFocus?.isConnected && !sheetReturnFocus.disabled) sheetReturnFocus.focus({ preventScroll: true });
  else if (game) cells[game.state.selectedCell].focus({ preventScroll: true });
  // Details opened from the completion screen return to it when closed.
  const back = reopenCompletion;
  reopenCompletion = false;
  if (back && game?.state.status === 'completed') showCompletion();
});
sheet.addEventListener('click', (event) => {
  if (event.target !== sheet) return;
  const rect = sheet.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeSheet();
});

function showMenu(event) {
  openSheet('Game', '<div class="menu-list"><button data-menu="new">New Game <span aria-hidden="true">↗</span></button><button data-menu="restart">Restart this puzzle</button><button data-menu="settings">Settings</button><button data-menu="details">Puzzle Details</button><button data-menu="help">How to play & keyboard</button></div>', event?.currentTarget);
  sheetContent.querySelectorAll('[data-menu]').forEach((button) => button.addEventListener('click', () => ({ new: showNewGame, restart: showRestart, settings: showSettings, details: showDetails, help: showHelp })[button.dataset.menu]()));
}

function solvedIds() { return new Set(loadRecent()); }
function pickPuzzle(difficulty) {
  const solved = solvedIds();
  const pool = puzzles.filter((puzzle) => (!difficulty || puzzle.difficulty === difficulty) && puzzle.id !== game?.state.puzzle.id && !solved.has(puzzle.id));
  return pool.length ? pool[Math.floor(Math.random() * pool.length)] : null;
}

function startGame(puzzle, { fresh = false } = {}) {
  const settings = game ? game.state.settings : loadSettings();
  game = new SudokuGame(puzzle, { saved: fresh ? null : loadSave(puzzle.id), settings });
  hintedCell = -1;
  completionShown = game.state.status === 'completed';
  render();
  persist();
}

function showNewGame(event) {
  const opener = event?.currentTarget;
  if (puzzles.length <= 1) {
    // One certified puzzle: say so plainly instead of silently reloading the same board.
    openSheet('New Game', `<p lang="ru" id="all-played-message">${MESSAGES.allPlayed}</p><p lang="ru" class="small-print">Текущий прогресс по этой задаче будет сброшен.</p><div class="dialog-actions"><button id="cancel-new" class="secondary">Отмена</button><button id="replay-puzzle" class="primary">Решить ещё раз</button></div>`, opener);
    $('#cancel-new').addEventListener('click', closeSheet);
    $('#replay-puzzle').addEventListener('click', () => replay(game.state.puzzle));
    return;
  }
  const solved = solvedIds();
  const remaining = puzzles.filter((puzzle) => puzzle.id !== game.state.puzzle.id && !solved.has(puzzle.id));
  if (!remaining.length) {
    openSheet('New Game', `<p lang="ru" id="all-played-message">${MESSAGES.allPlayed}</p><p lang="ru" class="small-print">Будет выбрана случайная задача; её сохранённый прогресс будет сброшен.</p><div class="dialog-actions"><button id="cancel-new" class="secondary">Отмена</button><button id="replay-puzzle" class="primary">Решить ещё раз</button></div>`, opener);
    $('#cancel-new').addEventListener('click', closeSheet);
    $('#replay-puzzle').addEventListener('click', () => replay(puzzles[Math.floor(Math.random() * puzzles.length)]));
    return;
  }
  const counts = Object.fromEntries(DIFFICULTIES.map((difficulty) => [difficulty, remaining.filter((puzzle) => puzzle.difficulty === difficulty).length]));
  const offered = DIFFICULTIES.filter((difficulty) => counts[difficulty]);
  let chosen = offered.includes(game.state.puzzle.difficulty) ? game.state.puzzle.difficulty : offered[0];
  openSheet('New Game', `<p>Your progress on the current puzzle stays saved.</p><div class="difficulty-list">${offered.map((difficulty) => `<button class="difficulty-choice" data-difficulty="${escapeHTML(difficulty)}" aria-pressed="${difficulty === chosen}"><strong>${escapeHTML(difficulty)}</strong><span>${counts[difficulty]} available</span></button>`).join('')}</div><div class="dialog-actions"><button id="start-game" class="primary">Start puzzle</button></div>`, opener);
  sheetContent.querySelectorAll('[data-difficulty]').forEach((button) => button.addEventListener('click', () => {
    chosen = button.dataset.difficulty;
    sheetContent.querySelectorAll('[data-difficulty]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
  }));
  $('#start-game').addEventListener('click', () => {
    const puzzle = pickPuzzle(chosen);
    if (!puzzle) return;
    persist();
    startGame(puzzle);
    closeSheet();
    cells[game.state.selectedCell].focus({ preventScroll: true });
    announce(`New ${puzzle.difficulty} puzzle. ${puzzle.clues} clues.`);
  });
}

function replay(puzzle) {
  startGame(puzzle, { fresh: true });
  closeSheet();
  cells[game.state.selectedCell].focus({ preventScroll: true });
  announce('Puzzle restarted.');
}

function showRestart() {
  openSheet('Start again?', '<p>Your entries, notes, time, and counts will be reset. You’ll keep the same puzzle.</p><div class="dialog-actions"><button id="cancel-restart" class="secondary">Keep playing</button><button id="confirm-restart" class="primary">Restart puzzle</button></div>');
  $('#cancel-restart').addEventListener('click', closeSheet);
  $('#confirm-restart').addEventListener('click', () => {
    game.restart(); hintedCell = -1; completionShown = false;
    render(); persist(); closeSheet(); announce('Puzzle restarted.');
  });
}

function updateSettings(patch) {
  game.updateSettings(patch);
  if (!saveSettings(game.state.settings)) storageAvailable = false;
  render(); persist();
}
function showSettings() {
  const current = game.state.settings;
  openSheet('Make yourself comfortable', `<fieldset class="setting-group"><legend>Appearance</legend><div class="segmented">${['system', 'light', 'dark'].map((theme) => `<button data-theme-choice="${theme}" aria-pressed="${current.theme === theme}">${theme[0].toUpperCase() + theme.slice(1)}</button>`).join('')}</div></fieldset><fieldset class="setting-group"><legend>Check mistakes</legend><div class="segmented">${[['immediate', 'Immediately'], ['completion', 'When full'], ['off', 'Off']].map(([mode, label]) => `<button data-error-mode="${mode}" aria-pressed="${current.errorMode === mode}">${label}</button>`).join('')}</div><p class="small-print">Correctly completing the puzzle is recognized in every mode.</p></fieldset><div class="setting-toggle"><div><strong>Auto-remove notes</strong><p class="small-print">Clear matching notes in the row, column, and box when you enter a number.</p></div><button id="auto-notes" role="switch" aria-label="Auto-remove notes" aria-checked="${current.autoRemoveNotes}">${current.autoRemoveNotes ? 'On' : 'Off'}</button></div>`);
  sheetContent.querySelectorAll('[data-theme-choice]').forEach((button) => button.addEventListener('click', () => {
    updateSettings({ theme: button.dataset.themeChoice });
    sheetContent.querySelectorAll('[data-theme-choice]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
  }));
  sheetContent.querySelectorAll('[data-error-mode]').forEach((button) => button.addEventListener('click', () => {
    updateSettings({ errorMode: button.dataset.errorMode });
    sheetContent.querySelectorAll('[data-error-mode]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
  }));
  $('#auto-notes').addEventListener('click', (event) => {
    updateSettings({ autoRemoveNotes: !game.state.settings.autoRemoveNotes });
    event.currentTarget.setAttribute('aria-checked', String(game.state.settings.autoRemoveNotes));
    event.currentTarget.textContent = game.state.settings.autoRemoveNotes ? 'On' : 'Off';
  });
}

function showDetails(event) {
  const puzzle = game.state.puzzle;
  const certification = isRecord(puzzle.certification) ? puzzle.certification : {};
  const numeric = (value) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
  const text = (value) => typeof value === 'string' && value ? value : null;
  const hardest = hardestStep(certification);
  const rating = numeric(puzzle.rating);
  const rows = [
    ['Puzzle ID', puzzle.id],
    ['Difficulty', puzzle.difficulty],
    ['Certification', certificationLabel(puzzle)],
    ['Clues', puzzle.clues],
    ['Rating (project scale)', rating === null ? null : rating.toFixed(rating % 1 ? 2 : 0)],
    ['Certified tier', text(certification.requiredTier)],
    ['Hardest step in certified path', hardest ? `${hardest.technique} (${hardest.rating})` : null],
    ['Genuine bottlenecks', numeric(certification.genuineBottlenecks)],
    ['Certification version', text(certification.version)],
    ['App version', appVersion],
  ].filter(([, value]) => value != null);
  const techniques = Object.entries(isRecord(puzzle.techniques) ? puzzle.techniques : {}).filter(([, count]) => Number.isInteger(count) && count > 0);
  const techniquesHTML = techniques.length ? `<h3>Techniques in the certified path</h3><ul class="techniques">${techniques.map(([name, count]) => `<li>${escapeHTML(name)} <span class="small-print">× ${escapeHTML(count)}</span></li>`).join('')}</ul>` : '';
  const note = certificationLabel(puzzle) ? `<p lang="ru" class="certification-note">${MESSAGES.certificationNote}</p><p class="small-print">Rating is the Extreme Sudoku project's internal scale.</p>` : '';
  openSheet('Puzzle Details', `${note}<dl class="details">${rows.map(([key, value]) => `<div><dt>${escapeHTML(key)}</dt><dd>${escapeHTML(value)}</dd></div>`).join('')}</dl>${techniquesHTML}`, event?.currentTarget);
}

function showHint(event) {
  let index = game.state.selectedCell;
  const canReveal = (i) => game.state.puzzle.puzzle[i] === '0' && game.state.values[i] !== Number(game.state.puzzle.solution[i]);
  if (!canReveal(index)) index = game.state.values.findIndex((_, i) => canReveal(i));
  if (index < 0) return;
  openSheet('A little help?', `<p>Reveal the correct number in <strong>${coordinate(index)}</strong>?</p><p class="small-print">This is a basic reveal, not a logical technique hint. It counts as one hint and can be undone.</p><div class="dialog-actions"><button id="cancel-hint" class="secondary">Keep thinking</button><button id="confirm-hint" class="primary">Reveal one cell</button></div>`, event?.currentTarget);
  $('#cancel-hint').addEventListener('click', closeSheet);
  $('#confirm-hint').addEventListener('click', () => {
    closeSheet();
    game.select(index);
    hintedCell = index;
    act(() => game.reveal(index));
    if (game.state.status !== 'completed') announce(`${coordinate(index)} revealed: ${game.state.values[index]}. One hint used.`);
  });
}

function showCompletion() {
  const { puzzle, mistakes, hintsUsed } = game.state;
  const label = certificationLabel(puzzle) ?? puzzle.difficulty;
  openSheet('Solved!', `<div class="result-mark" aria-hidden="true">✓</div><p class="result-summary"><strong>${escapeHTML(label)}</strong><br>${puzzle.clues} clues</p><div class="result-stats"><div><strong>${timeString(game.elapsedSeconds())}</strong><span>Time</span></div><div><strong>${mistakes}</strong><span>Mistakes</span></div><div><strong>${hintsUsed}</strong><span>Hints</span></div></div><div class="dialog-actions"><button id="result-details" class="secondary">Puzzle Details</button><button id="result-new" class="primary">${puzzles.length > 1 ? 'New Game' : 'Available Puzzles'}</button></div><div class="dialog-actions"><button id="result-restart" class="secondary">Restart</button></div>`);
  $('#result-new').addEventListener('click', showNewGame);
  $('#result-details').addEventListener('click', (event) => { reopenCompletion = true; showDetails(event); });
  $('#result-restart').addEventListener('click', showRestart);
}

function showHelp() {
  openSheet('One rule. Many possibilities.', '<p>Fill every row, column, and 3 × 3 box with the numbers 1–9, without repeating a number.</p><p>Select a cell, then use the number pad. Original clues have a heavier weight; your entries appear in green. Use Notes to pencil in candidates.</p><dl class="details"><div><dt>Enter a number</dt><dd>1–9</dd></div><div><dt>Move between cells</dt><dd>Arrow keys</dd></div><div><dt>Toggle notes</dt><dd>N</dd></div><div><dt>Erase</dt><dd>Delete / Backspace / 0</dd></div><div><dt>Undo</dt><dd>Ctrl / ⌘ + Z</dd></div><div><dt>Close a dialog</dt><dd>Escape</dd></div></dl><p class="small-print">Your game saves automatically on this device. Use the pause button when you take a break.</p>');
}

$('#menu-button').addEventListener('click', showMenu);
$('#desktop-new').addEventListener('click', showNewGame);
$('#cert-badge').addEventListener('click', showDetails);
$('#notes-button').addEventListener('click', () => { act(() => game.toggleNotes()); announce(game.state.notesMode ? 'Notes on' : 'Notes off'); });
$('#undo-button').addEventListener('click', () => { act(() => game.undo()); announce('Last move undone.'); });
$('#erase-button').addEventListener('click', () => act(() => game.erase()));
$('#hint-button').addEventListener('click', showHint);
$('#pause-button').addEventListener('click', () => act(() => game.state.status === 'paused' ? game.resume() : game.pause()));
$('#resume-button').addEventListener('click', () => { act(() => game.resume()); cells[game.state.selectedCell].focus({ preventScroll: true }); });
document.addEventListener('keydown', (event) => {
  if (!game || sheet.open || game.state.status !== 'playing' || event.altKey || event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
  const key = event.key.toLowerCase();
  if ((event.ctrlKey || event.metaKey) && key === 'z' && !event.shiftKey) { event.preventDefault(); act(() => game.undo()); return; }
  if (event.ctrlKey || event.metaKey) return;
  if (/^[1-9]$/.test(key)) { event.preventDefault(); act(() => game.input(Number(key))); }
  else if (['backspace', 'delete', '0'].includes(key)) { event.preventDefault(); act(() => game.erase()); }
  else if (key === 'n') { event.preventDefault(); act(() => game.toggleNotes()); }
  else if (['arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(key)) {
    event.preventDefault();
    const index = game.state.selectedCell;
    let row = Math.floor(index / 9), column = index % 9;
    if (key === 'arrowup') row = Math.max(0, row - 1);
    if (key === 'arrowdown') row = Math.min(8, row + 1);
    if (key === 'arrowleft') column = Math.max(0, column - 1);
    if (key === 'arrowright') column = Math.min(8, column + 1);
    game.select(row * 9 + column);
    render(); persist();
    cells[game.state.selectedCell].focus({ preventScroll: true });
  }
});

function showLoadMessage(message, { retry = false } = {}) {
  $('#game').hidden = true;
  $('#load-state').hidden = false;
  $('#load-state').innerHTML = `<p lang="ru" class="load-message">${message}</p>${retry ? '<button id="retry-loading" class="primary" lang="ru">Попробовать снова</button>' : ''}`;
  if (retry) $('#retry-loading').addEventListener('click', start);
}

const puzzleDatabaseUrl = () => new URL($('meta[name="puzzle-database"]').content, document.baseURI);

async function loadAppVersion() {
  // web/package.json is the single source of the version; failing to read it only hides the label.
  try {
    const response = await fetch(new URL('./package.json', import.meta.url));
    const version = response.ok ? (await response.json()).version : null;
    if (typeof version === 'string') appVersion = version;
  } catch { /* cosmetic */ }
}

async function start() {
  $('#load-state').hidden = false;
  $('#load-state').innerHTML = '<span class="loading-dot"></span><p lang="ru">Загрузка…</p>';
  try {
    mark('json-start');
    [puzzles] = await Promise.all([loadProductionPuzzles(puzzleDatabaseUrl()), loadAppVersion()]);
    mark('json-end');
    if (!puzzles.length) {
      showLoadMessage(MESSAGES.noPuzzles);
      return;
    }
    reconcileStorage(puzzles.map((puzzle) => puzzle.id));
    const solved = solvedIds();
    const active = puzzles.find((puzzle) => puzzle.id === activePuzzleId());
    const unsolved = puzzles.filter((puzzle) => !solved.has(puzzle.id));
    const pool = unsolved.length ? unsolved : puzzles;
    game = undefined;
    startGame(active || pool[Math.floor(Math.random() * pool.length)]);
    $('#load-state').hidden = true;
    $('#game').hidden = false;
    $('#menu-button').disabled = false;
    mark('first-render');
    if (completionShown) showCompletion();
  } catch (error) {
    console.error('Puzzle database loading failed:', error);
    showLoadMessage(MESSAGES.loadFailed, { retry: true });
  }
}

const updateTimer = () => { if (game) $('#timer').textContent = timeString(game.elapsedSeconds()); };
// Time comes from timestamps (see SudokuGame), so these ticks only repaint; throttled timers cannot skew it.
setInterval(updateTimer, 1000);
setInterval(persist, 10000);
// The timer keeps running while the page is hidden (wall clock); these hooks only flush the save and repaint.
function onVisibility() { persist(); updateTimer(); }
document.addEventListener('visibilitychange', onVisibility);
window.addEventListener('pagehide', persist);
window.addEventListener('pageshow', updateTimer);
// Long press on the board must not open the iOS callout / context menu.
$('#board').addEventListener('contextmenu', (event) => event.preventDefault());
start();
