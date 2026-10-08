/** Pure game state. No DOM, generation, solver or difficulty analysis. */
export const DEFAULT_SETTINGS = Object.freeze({
  autoRemoveNotes: true,
  errorMode: 'immediate',
  theme: 'system',
});

export function normalizeSettings(settings = {}) {
  return {
    autoRemoveNotes: typeof settings?.autoRemoveNotes === 'boolean' ? settings.autoRemoveNotes : true,
    errorMode: ['immediate', 'completion', 'off'].includes(settings?.errorMode) ? settings.errorMode : 'immediate',
    theme: ['system', 'light', 'dark'].includes(settings?.theme) ? settings.theme : 'system',
  };
}

export function arePeers(a, b) {
  if (a === b) return false;
  const ar = Math.floor(a / 9), br = Math.floor(b / 9);
  const ac = a % 9, bc = b % 9;
  return ar === br || ac === bc || (Math.floor(ar / 3) === Math.floor(br / 3) && Math.floor(ac / 3) === Math.floor(bc / 3));
}

const isIndex = value => Number.isInteger(value) && value >= 0 && value < 81;
const counter = value => Number.isSafeInteger(value) && value >= 0 ? value : 0;
const cloneNotes = notes => notes.map(cell => [...cell]);

export function validBoard(values, notes, puzzle) {
  return Array.isArray(values) && values.length === 81 &&
    values.every((value, index) => Number.isInteger(value) && value >= 0 && value <= 9 &&
      (puzzle[index] === '0' || value === Number(puzzle[index]))) &&
    Array.isArray(notes) && notes.length === 81 &&
    notes.every((cell, index) => Array.isArray(cell) && cell.length <= 9 &&
      new Set(cell).size === cell.length && cell.every(value => Number.isInteger(value) && value >= 1 && value <= 9) &&
      (values[index] === 0 || cell.length === 0));
}

export class SudokuGame {
  constructor(puzzle, { saved = null, settings = {}, now = Date.now } = {}) {
    this.now = now;
    this.state = {
      puzzle,
      values: [...puzzle.puzzle].map(Number),
      notes: Array.from({ length: 81 }, () => []),
      selectedCell: Math.max(0, puzzle.puzzle.indexOf('0')),
      notesMode: false,
      elapsedMs: 0,
      startedAt: now(),
      status: 'playing',
      mistakes: 0,
      hintsUsed: 0,
      hintsKnown: true,
      attemptId: globalThis.crypto?.randomUUID?.() ?? `attempt-${now()}-${Math.random().toString(36).slice(2)}`,
      timingMode: 'active-v1',
      attemptStartedAt: now(),
      completedAt: null,
      restartedAttempt: null,
      errorModesUsed: [normalizeSettings(settings).errorMode],
      autoNotesUsed: normalizeSettings(settings).autoRemoveNotes,
      history: [],
      settings: normalizeSettings(settings),
    };
    this.restore(saved);
  }

  restore(saved) {
    const state = this.state;
    if (!saved || saved.version !== 1 || saved.puzzleId !== state.puzzle.id ||
      saved.puzzleFingerprint !== state.puzzle.puzzle ||
      !validBoard(saved.values, saved.notes, state.puzzle.puzzle)) return;
    state.values = [...saved.values];
    state.notes = cloneNotes(saved.notes).map(notes => notes.sort((a, b) => a - b));
    state.selectedCell = isIndex(saved.selectedCell) ? saved.selectedCell : state.selectedCell;
    state.notesMode = saved.notesMode === true;
    state.mistakes = counter(saved.mistakes);
    state.hintsUsed = counter(saved.hintsUsed);
    state.hintsKnown = saved.hintsKnown !== false && Number.isSafeInteger(saved.hintsUsed) && saved.hintsUsed >= 0;
    state.elapsedMs = counter(saved.elapsedMs);
    const solved = state.values.join('') === state.puzzle.solution;
    state.status = solved ? 'completed' : 'paused';
    // Reloads never charge offline time; restored games require an explicit Resume.
    state.startedAt = null;
    state.attemptId = typeof saved.attemptId === 'string' && saved.attemptId ? saved.attemptId : `legacy:${state.puzzle.id}:${state.puzzle.puzzle}`;
    state.timingMode = saved.timingMode === 'active-v1' ? 'active-v1' : 'legacy-mixed';
    state.attemptStartedAt = Number.isFinite(saved.attemptStartedAt) ? saved.attemptStartedAt : null;
    state.completedAt = Number.isFinite(saved.completedAt) ? saved.completedAt : null;
    state.restartedAttempt = saved.restartedAttempt && typeof saved.restartedAttempt === 'object' ? { ...saved.restartedAttempt } : null;
    state.errorModesUsed = Array.isArray(saved.errorModesUsed) ? [...new Set(saved.errorModesUsed.filter(mode => ['immediate', 'completion', 'off'].includes(mode)))] : [];
    state.autoNotesUsed = typeof saved.autoNotesUsed === 'boolean' ? saved.autoNotesUsed : null;
    state.history = Array.isArray(saved.history) ? saved.history.slice(-200)
      .filter(item => item && validBoard(item.values, item.notes, state.puzzle.puzzle))
      .map(item => ({ values: [...item.values], notes: cloneNotes(item.notes), selectedCell: isIndex(item.selectedCell) ? item.selectedCell : state.selectedCell })) : [];
  }

  elapsedSeconds() {
    return Math.floor(this.elapsedMilliseconds() / 1000);
  }

  elapsedMilliseconds() {
    const state = this.state, current = this.now();
    // The system clock moved backwards: absorb the jump so elapsed time never shrinks (it just pauses for that moment).
    if (this.lastSeen != null && current < this.lastSeen && state.startedAt != null) state.startedAt -= this.lastSeen - current;
    this.lastSeen = current;
    return state.elapsedMs + (state.status === 'playing' && state.startedAt != null ? Math.max(0, current - state.startedAt) : 0);
  }

  snapshot() {
    const state = this.state;
    return {
      version: 1, puzzleId: state.puzzle.id, puzzleFingerprint: state.puzzle.puzzle,
      values: [...state.values], notes: cloneNotes(state.notes),
      selectedCell: state.selectedCell, notesMode: state.notesMode,
      elapsedMs: Math.floor(this.elapsedMilliseconds()), savedAt: this.now(),
      status: state.status, mistakes: state.mistakes, hintsUsed: state.hintsUsed, hintsKnown: state.hintsKnown,
      attemptId: state.attemptId, timingMode: state.timingMode, attemptStartedAt: state.attemptStartedAt,
      completedAt: state.completedAt, errorModesUsed: [...state.errorModesUsed], autoNotesUsed: state.autoNotesUsed,
      restartedAttempt: state.restartedAttempt,
      difficulty: state.puzzle.difficulty,
      history: state.history.slice(-100).map(item => ({ ...item, values: [...item.values], notes: cloneNotes(item.notes) })),
    };
  }

  select(index) {
    if (!isIndex(index) || index === this.state.selectedCell || this.state.status === 'paused') return false;
    this.state.selectedCell = index;
    return true;
  }

  editable(index = this.state.selectedCell) {
    return this.state.status === 'playing' && isIndex(index) && this.state.puzzle.puzzle[index] === '0';
  }

  record() {
    const state = this.state;
    state.history.push({ values: [...state.values], notes: cloneNotes(state.notes), selectedCell: state.selectedCell });
    if (state.history.length > 200) state.history.shift();
  }

  input(digit) {
    const state = this.state, index = state.selectedCell;
    if (!this.editable() || !Number.isInteger(digit) || digit < 1 || digit > 9) return false;
    if (state.notesMode) {
      if (state.values[index] !== 0) return false;
      this.record();
      state.notes[index] = state.notes[index].includes(digit)
        ? state.notes[index].filter(note => note !== digit)
        : [...state.notes[index], digit].sort((a, b) => a - b);
      return true;
    }
    if (state.values[index] === digit) return false;
    this.record();
    this.place(index, digit);
    if (state.settings.errorMode === 'immediate' && digit !== Number(state.puzzle.solution[index])) state.mistakes++;
    this.checkCompletion();
    return true;
  }

  place(index, digit) {
    const state = this.state;
    state.values[index] = digit;
    state.notes[index] = [];
    if (state.settings.autoRemoveNotes) {
      state.notes.forEach((notes, peer) => {
        if (arePeers(index, peer)) state.notes[peer] = notes.filter(note => note !== digit);
      });
    }
  }

  checkCompletion() {
    const state = this.state;
    if (state.values.some(value => value === 0)) return;
    if (state.values.join('') === state.puzzle.solution) {
      state.elapsedMs = this.elapsedMilliseconds();
      state.startedAt = null;
      state.status = 'completed';
      state.completedAt = this.now();
    } else if (state.settings.errorMode === 'completion') {
      state.mistakes++;
    }
  }

  erase() {
    const state = this.state, index = state.selectedCell;
    if (!this.editable() || (!state.values[index] && state.notes[index].length === 0)) return false;
    this.record();
    state.values[index] = 0;
    state.notes[index] = [];
    return true;
  }

  undo() {
    const state = this.state;
    if (state.status !== 'playing' || state.history.length === 0) return false;
    const previous = state.history.pop();
    state.values = previous.values;
    state.notes = previous.notes;
    state.selectedCell = previous.selectedCell;
    // Mistakes and hints are lifetime counters for this attempt, not board state.
    return true;
  }

  toggleNotes() {
    if (this.state.status !== 'playing') return false;
    this.state.notesMode = !this.state.notesMode;
    return true;
  }

  reveal(index = this.state.selectedCell) {
    if (!this.editable(index) || this.state.values[index] === Number(this.state.puzzle.solution[index])) return false;
    this.record();
    this.state.selectedCell = index;
    this.place(index, Number(this.state.puzzle.solution[index]));
    this.state.hintsUsed++;
    this.checkCompletion();
    return true;
  }

  pause() {
    if (this.state.status !== 'playing') return false;
    this.state.elapsedMs = this.elapsedMilliseconds();
    this.state.startedAt = null;
    this.state.status = 'paused';
    return true;
  }

  resume() {
    if (this.state.status !== 'paused') return false;
    this.state.startedAt = this.now();
    this.lastSeen = this.state.startedAt;
    this.state.status = 'playing';
    this.updateSettings({}); // Global settings may have changed while another puzzle was open.
    return true;
  }

  restart() {
    if (this.state.status === 'completed') return false;
    const { puzzle, settings } = this.state;
    this.state = new SudokuGame(puzzle, { settings, now: this.now }).state;
    this.lastSeen = this.state.startedAt;
    return true;
  }

  updateSettings(patch) {
    this.state.settings = normalizeSettings({ ...this.state.settings, ...patch });
    if (this.state.status !== 'completed') {
      if (!this.state.errorModesUsed.includes(this.state.settings.errorMode)) this.state.errorModesUsed.push(this.state.settings.errorMode);
      if (this.state.settings.autoRemoveNotes) this.state.autoNotesUsed = true;
    }
    return true;
  }
}
