import { SudokuGame } from './lib/game.js';
import { loadProductionPuzzles, certificationLabel, hardestStep, DIFFICULTIES } from './lib/data.js';
import { loadSave, saveGame, loadSettings, saveSettings, startedPuzzleIds, loadProfile, saveProfile, normalizeProfile, PREPARATIONS, migratePlayerData, savedGames, playerStatistics, restartSummary } from './lib/storage.js';
import { nextPuzzle } from './lib/selection.js';

const MESSAGES = Object.freeze({
  loadFailed: 'Не удалось загрузить базу Sudoku. Попробуйте обновить страницу.',
  noPuzzles: 'Сейчас нет доступных проверенных Sudoku.',
  allPlayed: 'Все доступные Sudoku этой сложности уже сыграны. Можно решить задачу ещё раз.',
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
let settings = loadSettings();
let writer = false;
let lockPending = false;
let lockAbort;
let releaseWriter;
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
function storageFailure() {
  storageAvailable = false;
  $('#storage-warning').hidden = false;
  $('#storage-warning').textContent = 'Progress could not be saved. Keep this tab open and allow site storage. New games and restarts are unavailable until saving works.';
}
function persist() {
  clearTimeout(persistTimer);
  if (!writer || !game) return false;
  storageAvailable = saveGame(game.snapshot());
  if (!storageAvailable) storageFailure();
  else $('#storage-warning').hidden = true;
  $('#save-status').textContent = storageAvailable ? 'Saved on this device' : 'Progress cannot be saved';
  return storageAvailable;
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
  if (!writer || !game || !action()) return;
  render();
  persist();
  if (game.state.status === 'completed' && !completionShown) {
    completionShown = true;
    announce('Puzzle solved!');
    showCompletion();
  }
}

function openSheet(title, content, opener) {
  if (!sheet.open) {
    const active = opener || document.activeElement;
    // Safari touch activation does not necessarily focus the pressed button.
    sheetReturnFocus = active && active !== document.body && active !== document.documentElement ? active : game ? cells[game.state.selectedCell] : $('#home-button');
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
  openSheet('Game', `<div class="menu-list"><button data-menu="home">My games & profile</button><button data-menu="new">New Game <span aria-hidden="true">↗</span></button><button data-menu="stats">Statistics & history</button>${game ? `${game.state.status !== 'completed' ? '<button data-menu="restart">Restart this puzzle</button>' : ''}<button data-menu="settings">Settings</button><button data-menu="details">Puzzle Details</button>` : ''}<button data-menu="help">How to play & keyboard</button></div>`, event?.currentTarget);
  sheetContent.querySelectorAll('[data-menu]').forEach((button) => button.addEventListener('click', () => ({ home: showHome, new: showNewGame, stats: showStatistics, restart: showRestart, settings: showSettings, details: showDetails, help: showHelp })[button.dataset.menu]()));
}

const pickPuzzle = (difficulty = null) => nextPuzzle(puzzles, { currentId: game?.state.puzzle.id ?? null, started: startedPuzzleIds(), difficulty });

function startGame(puzzle, { fresh = false, restartedAttempt = null } = {}) {
  if (!writer || !loadProfile()) return false;
  if (game) { game.pause(); if (!persist()) return false; }
  const candidate = new SudokuGame(puzzle, { saved: fresh ? null : loadSave(puzzle.id), settings: loadSettings() });
  if (restartedAttempt) candidate.state.restartedAttempt = restartSummary(restartedAttempt);
  if (!fresh && !loadSave(puzzle.id)) return false;
  if (document.hidden) candidate.pause();
  if (!saveGame(candidate.snapshot())) {
    storageFailure();
    // A committed board is authoritative even if its secondary history write failed.
    // Its embedded restart summary lets the next save/migration repair the history.
    if (loadSave(puzzle.id)?.attemptId !== candidate.state.attemptId) return false;
    candidate.pause();
  }
  game = candidate;
  hintedCell = -1;
  completionShown = game.state.status === 'completed';
  $('#home').hidden = true;
  $('#game').hidden = false;
  $('#home-button').hidden = false;
  render();
  closeSheet();
  if (completionShown) showCompletion();
  return true;
}

function showNewGame(event) {
  if (!writer || !loadProfile()) return;
  if (game) { game.pause(); render(); persist(); }
  const seen = new Set(startedPuzzleIds());
  const remaining = puzzles.filter(puzzle => !seen.has(puzzle.id));
  const offered = DIFFICULTIES.filter((difficulty) => puzzles.some((puzzle) => puzzle.difficulty === difficulty));
  const counts = Object.fromEntries(DIFFICULTIES.map((difficulty) => [difficulty, remaining.filter((puzzle) => puzzle.difficulty === difficulty).length]));
  const recommended = PREPARATIONS[loadProfile().preparation];
  let chosen = offered.includes(recommended) ? recommended : offered[0];
  openSheet('New Game', `<p>Recommended for your preparation: <strong>${escapeHTML(recommended)}</strong>. You can choose any available level.</p><p class="small-print">Only puzzles you have never started appear here. Your unfinished games stay saved.</p><div class="difficulty-list">${offered.map((difficulty) => `<button class="difficulty-choice" data-difficulty="${escapeHTML(difficulty)}" aria-pressed="${difficulty === chosen}"><strong>${escapeHTML(difficulty)}</strong><span>${counts[difficulty]} new</span></button>`).join('')}</div><p id="exhausted-message" role="status"></p><div class="dialog-actions"><button id="continue-games" class="secondary">My unfinished games</button><button id="start-game" class="primary">Start puzzle</button></div>`, event?.currentTarget);
  const refresh = () => {
    $('#start-game').disabled = !counts[chosen];
    $('#exhausted-message').textContent = counts[chosen] ? '' : 'No new puzzles at this level yet. Choose another level or continue an unfinished game.';
  };
  refresh();
  $('#continue-games').addEventListener('click', showHome);
  sheetContent.querySelectorAll('[data-difficulty]').forEach((button) => button.addEventListener('click', () => {
    chosen = button.dataset.difficulty;
    sheetContent.querySelectorAll('[data-difficulty]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
    refresh();
  }));
  $('#start-game').addEventListener('click', () => {
    const choice = pickPuzzle(chosen);
    if (!choice) return;
    if (startGame(choice.puzzle, { fresh: true })) {
      cells[game.state.selectedCell].focus({ preventScroll: true });
      announce(`New ${choice.puzzle.difficulty} puzzle. ${choice.puzzle.clues} clues.`);
    }
  });
}

function showRestart() {
  if (!writer || !game || game.state.status === 'completed') return;
  game.pause(); render(); persist();
  openSheet('Start again?', '<p>This unfinished attempt will be archived. A new attempt of the same puzzle starts with empty entries, notes and time. The puzzle remains used and cannot appear as a new game.</p><div class="dialog-actions"><button id="cancel-restart" class="secondary">Keep playing</button><button id="confirm-restart" class="primary">Restart puzzle</button></div>');
  $('#cancel-restart').addEventListener('click', closeSheet);
  $('#confirm-restart').addEventListener('click', () => {
    if (!writer || !persist()) { storageFailure(); return; }
    if (startGame(game.state.puzzle, { fresh: true, restartedAttempt: game.snapshot() })) announce('New attempt started.');
  });
}

function profileForm(profile = null) {
  const labels = { beginner: 'Beginner', amateur: 'Amateur', experienced: 'Experienced', expert: 'Expert' };
  return `<form id="profile-form" class="profile-form"><label for="player-name">Your name</label><input id="player-name" name="name" autocomplete="nickname" maxlength="64" required value="${escapeHTML(profile?.name ?? '')}" aria-describedby="profile-note"><label for="player-preparation">Sudoku preparation</label><select id="player-preparation" name="preparation" required><option value="">Choose your preparation</option>${Object.entries(labels).map(([value, label]) => `<option value="${value}" ${profile?.preparation === value ? 'selected' : ''}>${label} · recommended ${PREPARATIONS[value]}</option>`).join('')}</select><p id="profile-note" class="small-print">Use 1–32 characters for your name. Preparation suggests a starting level; every available level remains open.</p><p class="small-print">One profile, saved only in this browser. Clearing site data removes your profile, games and results. There is no account or sync between devices.</p><p id="profile-error" role="alert"></p><button id="save-profile" class="primary" type="submit">${profile ? 'Save profile' : 'Save and choose a puzzle'}</button></form>`;
}

function bindProfileForm() {
  $('#profile-form').addEventListener('submit', event => {
    event.preventDefault();
    if (!writer) return;
    const profile = normalizeProfile({ name: $('#player-name').value, preparation: $('#player-preparation').value });
    if (!profile) { $('#profile-error').textContent = 'Enter a name of 1–32 characters and choose your preparation.'; return; }
    if (!saveProfile(profile)) { $('#profile-error').textContent = 'Your profile could not be saved. Allow storage for this site and try again.'; return; }
    showHome();
  });
}

function showProfile() {
  if (game) { game.pause(); render(); persist(); }
  openSheet('Your profile', profileForm(loadProfile()));
  bindProfileForm();
  $('#player-name').focus();
}

function showHome() {
  if (!writer) return;
  reopenCompletion = false;
  if (game) { game.pause(); render(); persist(); }
  closeSheet();
  $('#game').hidden = true;
  $('#load-state').hidden = true;
  $('#home').hidden = false;
  $('#home-button').hidden = true;
  const profile = loadProfile();
  $('#menu-button').disabled = !profile;
  if (!profile) {
    $('#home').innerHTML = `<span class="eyebrow">YOUR PLACE TO THINK</span><h2>Welcome to Extreme Sudoku</h2><p>Create your local player profile before your first puzzle.</p>${profileForm()}`;
    bindProfileForm();
    return;
  }
  const saves = savedGames().filter(saved => saved.status !== 'completed');
  const stats = playerStatistics();
  $('#home').innerHTML = `<div class="home-heading"><div><span class="eyebrow">YOUR SUDOKU SPACE</span><h2>Hello, ${escapeHTML(profile.name)}</h2></div><button id="edit-profile" class="secondary">Edit profile</button></div><p class="small-print">${escapeHTML(profile.preparation)} · recommended ${PREPARATIONS[profile.preparation]}. Your progress stays in this browser.</p><div class="home-actions"><button id="home-new" class="primary">New Game</button><button id="home-stats" class="secondary">Statistics & history · ${stats.solved} solved</button></div><h3>Unfinished games</h3><p class="small-print">Opening a saved game keeps it paused until you press Resume.</p><div class="saved-list">${saves.length ? saves.map(saved => {
    const puzzle = puzzles.find(item => item.id === saved.puzzleId);
    return `<div class="saved-card"><div><strong>${escapeHTML(puzzle?.difficulty ?? saved.difficulty ?? 'Unavailable puzzle')}</strong><p>${escapeHTML(saved.puzzleId)}</p><span class="small-print">${timeString((saved.elapsedMs ?? 0) / 1000)}${saved.timingMode !== 'active-v1' ? ' · includes legacy time' : ' active time'}</span></div><button class="secondary" data-continue="${escapeHTML(saved.puzzleId)}" ${puzzle ? '' : 'disabled'}>${puzzle ? 'Continue' : 'Unavailable'}</button></div>`;
  }).join('') : '<p>No unfinished games. Choose a new puzzle when you are ready.</p>'}</div>`;
  $('#edit-profile').addEventListener('click', showProfile);
  $('#home-new').addEventListener('click', showNewGame);
  $('#home-stats').addEventListener('click', showStatistics);
  $('#home').querySelectorAll('[data-continue]').forEach(button => button.addEventListener('click', () => {
    const puzzle = puzzles.find(item => item.id === button.dataset.continue);
    if (puzzle) startGame(puzzle);
  }));
}

const modeLabel = mode => ({ immediate: 'Immediate checks', completion: 'Check when full', off: 'Checks off' })[mode] ?? 'Unknown checks';
function showStatistics() {
  if (game) { game.pause(); render(); persist(); }
  const stats = playerStatistics();
  const history = [...stats.history].sort((a, b) => (b.completedAt ?? 0) - (a.completedAt ?? 0));
  const date = value => Number.isFinite(value) ? new Date(value).toLocaleString() : 'Date unknown';
  const resultTime = value => Number.isFinite(value) ? timeString(value / 1000) : 'Unknown';
  const recordRows = Object.values(stats.records).map(result => `<tr><td>${escapeHTML(result.difficulty)}<small>${result.hintsUsed === 0 ? 'No reveals' : 'With reveals'} · ${modeLabel(result.errorModesUsed[0])} · ${result.autoNotesUsed ? 'auto notes' : 'manual notes'}</small></td><td>${resultTime(result.elapsedMs)}</td></tr>`).join('');
  const levels = DIFFICULTIES.map(difficulty => {
    const completed = history.filter(result => result.status === 'completed' && result.difficulty === difficulty);
    if (!completed.length) return '';
    const active = completed.filter(result => result.timingMode === 'active-v1' && Number.isFinite(result.elapsedMs));
    return `<tr><td>${escapeHTML(difficulty)}</td><td>${completed.length}</td><td>${active.length ? resultTime(active.reduce((sum, result) => sum + result.elapsedMs, 0) / active.length) : '—'}</td></tr>`;
  }).join('');
  openSheet('Statistics & history', `<div class="result-stats"><div><strong>${stats.solved}</strong><span>Unique puzzles solved</span></div><div><strong>${stats.noReveal}</strong><span>Completions without reveals</span></div><div><strong>${stats.inProgress}</strong><span>Unfinished</span></div></div><p class="small-print">${stats.completed} recorded completions. ${stats.legacyUnknown ? `${stats.legacyUnknown} older solved puzzle(s) have no detailed result. ` : ''}A reveal remains counted even after Undo.</p>${levels ? `<h3>By difficulty</h3><table class="history-table"><thead><tr><th>Level</th><th>Completed</th><th>Mean active time</th></tr></thead><tbody>${levels}</tbody></table>` : ''}<h3>Personal time records</h3><p class="small-print">Active time only. Records are separated by reveals, error-check mode and automatic notes. Mixed check modes and legacy timing are excluded. Mean times above include all assistance settings.</p>${recordRows ? `<table class="history-table"><thead><tr><th>Playing conditions</th><th>Best time</th></tr></thead><tbody>${recordRows}</tbody></table>` : '<p>No comparable active-time records yet.</p>'}<h3>Attempt history</h3><div class="history-list">${history.length ? history.map(result => `<article class="history-card"><strong>${escapeHTML(result.difficulty ?? 'Unknown level')} · ${result.status === 'completed' ? 'Solved' : 'Restarted'}</strong><p>${escapeHTML(result.puzzleId)}</p><p>${escapeHTML(date(result.completedAt))} · ${resultTime(result.elapsedMs)}${result.timingMode !== 'active-v1' ? ' (legacy / mixed time)' : ' active time'}</p><p class="small-print">Reveals: ${result.hintsUsed ?? 'unknown'} · Error counter: ${result.mistakes ?? 'unknown'}<br>${result.errorModesUsed.length ? result.errorModesUsed.map(modeLabel).join(' → ') : 'Earlier check modes unknown'} · Auto notes: ${result.autoNotesUsed == null ? 'unknown' : result.autoNotesUsed ? 'used' : 'off'}</p></article>`).join('') : '<p>Your completed attempts will appear here.</p>'}</div><p class="small-print">Error counters depend on check mode. Zero with checks off does not mean an error-free solution. All results are local to this browser.</p>`);
}

function updateSettings(patch) {
  if (!writer) return;
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
  const verification = isRecord(puzzle.verification) ? puzzle.verification : {};
  const certified = Boolean(certificationLabel(puzzle));
  const numeric = (value) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
  const text = (value) => typeof value === 'string' && value ? value : null;
  const hardest = hardestStep(certification);
  const rating = numeric(puzzle.rating);
  const rows = [
    ['Puzzle ID', puzzle.id],
    ['Difficulty', puzzle.difficulty],
    ['Certification', certificationLabel(puzzle)],
    ['Verification', verification.status === 'VERIFIED' ? 'Verified logical solution' : null],
    ['Clues', puzzle.clues],
    ['Rating (project scale)', rating === null ? null : rating.toFixed(rating % 1 ? 2 : 0)],
    ['Certified tier', text(certification.requiredTier)],
    ['Hardest step in certified path', hardest ? `${hardest.technique} (${hardest.rating})` : null],
    ['Hardest technique in verified path', certified ? null : text(puzzle.hardestTechnique)],
    ['Solution steps', certified ? null : numeric(puzzle.solutionSteps)],
    ['Genuine bottlenecks', numeric(certification.genuineBottlenecks)],
    ['Certification version', text(certification.version)],
    ['App version', appVersion],
  ].filter(([, value]) => value != null);
  const techniques = Object.entries(isRecord(puzzle.techniques) ? puzzle.techniques : {}).filter(([, count]) => Number.isInteger(count) && count > 0);
  const techniquesHTML = techniques.length ? `<h3>Techniques in the ${certified ? 'certified' : 'verified'} path</h3><ul class="techniques">${techniques.map(([name, count]) => `<li>${escapeHTML(name)} <span class="small-print">× ${escapeHTML(count)}</span></li>`).join('')}</ul>` : '';
  const note = `${certified ? `<p lang="ru" class="certification-note">${MESSAGES.certificationNote}</p>` : '<p>Verified unique solution, logical solving and deterministic replay.</p>'}<p class="small-print">Rating is the Extreme Sudoku project's internal scale.</p>`;
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
  openSheet('Solved!', `<div class="result-mark" aria-hidden="true">✓</div><p class="result-summary"><strong>${escapeHTML(label)}</strong><br>${puzzle.clues} clues</p><div class="result-stats"><div><strong>${timeString(game.elapsedSeconds())}</strong><span>${game.state.timingMode === 'active-v1' ? 'Active time' : 'Legacy / mixed time'}</span></div><div><strong>${mistakes}</strong><span>Error counter</span></div><div><strong>${game.state.hintsKnown ? hintsUsed : '?'}</strong><span>Reveals</span></div></div><p class="small-print">${game.state.errorModesUsed.length ? game.state.errorModesUsed.map(modeLabel).join(' → ') : 'Earlier checks unknown'}. Error counts depend on the check mode.</p><div class="dialog-actions"><button id="result-details" class="secondary">Puzzle Details</button><button id="result-new" class="primary">New Game</button></div><div class="dialog-actions"><button id="result-stats" class="secondary">Statistics & history</button><button id="result-home" class="secondary">My games</button></div>`);
  $('#result-new').addEventListener('click', showNewGame);
  $('#result-details').addEventListener('click', (event) => { reopenCompletion = true; showDetails(event); });
  $('#result-stats').addEventListener('click', showStatistics);
  $('#result-home').addEventListener('click', showHome);
}

function showHelp() {
  openSheet('One rule. Many possibilities.', '<p>Fill every row, column, and 3 × 3 box with the numbers 1–9, without repeating a number.</p><p>Select a cell, then use the number pad. Original clues have a heavier weight; your entries appear in green. Use Notes to pencil in candidates.</p><dl class="details"><div><dt>Enter a number</dt><dd>1–9</dd></div><div><dt>Move between cells</dt><dd>Arrow keys</dd></div><div><dt>Toggle notes</dt><dd>N</dd></div><div><dt>Erase</dt><dd>Delete / Backspace / 0</dd></div><div><dt>Undo</dt><dd>Ctrl / ⌘ + Z</dd></div><div><dt>Close a dialog</dt><dd>Escape</dd></div></dl><p class="small-print">Your game saves automatically on this device. Use the pause button when you take a break.</p>');
}

$('#menu-button').addEventListener('click', showMenu);
$('#home-button').addEventListener('click', showHome);
$('#desktop-new').addEventListener('click', showNewGame);
$('#cert-badge').addEventListener('click', showDetails);
$('#notes-button').addEventListener('click', () => { act(() => game.toggleNotes()); announce(game.state.notesMode ? 'Notes on' : 'Notes off'); });
$('#undo-button').addEventListener('click', () => { act(() => game.undo()); announce('Last move undone.'); });
$('#erase-button').addEventListener('click', () => act(() => game.erase()));
$('#hint-button').addEventListener('click', showHint);
$('#pause-button').addEventListener('click', () => act(() => game.state.status === 'paused' ? game.resume() : game.pause()));
$('#resume-button').addEventListener('click', () => { act(() => game.resume()); cells[game.state.selectedCell].focus({ preventScroll: true }); });
document.addEventListener('keydown', (event) => {
  if (!writer || !game || sheet.open || game.state.status !== 'playing' || event.altKey || event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
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
  $('#home').hidden = true;
  $('#home-button').hidden = true;
  $('#menu-button').disabled = true;
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
  if (!writer) return;
  $('#load-state').hidden = false;
  $('#load-state').innerHTML = '<span class="loading-dot"></span><p lang="ru">Загрузка…</p>';
  try {
    mark('json-start');
    [puzzles] = await Promise.all([loadProductionPuzzles(puzzleDatabaseUrl()), loadAppVersion()]);
    if (!writer) return;
    mark('json-end');
    if (!puzzles.length) {
      showLoadMessage(MESSAGES.noPuzzles);
      return;
    }
    settings = loadSettings();
    game = undefined;
    if (!migratePlayerData(puzzles)) {
      showLoadMessage('Не удалось сохранить данные. Разрешите хранилище для сайта и повторите попытку. Старые сохранения не удалены.', { retry: true });
      return;
    }
    storageAvailable = true;
    $('#storage-warning').hidden = true;
    showHome();
    mark('first-render');
  } catch (error) {
    console.error('Puzzle database loading failed:', error);
    showLoadMessage(MESSAGES.loadFailed, { retry: true });
  }
}

const updateTimer = () => { if (game) $('#timer').textContent = timeString(game.elapsedSeconds()); };
// Time comes from timestamps (see SudokuGame), so these ticks only repaint; throttled timers cannot skew it.
setInterval(updateTimer, 1000);
setInterval(persist, 10000);
function pauseForLeave() {
  if (!writer || !game) return;
  game.pause(); render(); persist();
}
function onVisibility() { if (document.hidden) pauseForLeave(); updateTimer(); }
document.addEventListener('visibilitychange', onVisibility);
window.addEventListener('pagehide', () => {
  pauseForLeave();
  writer = false;
  lockAbort?.abort();
  releaseWriter?.();
});
window.addEventListener('pageshow', event => { if (event.persisted) acquireWriter(); updateTimer(); });
// Long press on the board must not open the iOS callout / context menu.
$('#board').addEventListener('contextmenu', (event) => event.preventDefault());
async function acquireWriter() {
  if (writer || lockPending) return;
  if (!navigator.locks?.request) {
    showLoadMessage('Для безопасного сохранения нужен современный браузер с Web Locks и защищённое соединение HTTPS. Обновите браузер или откройте HTTPS-адрес сайта.');
    return;
  }
  lockPending = true;
  lockAbort = new AbortController();
  showLoadMessage('Ожидание доступа к профилю. Если игра открыта в другой вкладке, закройте её. Эта вкладка пока ничего не сохраняет.');
  try {
    await navigator.locks.request('extreme-sudoku.player.v1', { signal: lockAbort.signal }, async () => {
      lockPending = false;
      writer = true;
      const held = new Promise(resolve => { releaseWriter = resolve; });
      await start(); // Re-read all saved data only after acquiring ownership.
      await held;
      releaseWriter = undefined;
    });
  } catch (error) {
    if (error.name !== 'AbortError') showLoadMessage('Не удалось получить безопасный доступ к профилю. Закройте другие вкладки игры и обновите страницу.');
  } finally {
    lockPending = false;
  }
}
acquireWriter();
