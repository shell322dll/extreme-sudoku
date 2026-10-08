import { normalizeSettings, SudokuGame, validBoard } from './game.js';

/** Version of the stored progress container (not of a single game snapshot). */
export const STORAGE_SCHEMA_VERSION = 2;
export const STORAGE_KEYS = Object.freeze({
  game: 'extreme-sudoku.progress.v2',
  legacyGame: 'extreme-sudoku.game.v1',
  settings: 'extreme-sudoku.settings.v1',
  recent: 'extreme-sudoku.recent.v1',
  profile: 'extreme-sudoku.profile.v1',
  activity: 'extreme-sudoku.activity.v1',
});
const MAX_RECENT = 1000;
const STALE_SAVE_MS = 90 * 24 * 60 * 60 * 1000;

const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);

function read(key) {
  try {
    const value = globalThis.localStorage?.getItem(key);
    return value ? JSON.parse(value) : null;
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    if (!globalThis.localStorage) return false;
    globalThis.localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

function remove(key) {
  try { globalThis.localStorage?.removeItem(key); } catch { /* storage may be blocked */ }
}

/**
 * Progress container: { storageSchemaVersion: 2, activePuzzleId, games: { [puzzleId]: snapshot } }.
 * Anything else (corrupt JSON, other versions, wrong shapes) reads as an empty container.
 */
// Parsed-store cache keyed by the exact stored string: a tap re-parses only if another tab/tool changed the value.
let cache = { raw: undefined, store: null };
function readStore() {
  let raw = null;
  try { raw = globalThis.localStorage?.getItem(STORAGE_KEYS.game) ?? null; } catch { raw = null; }
  if (cache.raw === raw && cache.store && raw !== null) return cache.store;
  const store = parseStore(raw);
  cache = { raw, store: raw === null ? null : store };
  return store;
}

function writeStore(store) {
  try {
    if (!globalThis.localStorage) return false;
    const raw = JSON.stringify(store);
    globalThis.localStorage.setItem(STORAGE_KEYS.game, raw);
    cache = { raw, store };
    return true;
  } catch {
    cache = { raw: undefined, store: null };
    return false;
  }
}

function parseStore(raw) {
  let store = null;
  try { store = raw ? JSON.parse(raw) : null; } catch { store = null; }
  if (!isRecord(store) || store.storageSchemaVersion !== STORAGE_SCHEMA_VERSION || !isRecord(store.games)) {
    return { storageSchemaVersion: STORAGE_SCHEMA_VERSION, activePuzzleId: null, games: {} };
  }
  const games = {};
  for (const [id, snapshot] of Object.entries(store.games)) if (isRecord(snapshot) && snapshot.puzzleId === id) games[id] = snapshot;
  return { storageSchemaVersion: STORAGE_SCHEMA_VERSION, activePuzzleId: typeof store.activePuzzleId === 'string' ? store.activePuzzleId : null, games };
}

/** Saved progress of one puzzle; without an ID, of the puzzle that was active last. */
export function loadSave(puzzleId) {
  const store = readStore();
  const id = puzzleId ?? store.activePuzzleId;
  return typeof id === 'string' ? store.games[id] ?? null : null;
}

export function activePuzzleId() {
  return readStore().activePuzzleId;
}

/** Store a snapshot under its own puzzle ID (other puzzles keep their progress) and mark it active. */
export function saveGame(snapshot) {
  if (!isRecord(snapshot) || typeof snapshot.puzzleId !== 'string') return false;
  const store = readStore();
  store.games[snapshot.puzzleId] = snapshot;
  store.activePuzzleId = snapshot.puzzleId;
  if (!writeStore(store)) return false;
  const activity = loadActivity();
  activity.seen = [...new Set([...activity.seen, snapshot.puzzleId])];
  if (isRecord(snapshot.restartedAttempt)) addResult(activity, snapshot.restartedAttempt);
  if (snapshot.status === 'completed') addResult(activity, snapshot);
  return write(STORAGE_KEYS.activity, activity);
}

/** IDs of every puzzle with saved progress on this device (in progress or completed). */
export function startedPuzzleIds() {
  return [...new Set([...Object.keys(readStore().games), ...loadActivity().seen, ...loadRecent()])];
}

export function setActivePuzzle(puzzleId) {
  const store = readStore();
  store.activePuzzleId = typeof puzzleId === 'string' ? puzzleId : null;
  return writeStore(store);
}

/**
 * Once the current database is known: adopt a pre-0.1 single-slot save, then delete that legacy key.
 * Saves of puzzles missing from the database are KEPT (a bad deploy must not erase progress); only saves
 * untouched for 90 days are discarded, and never when the database is empty.
 */
export function reconcileStorage(knownIds, now = Date.now()) {
  const known = new Set(knownIds);
  if (known.size === 0) return;
  const store = readStore();
  const legacy = read(STORAGE_KEYS.legacyGame);
  let changed = false;
  if (isRecord(legacy) && typeof legacy.puzzleId === 'string' && !store.games[legacy.puzzleId]) {
    store.games[legacy.puzzleId] = legacy;
    store.activePuzzleId ??= legacy.puzzleId;
    changed = true;
  }
  // Preserve permanent seen IDs before any old, unavailable progress is discarded.
  const activity = loadActivity();
  activity.seen = [...new Set([...activity.seen, ...Object.keys(store.games), ...loadRecent()])];
  if (!write(STORAGE_KEYS.activity, activity)) return false;
  for (const [id, snapshot] of Object.entries(store.games)) {
    if (!known.has(id) && Number.isFinite(snapshot.savedAt) && now - snapshot.savedAt > STALE_SAVE_MS) { delete store.games[id]; changed = true; }
  }
  if (store.activePuzzleId && !store.games[store.activePuzzleId]) { store.activePuzzleId = null; changed = true; }
  if (!changed || writeStore(store)) { remove(STORAGE_KEYS.legacyGame); return true; }
  return false;
}

export const loadSettings = () => normalizeSettings(read(STORAGE_KEYS.settings));
export const saveSettings = settings => write(STORAGE_KEYS.settings, normalizeSettings(settings));

export function loadRecent() {
  const recent = read(STORAGE_KEYS.recent);
  return Array.isArray(recent) ? [...new Set(recent.filter(id => typeof id === 'string'))].slice(0, MAX_RECENT) : [];
}

export function rememberPuzzle(id) {
  if (typeof id !== 'string') return false;
  return write(STORAGE_KEYS.recent, [id, ...loadRecent().filter(existing => existing !== id)].slice(0, MAX_RECENT));
}

export const PREPARATIONS = Object.freeze({ beginner: 'Easy', amateur: 'Medium', experienced: 'Hard', expert: 'Expert' });
export function normalizeProfile(value) {
  if (!isRecord(value) || typeof value.name !== 'string' || !Object.hasOwn(PREPARATIONS, value.preparation)) return null;
  const name = value.name.trim();
  if ([...name].length < 1 || [...name].length > 32) return null;
  return { version: 1, name, preparation: value.preparation };
}
export const loadProfile = () => normalizeProfile(read(STORAGE_KEYS.profile));
export function saveProfile(value) {
  const profile = normalizeProfile(value);
  return Boolean(profile) && write(STORAGE_KEYS.profile, profile);
}

export function loadActivity() {
  const raw = read(STORAGE_KEYS.activity);
  const results = {};
  for (const [id, value] of Object.entries(isRecord(raw?.results) ? raw.results : {})) {
    if (!isRecord(value) || typeof value.puzzleId !== 'string' || !['completed', 'restarted'].includes(value.status)) continue;
    const count = number => Number.isSafeInteger(number) && number >= 0 ? number : null;
    Object.defineProperty(results, id, { enumerable: true, configurable: true, writable: true, value: {
      attemptId: id, puzzleId: value.puzzleId, status: value.status,
      difficulty: typeof value.difficulty === 'string' ? value.difficulty : null,
      completedAt: count(value.completedAt), elapsedMs: count(value.elapsedMs),
      hintsUsed: count(value.hintsUsed), mistakes: count(value.mistakes),
      errorModesUsed: Array.isArray(value.errorModesUsed) ? [...new Set(value.errorModesUsed.filter(mode => ['immediate', 'completion', 'off'].includes(mode)))] : [],
      autoNotesUsed: typeof value.autoNotesUsed === 'boolean' ? value.autoNotesUsed : null,
      timingMode: value.timingMode === 'active-v1' ? 'active-v1' : 'legacy-mixed',
    } });
  }
  return {
    version: 1,
    seen: Array.isArray(raw?.seen) ? [...new Set(raw.seen.filter(id => typeof id === 'string'))] : [],
    results,
    legacySolved: Array.isArray(raw?.legacySolved) ? [...new Set(raw.legacySolved.filter(id => typeof id === 'string'))] : [],
  };
}

function addResult(activity, snapshot) {
  if (typeof snapshot.attemptId !== 'string' || typeof snapshot.puzzleId !== 'string') return;
  const previous = activity.results[snapshot.attemptId];
  if (Object.hasOwn(activity.results, snapshot.attemptId) && (previous.status === 'completed' || snapshot.status !== 'completed')) return;
  const result = {
    attemptId: snapshot.attemptId, puzzleId: snapshot.puzzleId, difficulty: snapshot.difficulty ?? null,
    status: snapshot.status, completedAt: snapshot.completedAt ?? null,
    elapsedMs: Number.isFinite(snapshot.elapsedMs) ? snapshot.elapsedMs : null,
    hintsUsed: snapshot.hintsKnown === false ? null : Number.isSafeInteger(snapshot.hintsUsed) ? snapshot.hintsUsed : null,
    mistakes: Number.isSafeInteger(snapshot.mistakes) ? snapshot.mistakes : null,
    errorModesUsed: Array.isArray(snapshot.errorModesUsed) ? [...snapshot.errorModesUsed] : [],
    autoNotesUsed: snapshot.autoNotesUsed ?? null,
    timingMode: snapshot.timingMode === 'active-v1' ? 'active-v1' : 'legacy-mixed',
  };
  Object.defineProperty(activity.results, snapshot.attemptId, { value: result, enumerable: true, configurable: true, writable: true });
}

export function archiveAttempt(snapshot) {
  const activity = loadActivity();
  addResult(activity, { ...snapshot, status: 'restarted', completedAt: null });
  return write(STORAGE_KEYS.activity, activity);
}

export function restartSummary(snapshot) {
  const activity = { results: {} };
  addResult(activity, { ...snapshot, status: 'restarted', completedAt: null });
  return activity.results[snapshot.attemptId];
}

/** Run only under the application's single-writer lock. Never invent old dates or assistance history. */
export function migratePlayerData(puzzles) {
  const store = readStore(), activity = loadActivity();
  const legacy = read(STORAGE_KEYS.legacyGame);
  if (isRecord(legacy) && typeof legacy.puzzleId === 'string' && !store.games[legacy.puzzleId]) {
    store.games[legacy.puzzleId] = legacy;
    store.activePuzzleId ??= legacy.puzzleId;
  }
  const known = new Map(puzzles.map(puzzle => [puzzle.id, puzzle]));
  activity.seen = [...new Set([...activity.seen, ...Object.keys(store.games), ...loadRecent()])];
  activity.legacySolved = [...new Set([...activity.legacySolved, ...loadRecent()])];
  for (const [id, saved] of Object.entries(store.games)) {
    const puzzle = known.get(id);
    if (!puzzle || saved.version !== 1 || saved.puzzleFingerprint !== puzzle.puzzle || !validBoard(saved.values, saved.notes, puzzle.puzzle)) continue;
    const restored = new SudokuGame(puzzle, { saved, settings: loadSettings() });
    const snapshot = restored.snapshot();
    store.games[id] = snapshot;
    if (isRecord(snapshot.restartedAttempt)) addResult(activity, snapshot.restartedAttempt);
    if (snapshot.status === 'completed') addResult(activity, snapshot);
  }
  // Both writes must succeed before the legacy source may be removed. A retry is idempotent.
  if (!write(STORAGE_KEYS.activity, activity) || !writeStore(store)) return false;
  remove(STORAGE_KEYS.legacyGame);
  return true;
}

export const savedGames = () => Object.values(readStore().games);

export function playerStatistics() {
  const activity = loadActivity();
  const history = Object.values(activity.results);
  const completed = history.filter(result => result.status === 'completed');
  const solved = new Set([...activity.legacySolved, ...completed.map(result => result.puzzleId)]);
  const records = {};
  for (const result of completed) {
    // Separate records by reveal assistance and error-check mode; mixed/unknown modes are not comparable.
    if (result.timingMode !== 'active-v1' || !Number.isFinite(result.elapsedMs) || result.errorModesUsed.length !== 1 || result.hintsUsed == null || result.autoNotesUsed == null) continue;
    const category = `${result.difficulty}|${result.hintsUsed === 0 ? 'no-reveal' : 'with-reveal'}|${result.errorModesUsed[0]}|${result.autoNotesUsed ? 'auto-notes' : 'manual-notes'}`;
    if (!records[category] || result.elapsedMs < records[category].elapsedMs) records[category] = result;
  }
  return { solved: solved.size, completed: completed.length, noReveal: completed.filter(result => result.hintsUsed === 0).length,
    inProgress: savedGames().filter(saved => saved.status !== 'completed').length,
    legacyUnknown: activity.legacySolved.filter(id => !completed.some(result => result.puzzleId === id)).length,
    history, records };
}
