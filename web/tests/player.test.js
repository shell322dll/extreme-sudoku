import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { SudokuGame } from '../lib/game.js';
import { STORAGE_KEYS, normalizeProfile, saveProfile, loadProfile, PREPARATIONS, saveGame, loadSave,
  loadActivity, startedPuzzleIds, migratePlayerData, playerStatistics, archiveAttempt, reconcileStorage, restartSummary } from '../lib/storage.js';
import { nextPuzzle } from '../lib/selection.js';

const { puzzles } = JSON.parse(await readFile(new URL('./fixtures/production_multi.json', import.meta.url), 'utf8'));
const [A, B] = puzzles;
function memoryStorage(run) {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  const memory = new Map();
  const storage = { getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, String(value)), removeItem: key => memory.delete(key) };
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage });
  try { return run(memory, storage); }
  finally { if (descriptor) Object.defineProperty(globalThis, 'localStorage', descriptor); else delete globalThis.localStorage; }
}
const solve = game => {
  game.resume();
  if (game.state.notesMode) game.toggleNotes();
  for (let i = 0; i < 81; i++) if (game.state.puzzle.puzzle[i] === '0') {
    game.select(i); game.input(Number(game.state.puzzle.solution[i]));
  }
  return game;
};
function oldSnapshot(puzzle, completed = false) {
  const game = new SudokuGame(puzzle, { now: () => 100 });
  if (completed) solve(game);
  else { game.toggleNotes(); game.input(3); }
  const snapshot = game.snapshot();
  for (const key of ['attemptId', 'timingMode', 'attemptStartedAt', 'completedAt', 'errorModesUsed', 'autoNotesUsed', 'hintsKnown', 'difficulty']) delete snapshot[key];
  snapshot.elapsedMs = 123456;
  snapshot.savedAt = 100;
  return snapshot;
}

test('profile requires trimmed 1–32 code points and preparation; rename keeps gameplay intact', () => memoryStorage(() => {
  assert.equal(normalizeProfile({ name: '  ', preparation: 'beginner' }), null);
  assert.equal(normalizeProfile({ name: 'a'.repeat(33), preparation: 'expert' }), null);
  assert.equal(normalizeProfile({ name: 'Ada', preparation: 'other' }), null);
  assert.equal(normalizeProfile({ name: '😀'.repeat(32), preparation: 'expert' }).name.length, 64);
  saveGame(new SudokuGame(A).snapshot());
  assert.equal(saveProfile({ name: ' Ada ', preparation: 'experienced' }), true);
  assert.deepEqual(loadProfile(), { version: 1, name: 'Ada', preparation: 'experienced' });
  assert.equal(PREPARATIONS[loadProfile().preparation], 'Hard');
  saveProfile({ name: 'Grace', preparation: 'expert' });
  assert.equal(loadSave(A.id).puzzleId, A.id);
  assert.ok(startedPuzzleIds().includes(A.id));
}));

test('migration preserves old notes, selection, undo and elapsed; restores paused with legacy timing', () => memoryStorage(memory => {
  const original = oldSnapshot(A);
  memory.set(STORAGE_KEYS.game, JSON.stringify({ storageSchemaVersion: 2, activePuzzleId: A.id, games: { [A.id]: original } }));
  memory.set(STORAGE_KEYS.recent, JSON.stringify(['older-solved-id']));
  assert.equal(migratePlayerData(puzzles), true);
  const migrated = loadSave(A.id);
  for (const key of ['values', 'notes', 'history', 'selectedCell', 'mistakes', 'hintsUsed', 'elapsedMs']) assert.deepEqual(migrated[key], original[key], key);
  assert.equal(migrated.status, 'paused');
  assert.equal(migrated.timingMode, 'legacy-mixed');
  assert.equal(migrated.completedAt, null);
  assert.deepEqual(new Set(startedPuzzleIds()), new Set([A.id, 'older-solved-id']));
  const restored = new SudokuGame(A, { saved: migrated, now: () => 99999999 });
  assert.equal(restored.elapsedMilliseconds(), 123456);
  restored.resume(); solve(restored); saveGame(restored.snapshot());
  assert.equal(playerStatistics().solved, 2);
  assert.equal(Object.keys(playerStatistics().records).length, 0);
}));

test('old completed result is imported once without invented completion date or assistance settings', () => memoryStorage(memory => {
  memory.set(STORAGE_KEYS.legacyGame, JSON.stringify(oldSnapshot(A, true)));
  assert.equal(migratePlayerData(puzzles), true);
  assert.equal(migratePlayerData(puzzles), true);
  const result = playerStatistics().history[0];
  assert.equal(playerStatistics().completed, 1);
  assert.equal(result.completedAt, null);
  assert.deepEqual(result.errorModesUsed, []);
  assert.equal(result.autoNotesUsed, null);
  assert.equal(Object.keys(playerStatistics().records).length, 0);
  assert.equal(memory.has(STORAGE_KEYS.legacyGame), false);
}));

test('failed migration retains legacy source and retry does not duplicate results', () => memoryStorage((memory, storage) => {
  memory.set(STORAGE_KEYS.legacyGame, JSON.stringify(oldSnapshot(A, true)));
  const write = storage.setItem;
  storage.setItem = (key, value) => { if (key === STORAGE_KEYS.game) throw new Error('Quota'); write(key, value); };
  assert.equal(migratePlayerData(puzzles), false);
  assert.equal(memory.has(STORAGE_KEYS.legacyGame), true);
  storage.setItem = write;
  assert.equal(migratePlayerData(puzzles), true);
  assert.equal(playerStatistics().completed, 1);
}));

test('permanent seen survives old save cleanup, large history and an unavailable/reintroduced puzzle', () => memoryStorage(memory => {
  const snapshot = new SudokuGame(A).snapshot(); snapshot.savedAt = 1;
  saveGame(snapshot);
  const activity = loadActivity();
  activity.seen.push(...Array.from({ length: 1100 }, (_, i) => `seen-${i}`));
  memory.set(STORAGE_KEYS.activity, JSON.stringify(activity));
  reconcileStorage([B.id], 100 * 24 * 60 * 60 * 1000);
  assert.equal(loadSave(A.id), null);
  assert.equal(startedPuzzleIds().length, 1101);
  assert.equal(nextPuzzle([A], { started: startedPuzzleIds() }), null);
}));

test('completion is idempotent; reveal undone still counts; restart gets a distinct attempt', () => memoryStorage(() => {
  const game = new SudokuGame(A);
  game.reveal(); game.undo();
  saveGame(game.snapshot());
  const previous = game.snapshot();
  archiveAttempt(previous);
  game.restart();
  assert.notEqual(game.state.attemptId, previous.attemptId);
  assert.equal(game.state.timingMode, 'active-v1');
  solve(game);
  saveGame(game.snapshot()); saveGame(game.snapshot());
  migratePlayerData(puzzles);
  const stats = playerStatistics();
  assert.equal(stats.completed, 1);
  assert.equal(stats.noReveal, 1);
  assert.equal(stats.history.find(result => result.status === 'restarted').hintsUsed, 1);
  assert.equal(Object.keys(stats.records).length, 1);
  assert.equal(game.restart(), false);
  assert.equal(nextPuzzle([A], { started: startedPuzzleIds() }), null);
}));

test('mixed assistance is retained across restoration and excluded from comparable records', () => memoryStorage(() => {
  const first = new SudokuGame(A, { settings: { errorMode: 'off', autoRemoveNotes: false } });
  const restored = new SudokuGame(A, { saved: first.snapshot(), settings: { errorMode: 'immediate' } });
  restored.resume(); solve(restored); saveGame(restored.snapshot());
  const result = playerStatistics().history[0];
  assert.deepEqual(result.errorModesUsed, ['off', 'immediate']);
  assert.equal(result.autoNotesUsed, true);
  assert.equal(Object.keys(playerStatistics().records).length, 0);
}));

test('partially damaged activity remains readable without false timing records', () => memoryStorage(memory => {
  memory.set(STORAGE_KEYS.activity, JSON.stringify({ seen: [A.id, null, A.id], results: {
    broken: null,
    missing: { puzzleId: A.id, status: 'completed', timingMode: 'active-v1', elapsedMs: 1 },
    strange: { puzzleId: B.id, status: 'completed', hintsUsed: -1, mistakes: '0', errorModesUsed: ['invalid', 'off'], autoNotesUsed: 'yes' },
  } }));
  assert.doesNotThrow(playerStatistics);
  const stats = playerStatistics();
  assert.equal(stats.noReveal, 0);
  assert.equal(Object.keys(stats.records).length, 0);
  assert.deepEqual(loadActivity().seen, [A.id]);
}));

test('restart failure preserves the old attempt; interrupted history write is repaired from committed progress', () => memoryStorage((memory, storage) => {
  const old = new SudokuGame(A);
  old.reveal(); old.pause(); saveGame(old.snapshot());
  const replacement = new SudokuGame(A);
  replacement.state.restartedAttempt = restartSummary(old.snapshot());
  const write = storage.setItem;
  storage.setItem = (key, value) => { if (key === STORAGE_KEYS.game) throw new Error('Quota'); write(key, value); };
  assert.equal(saveGame(replacement.snapshot()), false);
  assert.equal(loadSave(A.id).attemptId, old.state.attemptId);
  assert.equal(playerStatistics().history.length, 0);
  storage.setItem = (key, value) => { if (key === STORAGE_KEYS.activity) throw new Error('Blocked'); write(key, value); };
  assert.equal(saveGame(replacement.snapshot()), false);
  assert.equal(loadSave(A.id).attemptId, replacement.state.attemptId);
  storage.setItem = write;
  assert.equal(migratePlayerData(puzzles), true);
  assert.equal(playerStatistics().history[0].status, 'restarted');
  assert.equal(playerStatistics().history[0].hintsUsed, 1);
  const resumed = new SudokuGame(A, { saved: loadSave(A.id) });
  solve(resumed); saveGame(resumed.snapshot());
  assert.equal(playerStatistics().completed, 1);
  assert.equal(playerStatistics().history.length, 2);
}));

test('system clock moving backwards during pause or restart does not add phantom active time', () => {
  let now = 1000;
  const game = new SudokuGame(A, { now: () => now });
  now = 2000; game.pause();
  assert.equal(game.elapsedMilliseconds(), 1000);
  now = 1000; game.resume();
  assert.equal(game.elapsedMilliseconds(), 1000);
  now = 1500;
  assert.equal(game.elapsedMilliseconds(), 1500);
  now = 500; game.restart();
  assert.equal(game.elapsedMilliseconds(), 0);
});
