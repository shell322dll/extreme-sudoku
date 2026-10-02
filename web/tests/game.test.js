import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { SudokuGame, arePeers } from '../lib/game.js';
import { parseDatabase, isValidPuzzle, loadPuzzles } from '../lib/data.js';
import { STORAGE_KEYS, loadSave, saveGame, loadSettings, saveSettings, loadRecent, rememberPuzzle } from '../lib/storage.js';

const database = JSON.parse(await readFile(new URL('../../data/puzzles.json', import.meta.url), 'utf8'));
const puzzle = database.puzzles[0];
const empty = [...puzzle.puzzle].flatMap((digit, index) => digit === '0' ? [index] : []);
const given = [...puzzle.puzzle].findIndex(digit => digit !== '0');
const correct = index => Number(puzzle.solution[index]);
const wrong = index => correct(index) % 9 + 1;

test('all current exported puzzles satisfy the frontend exchange contract', () => {
  assert.equal(parseDatabase(database).length, database.puzzles.length);
  assert.equal(database.puzzles.every(isValidPuzzle), true);
});

test('invalid or duplicate entries do not discard good entries; schema is enforced', () => {
  const warnings = [];
  const bad = { ...puzzle, id: 'bad', puzzle: '0'.repeat(80) };
  const parsed = parseDatabase({ schemaVersion: 1, puzzles: [bad, puzzle, puzzle] }, (...args) => warnings.push(args));
  assert.deepEqual(parsed, [puzzle]);
  assert.equal(warnings.length, 2);
  assert.throws(() => parseDatabase({ schemaVersion: 2, puzzles: [puzzle] }), /version/);
  assert.throws(() => parseDatabase({ schemaVersion: 1, puzzles: [] }), /playable/);
  assert.equal(isValidPuzzle({ ...puzzle, clues: 0 }), false);
  assert.equal(isValidPuzzle({ ...puzzle, difficulty: 'Impossible' }), false);
  assert.equal(isValidPuzzle({ ...puzzle, unique: false }), false);
  assert.equal(isValidPuzzle({ ...puzzle, solution: '1'.repeat(81) }), false);
  assert.equal(isValidPuzzle({ ...puzzle, futureMetadata: true }), true);
});

test('given cells cannot be overwritten, erased, annotated or revealed', () => {
  const game = new SudokuGame(puzzle);
  game.select(given);
  assert.equal(game.input(wrong(given)), false);
  assert.equal(game.erase(), false);
  assert.equal(game.reveal(), false);
  game.toggleNotes();
  assert.equal(game.input(1), false);
  assert.equal(game.state.values[given], correct(given));
  assert.equal(game.state.history.length, 0);
});

test('nine distinct notes toggle at stable candidate positions and undo atomically', () => {
  const game = new SudokuGame(puzzle);
  game.select(empty[0]);
  game.toggleNotes();
  for (let digit = 9; digit >= 1; digit--) assert.equal(game.input(digit), true);
  assert.deepEqual(game.state.notes[empty[0]], [1, 2, 3, 4, 5, 6, 7, 8, 9]);
  game.input(4);
  assert.equal(game.state.notes[empty[0]].includes(4), false);
  game.undo();
  assert.equal(game.state.notes[empty[0]].includes(4), true);
  game.erase();
  assert.deepEqual(game.state.notes[empty[0]], []);
  game.undo();
  assert.equal(game.state.notes[empty[0]].length, 9);
});

test('a value removes matching peer notes as one undo group, preserving unrelated notes', () => {
  const game = new SudokuGame(puzzle);
  const target = empty[0], peer = empty.find(index => arePeers(target, index));
  const unrelated = empty.find(index => index !== target && !arePeers(target, index));
  game.toggleNotes();
  for (const index of [target, peer, unrelated]) {
    game.select(index);
    game.input(correct(target));
  }
  game.toggleNotes();
  game.select(target);
  const before = game.snapshot();
  game.input(correct(target));
  assert.deepEqual(game.state.notes[target], []);
  assert.deepEqual(game.state.notes[peer], []);
  assert.deepEqual(game.state.notes[unrelated], [correct(target)]);
  assert.equal(game.state.history.length, before.history.length + 1);
  game.undo();
  assert.deepEqual(game.state.values, before.values);
  assert.deepEqual(game.state.notes, before.notes);
});

test('auto removal setting preserves peer candidates and notes cannot overwrite values', () => {
  const game = new SudokuGame(puzzle, { settings: { autoRemoveNotes: false } });
  const target = empty[0], peer = empty.find(index => arePeers(target, index));
  game.toggleNotes();
  game.select(peer);
  game.input(correct(target));
  game.toggleNotes();
  game.select(target);
  game.input(correct(target));
  assert.deepEqual(game.state.notes[peer], [correct(target)]);
  game.toggleNotes();
  assert.equal(game.input(2), false);
});

test('immediate mistakes count changed incorrect entries only and survive undo', () => {
  const game = new SudokuGame(puzzle);
  game.select(empty[0]);
  game.input(wrong(empty[0]));
  game.input(wrong(empty[0]));
  assert.equal(game.state.mistakes, 1);
  game.undo();
  assert.equal(game.state.mistakes, 1);
  assert.equal(game.state.values[empty[0]], 0);
  game.input(correct(empty[0]));
  assert.equal(game.state.mistakes, 1);
});

test('completion checking catches a wrong full board and off mode suppresses mistakes', () => {
  for (const errorMode of ['completion', 'off']) {
    const game = new SudokuGame(puzzle, { settings: { errorMode } });
    for (const index of empty) {
      game.select(index);
      game.input(index === empty[0] ? wrong(index) : correct(index));
    }
    assert.equal(game.state.status, 'playing');
    assert.equal(game.state.mistakes, errorMode === 'completion' ? 1 : 0);
    game.select(empty[0]);
    game.input(correct(empty[0]));
    assert.equal(game.state.status, 'completed');
  }
});

test('timer uses real time, explicit pause freezes it, restore adds the wall-clock time since the save', () => {
  let now = 100000;
  const game = new SudokuGame(puzzle, { now: () => now });
  now += 6500;
  assert.equal(game.elapsedSeconds(), 6);
  game.pause();
  now += 300000;
  assert.equal(game.elapsedSeconds(), 6);
  assert.equal(game.input(1), false);
  game.resume();
  now += 500;
  assert.equal(game.elapsedSeconds(), 7);
  const saved = game.snapshot();
  now += 60000;
  const restored = new SudokuGame(puzzle, { saved, now: () => now });
  assert.equal(restored.elapsedSeconds(), 67);
  now += 1000;
  assert.equal(restored.elapsedSeconds(), 68);
  restored.pause();
  const paused = new SudokuGame(puzzle, { saved: restored.snapshot(), now: () => now + 100000 });
  assert.equal(paused.state.status, 'paused');
  assert.equal(paused.elapsedSeconds(), 68);
});

test('correct completion freezes timer; undo reopens game; completed progress restores', () => {
  let now = 10000;
  const game = new SudokuGame(puzzle, { now: () => now });
  now += 9000;
  for (const index of empty) {
    game.select(index);
    game.input(correct(index));
  }
  assert.equal(game.state.status, 'completed');
  now += 100000;
  assert.equal(game.elapsedSeconds(), 9);
  assert.equal(game.erase(), false);
  const restored = new SudokuGame(puzzle, { saved: game.snapshot(), now: () => now });
  assert.equal(restored.state.status, 'completed');
  assert.equal(restored.elapsedSeconds(), 9);
  restored.undo();
  assert.equal(restored.state.status, 'playing');
  now += 1000;
  assert.equal(restored.elapsedSeconds(), 10);
});

test('restoration preserves notes, selection and history without allowing clue tampering', () => {
  const game = new SudokuGame(puzzle);
  game.select(empty[1]);
  game.toggleNotes();
  game.input(3);
  const saved = game.snapshot();
  const restored = new SudokuGame(puzzle, { saved });
  assert.equal(restored.state.selectedCell, empty[1]);
  assert.equal(restored.state.notesMode, true);
  assert.deepEqual(restored.state.notes[empty[1]], [3]);
  restored.undo();
  assert.deepEqual(restored.state.notes[empty[1]], []);
  saved.values[given] = 0;
  const tampered = new SudokuGame(puzzle, { saved });
  assert.equal(tampered.state.values[given], correct(given));
  assert.equal(tampered.state.history.length, 0);
});

test('foreign saves, malformed notes and malicious undo frames are rejected', () => {
  const game = new SudokuGame(puzzle);
  game.input(1);
  const saved = game.snapshot();
  assert.equal(new SudokuGame(puzzle, { saved: { ...saved, puzzleId: 'other' } }).state.history.length, 0);
  assert.equal(new SudokuGame(puzzle, { saved: { ...saved, puzzleFingerprint: 'changed' } }).state.history.length, 0);
  saved.history.push({ values: Array(81).fill(0), notes: Array.from({ length: 81 }, () => []) });
  const restored = new SudokuGame(puzzle, { saved });
  assert.equal(restored.state.history.length, 1);
  saved.notes[empty[1]] = [0, 10];
  assert.equal(new SudokuGame(puzzle, { saved }).state.history.length, 0);
});

test('hint reveals selected correct value, groups notes removal and tracks lifetime hints', () => {
  const game = new SudokuGame(puzzle);
  game.select(empty[0]);
  game.reveal();
  assert.equal(game.state.values[empty[0]], correct(empty[0]));
  assert.equal(game.state.hintsUsed, 1);
  assert.equal(game.reveal(), false);
  game.undo();
  assert.equal(game.state.values[empty[0]], 0);
  assert.equal(game.state.hintsUsed, 1);
  game.updateSettings({ theme: 'dark', autoRemoveNotes: false });
  game.restart();
  assert.equal(game.state.hintsUsed, 0);
  assert.equal(game.state.mistakes, 0);
  assert.equal(game.state.history.length, 0);
  assert.equal(game.state.settings.theme, 'dark');
  assert.equal(game.state.settings.autoRemoveNotes, false);
});

test('localStorage failures and malformed JSON do not interrupt gameplay', () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  const memory = new Map();
  try {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
      getItem: key => memory.get(key) ?? null,
      setItem: (key, value) => memory.set(key, value),
    } });
    const saved = new SudokuGame(puzzle).snapshot();
    assert.equal(saveGame(saved), true);
    assert.deepEqual(loadSave(), saved);
    saveSettings({ theme: 'dark', errorMode: 'off', autoRemoveNotes: false });
    assert.equal(loadSettings().theme, 'dark');
    rememberPuzzle('first'); rememberPuzzle('second'); rememberPuzzle('first');
    assert.deepEqual(loadRecent(), ['first', 'second']);
    memory.set(STORAGE_KEYS.game, '{broken');
    assert.equal(loadSave(), null);
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('Blocked'); } });
    assert.equal(saveGame(saved), false);
    assert.equal(loadSave(), null);
    assert.equal(loadSettings().theme, 'system');
  } finally {
    if (original) Object.defineProperty(globalThis, 'localStorage', original);
    else delete globalThis.localStorage;
  }
});

test('loader resolves data relative to a nested GitHub Pages project path', async () => {
  const originalFetch = globalThis.fetch, originalDocument = globalThis.document;
  try {
    globalThis.document = { baseURI: 'https://example.github.io/extreme-sudoku/web/' };
    let requested;
    globalThis.fetch = async url => { requested = url.href; return { ok: true, json: async () => database }; };
    assert.equal((await loadPuzzles()).length, database.puzzles.length);
    assert.equal(requested, 'https://example.github.io/extreme-sudoku/data/puzzles.json');
    globalThis.fetch = async () => ({ ok: false, status: 404 });
    await assert.rejects(loadPuzzles(), /404/);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
  }
});
