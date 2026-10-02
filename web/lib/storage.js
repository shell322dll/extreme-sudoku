import { normalizeSettings } from './game.js';

/** Version of the stored progress container (not of a single game snapshot). */
export const STORAGE_SCHEMA_VERSION = 2;
export const STORAGE_KEYS = Object.freeze({
  game: 'extreme-sudoku.progress.v2',
  legacyGame: 'extreme-sudoku.game.v1',
  settings: 'extreme-sudoku.settings.v1',
  recent: 'extreme-sudoku.recent.v1',
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
  return writeStore(store);
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
  for (const [id, snapshot] of Object.entries(store.games)) {
    if (!known.has(id) && Number.isFinite(snapshot.savedAt) && now - snapshot.savedAt > STALE_SAVE_MS) { delete store.games[id]; changed = true; }
  }
  if (store.activePuzzleId && !store.games[store.activePuzzleId]) { store.activePuzzleId = null; changed = true; }
  if (!changed || writeStore(store)) remove(STORAGE_KEYS.legacyGame);
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
