import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseProductionDatabase, certificationLabel, hardestStep } from '../lib/data.js';
import { nextPuzzle, startupPuzzle } from '../lib/selection.js';
import { SudokuGame } from '../lib/game.js';
import { STORAGE_KEYS, loadSave, saveGame, activePuzzleId, startedPuzzleIds, loadRecent, rememberPuzzle } from '../lib/storage.js';

// Compact multi-puzzle fixture: publish-style (slim) copies of certified records. Never production input.
const fixture = JSON.parse(await readFile(new URL('./fixtures/production_multi.json', import.meta.url), 'utf8'));
const quiet = () => {};
const puzzles = parseProductionDatabase(fixture, quiet);
const [A, B, C, D] = puzzles;
const ids = list => list.map(p => p.id);
const sequence = (...values) => { let i = 0; return () => values[i++ % values.length]; };
const RANDOMS = [0, 0.1, 0.25, 0.49, 0.5, 0.74, 0.75, 0.99, 0.999999999];

function memoryStorage() {
  const memory = new Map();
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, String(value)), removeItem: key => memory.delete(key) } });
  return memory;
}
const restoreStorage = () => delete globalThis.localStorage;
const solve = puzzle => {
  const game = new SudokuGame(puzzle);
  for (let i = 0; i < 81; i++) if (puzzle.puzzle[i] === '0') { game.select(i); game.input(Number(puzzle.solution[i])); }
  return game;
};

test('the multi-puzzle fixture loads several distinct certified puzzles; labels and details come from the data', () => {
  assert.equal(puzzles.length, 4);
  assert.equal(new Set(ids(puzzles)).size, 4);
  assert.ok(ids(puzzles).includes('puzzle-8e2b144cecb50551d96b'));
  for (const [i, puzzle] of puzzles.entries()) {
    const record = fixture.puzzles[i];
    assert.equal(certificationLabel(puzzle), 'Certified Extreme');
    assert.equal(puzzle.clues, record.clues);
    assert.equal(puzzle.rating, record.rating);
    assert.deepEqual(hardestStep(puzzle.certification), record.certification.hardestStep);
  }
  // Details differ per puzzle: they are read from each record, not recomputed or shared.
  assert.notDeepEqual([A.clues, A.certification.genuineBottlenecks], [D.clues, D.certification.genuineBottlenecks]);
  assert.notEqual(hardestStep(A.certification).technique, hardestStep(C.certification).technique);
  // The label follows the certification status only, never the rating.
  const relabeled = { ...C, id: 'ultra', difficulty: 'Ultra Extreme', certification: { ...C.certification, status: 'CERTIFIED_ULTRA_EXTREME' } };
  assert.equal(certificationLabel(relabeled), 'Certified Ultra Extreme');
  assert.equal(relabeled.rating, 30);
});

test('certified filtering is strict for a multi-puzzle database: uncertified, inconsistent and broken entries are dropped', () => {
  const warnings = [];
  const entries = [A, { ...B, id: 'prelim', certification: { ...B.certification, status: 'PRELIMINARY' } },
    { ...C, id: 'wrong-difficulty', difficulty: 'Ultra Extreme' }, { ...D, id: 'broken', clues: 99 }, null, B, A, C];
  const parsed = parseProductionDatabase({ ...fixture, puzzles: entries }, (...a) => warnings.push(a));
  assert.deepEqual(ids(parsed), [A.id, B.id, C.id]);
  assert.equal(warnings.length, 5);
});

test('New Game never repeats the current puzzle while alternatives exist (any random value)', () => {
  for (const current of puzzles) {
    for (const r of RANDOMS) {
      const choice = nextPuzzle(puzzles, { currentId: current.id, random: () => r });
      assert.notEqual(choice.puzzle.id, current.id);
      assert.equal(choice.replay, false);
    }
  }
  const two = nextPuzzle([A, B], { currentId: A.id, started: [A.id, B.id], random: () => 0.99 });
  assert.equal(two.puzzle.id, B.id);
});

test('random selection is injectable: same seed, same choice; different values reach different puzzles', () => {
  const pick = r => nextPuzzle(puzzles, { currentId: A.id, random: () => r }).puzzle.id;
  assert.equal(pick(0), B.id);
  assert.equal(pick(0.5), C.id);
  assert.equal(pick(0.99), D.id);
  assert.equal(pick(0.5), pick(0.5));
  assert.equal(startupPuzzle(puzzles, { random: () => 0 }).id, A.id);
  assert.equal(startupPuzzle(puzzles, { random: () => 0.99 }).id, D.id);
  // A misbehaving random source cannot break the choice.
  for (const bad of [NaN, -1, 1, 7, Infinity]) assert.ok(puzzles.includes(nextPuzzle(puzzles, { currentId: A.id, random: () => bad }).puzzle));
});

test('preference: unopened unsolved → in-progress unsolved → least recently solved replay', () => {
  // B is in progress, C and D were never opened: one of the unopened ones is chosen.
  for (const r of RANDOMS) assert.ok([C.id, D.id].includes(nextPuzzle(puzzles, { currentId: A.id, started: [A.id, B.id], random: () => r }).puzzle.id));
  // Everything opened: an unsolved one (in progress) is resumed rather than a solved one replayed.
  const resume = nextPuzzle(puzzles, { currentId: A.id, started: ids(puzzles), solved: [C.id, D.id] });
  assert.deepEqual([resume.puzzle.id, resume.replay], [B.id, false]);
  // All others solved: replay the one solved longest ago (recent list is most-recent first), never the just-solved one.
  const replay = nextPuzzle(puzzles, { currentId: A.id, started: ids(puzzles), solved: [A.id, D.id, B.id, C.id] });
  assert.deepEqual([replay.puzzle.id, replay.replay], [C.id, true]);
  const justSolved = nextPuzzle(puzzles, { currentId: D.id, solved: [D.id, A.id, B.id, C.id] });
  assert.equal(justSolved.puzzle.id, C.id);
});

test('repeated New Game walks through every puzzle before repeating one', () => {
  const started = [A.id];
  let current = A.id;
  const seen = [A.id];
  for (let step = 0; step < puzzles.length - 1; step++) {
    const { puzzle } = nextPuzzle(puzzles, { currentId: current, started, random: sequence(0.3, 0.8, 0.1)});
    assert.ok(!seen.includes(puzzle.id), `repeated ${puzzle.id} after ${seen}`);
    seen.push(puzzle.id); started.push(puzzle.id); current = puzzle.id;
  }
  assert.deepEqual([...seen].sort(), ids(puzzles).sort());
  assert.notEqual(nextPuzzle(puzzles, { currentId: current, started }).puzzle.id, current);
});

test('single-puzzle database: the only puzzle is offered again as a replay; empty or invalid lists give nothing', () => {
  assert.deepEqual(nextPuzzle([A], { currentId: A.id }), { puzzle: A, replay: true });
  assert.deepEqual(nextPuzzle([A], { currentId: A.id, solved: [A.id] }), { puzzle: A, replay: true });
  assert.equal(nextPuzzle([], { currentId: A.id }), null);
  assert.equal(nextPuzzle(undefined), null);
  assert.equal(startupPuzzle([]), null);
});

test('invalid or uncertified entries are never selectable, even if passed in directly', () => {
  const prelim = { ...B, id: 'prelim', certification: { ...B.certification, status: 'PRELIMINARY' } };
  const broken = { ...C, id: 'broken', puzzle: '0'.repeat(81) };
  const noCert = { ...D, id: 'no-cert', certification: undefined };
  const pool = [A, prelim, broken, noCert, null, { id: 'junk' }];
  for (const r of RANDOMS) {
    assert.deepEqual(nextPuzzle(pool, { currentId: A.id, random: () => r }), { puzzle: A, replay: true });
    assert.equal(startupPuzzle(pool, { random: () => r }).id, A.id);
  }
  assert.equal(nextPuzzle([prelim, broken], { currentId: null }), null);
});

test('difficulty filter only offers matching certified puzzles', () => {
  const ultra = { ...B, id: 'ultra', difficulty: 'Ultra Extreme', certification: { ...B.certification, status: 'CERTIFIED_ULTRA_EXTREME' } };
  const list = [A, ultra, C];
  for (const r of RANDOMS) {
    assert.equal(nextPuzzle(list, { currentId: A.id, difficulty: 'Ultra Extreme', random: () => r }).puzzle.id, 'ultra');
    assert.equal(nextPuzzle(list, { currentId: A.id, difficulty: 'Extreme', random: () => r }).puzzle.id, C.id);
  }
  assert.equal(nextPuzzle(list, { currentId: A.id, difficulty: 'Hard' }), null);
});

test('progress is isolated per puzzle ID across several production puzzles', () => {
  memoryStorage();
  try {
    const a = new SudokuGame(A), b = new SudokuGame(B);
    const ea = A.puzzle.indexOf('0'), eb = B.puzzle.indexOf('0');
    a.select(ea); a.input(Number(A.solution[ea]));
    saveGame(a.snapshot());
    b.select(eb); b.toggleNotes(); b.input(4); b.input(7);
    saveGame(b.snapshot());
    assert.equal(activePuzzleId(), B.id);
    assert.deepEqual(startedPuzzleIds().sort(), [A.id, B.id].sort());
    const ra = new SudokuGame(A, { saved: loadSave(A.id) }), rb = new SudokuGame(B, { saved: loadSave(B.id) });
    assert.equal(ra.state.values[ea], Number(A.solution[ea]));
    assert.deepEqual(ra.state.notes.flat(), []);
    assert.deepEqual(rb.state.notes[eb], [4, 7]);
    assert.equal(rb.state.values.filter(Boolean).length, B.clues);
    // A save never restores into a different puzzle.
    assert.equal(new SudokuGame(C, { saved: loadSave(A.id) }).state.values.filter(Boolean).length, C.clues);
    assert.equal(loadSave(C.id), null);
  } finally { restoreStorage(); }
});

test('completed state is isolated per puzzle ID and feeds the New Game choice', () => {
  const memory = memoryStorage();
  try {
    const solvedA = solve(A);
    assert.equal(solvedA.state.status, 'completed');
    saveGame(solvedA.snapshot());
    rememberPuzzle(A.id);
    const b = new SudokuGame(B);
    saveGame(b.snapshot());
    assert.equal(new SudokuGame(A, { saved: loadSave(A.id) }).state.status, 'completed');
    assert.equal(new SudokuGame(B, { saved: loadSave(B.id) }).state.status, 'playing');
    assert.deepEqual(loadRecent(), [A.id]);
    assert.ok(memory.has(STORAGE_KEYS.recent));
    // From B: A is solved, C/D unopened → never A, never B.
    for (const r of RANDOMS) {
      const choice = nextPuzzle(puzzles, { currentId: B.id, solved: loadRecent(), started: startedPuzzleIds(), random: () => r });
      assert.ok([C.id, D.id].includes(choice.puzzle.id));
    }
  } finally { restoreStorage(); }
});
