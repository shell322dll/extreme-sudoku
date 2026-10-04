import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { isProductionPuzzle, isCertifiedPuzzle, isVerifiedStandardPuzzle, parseProductionDatabase, certificationLabel, slimDatabase } from '../lib/data.js';
import { nextPuzzle } from '../lib/selection.js';
import { SudokuGame } from '../lib/game.js';
import { loadSave, saveGame, activePuzzleId } from '../lib/storage.js';

const database = JSON.parse(await readFile(new URL('./fixtures/production_multi.json', import.meta.url), 'utf8'));
const extreme = database.puzzles[0];
// Schema-only fixtures: exercise the browser's structural gate, never claim these puzzles were re-rated.
function standard(difficulty, id = difficulty) {
  const { certification, ...record } = extreme;
  const requiredRating = difficulty === 'Easy' ? 1.2 : 3;
  return { ...record, id, difficulty, rating: 200, hardestTechnique: difficulty === 'Easy' ? 'Hidden Single' : 'Naked Pair',
    difficultyData: { hardestRating: requiredRating }, solutionSteps: 60,
    verification: { status: 'VERIFIED', version: 1, method: 'DETERMINISTIC_THRESHOLD_REPLAY', difficulty,
      requiredRating, techniqueCeiling: difficulty === 'Easy' ? 1.2 : 5.2,
      humanSolved: true, proofValidated: true, reproducible: true, unique: true, guesses: 0, usedBacktracking: false,
      evidence: { fullPath: ['not published'] } } };
}
const easy = standard('Easy'), medium = standard('Medium');
const quiet = () => {};

test('Easy/Medium structural admission is separate from unchanged Extreme certification', () => {
  for (const puzzle of [easy, medium]) {
    assert.equal(isProductionPuzzle(puzzle), true);
    assert.equal(isVerifiedStandardPuzzle(puzzle), true);
    assert.equal(isCertifiedPuzzle(puzzle), false);
    assert.equal(certificationLabel(puzzle), null);
  }
  assert.equal(isCertifiedPuzzle(extreme), true);
  assert.equal(isVerifiedStandardPuzzle(extreme), false);
  assert.equal(isProductionPuzzle({ ...extreme, certification: undefined, verification: easy.verification }), false);
  assert.equal(isProductionPuzzle({ ...easy, certification: extreme.certification }), false);
  assert.equal(isProductionPuzzle({ ...medium, difficulty: 'Hard' }), false);
});

test('standard admission rejects inconsistent difficulty, unverified status, false flags and missing evidence summaries', () => {
  const changes = [
    { status: 'PRELIMINARY' }, { status: 'SEARCH_INCONCLUSIVE' }, { status: 'INVALID' }, { status: 'CERTIFIED_EXTREME' },
    { version: 2 }, { method: 'GUESSING' }, { difficulty: 'Medium' }, { requiredRating: 3 },
    { requiredRating: -1 }, { requiredRating: NaN }, { techniqueCeiling: 7 }, { humanSolved: false },
    { proofValidated: false }, { reproducible: false }, { unique: false }, { guesses: 1 }, { usedBacktracking: true },
  ];
  for (const patch of changes) assert.equal(isProductionPuzzle({ ...easy, verification: { ...easy.verification, ...patch } }), false, JSON.stringify(patch));
  for (const key of Object.keys(easy.verification).filter(k => k !== 'evidence')) {
    const copy = structuredClone(easy); delete copy.verification[key];
    assert.equal(isProductionPuzzle(copy), false, `missing ${key}`);
  }
  assert.equal(isProductionPuzzle({ ...medium, verification: { ...medium.verification, requiredRating: 7 } }), false, 'Hard cannot masquerade as Medium');
  assert.equal(isProductionPuzzle({ ...easy, difficulty: 'Medium' }), false, 'Easy metadata cannot masquerade as Medium');
  assert.equal(isProductionPuzzle({ ...medium, difficulty: 'Easy' }), false, 'Medium cannot masquerade as Easy');
  for (const patch of [{ rating: NaN }, { rating: -1 }, { solutionSteps: 0 }, { hardestTechnique: '' }, { difficultyData: {} }])
    assert.equal(isProductionPuzzle({ ...easy, ...patch }), false);
});

test('mixed production parses verified standards and certified Extreme; future fields ignored and duplicates rejected', () => {
  const records = [easy, medium, extreme];
  const db = { ...database, puzzles: [...records, easy, { ...medium, id: 'unverified', verification: undefined }] };
  assert.deepEqual(parseProductionDatabase(db, quiet).map(p => p.id), records.map(p => p.id));
  assert.equal(isProductionPuzzle({ ...easy, futureField: true, verification: { ...easy.verification, futureProof: {} } }), true);
  const slim = slimDatabase({ ...db, puzzles: records });
  assert.equal(parseProductionDatabase(slim, quiet).length, 3);
  assert.equal(slim.puzzles[0].verification.evidence, undefined);
  assert.ok(easy.verification.evidence, 'source evidence stays untouched');
  assert.equal(slim.puzzles[1].hardestTechnique, medium.hardestTechnique);
});

test('New Game stays in the selected category including all-solved replays and a single-puzzle category', () => {
  const list = [easy, standard('Easy', 'easy-b'), medium, standard('Medium', 'medium-b'), ...database.puzzles];
  for (const difficulty of ['Easy', 'Medium', 'Extreme']) {
    const current = list.find(p => p.difficulty === difficulty);
    for (const random of [0, 0.5, 0.9999]) {
      for (const solved of [[], list.map(p => p.id)]) {
        const choice = nextPuzzle(list, { currentId: current.id, difficulty, solved, random: () => random });
        assert.equal(choice.puzzle.difficulty, difficulty);
        assert.notEqual(choice.puzzle.id, current.id);
        assert.equal(choice.replay, solved.length > 0);
      }
    }
  }
  assert.deepEqual(nextPuzzle([easy, medium, extreme], { currentId: easy.id, difficulty: 'Easy' }), { puzzle: easy, replay: true });
  assert.equal(nextPuzzle(list, { difficulty: 'Expert' }), null);
});

test('Easy A / Medium B / Extreme C progress, notes, undo, mistakes and hints remain isolated by ID', () => {
  const memory = new Map();
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, String(value)), removeItem: key => memory.delete(key) } });
  try {
    const records = [easy, medium, extreme], snapshots = [];
    for (const [n, puzzle] of records.entries()) {
      const game = new SudokuGame(puzzle);
      const empties = [...puzzle.puzzle].flatMap((d, i) => d === '0' ? [i] : []);
      game.select(empties[n]); game.input(Number(puzzle.solution[empties[n]]));
      game.select(empties[4 + n]); game.toggleNotes(); game.input(n + 1); game.toggleNotes();
      game.select(empties[8 + n]); game.input(Number(puzzle.solution[empties[8 + n]]) % 9 + 1);
      game.reveal(empties[12 + n]);
      const snapshot = game.snapshot(); snapshots.push(snapshot); saveGame(snapshot);
    }
    assert.equal(activePuzzleId(), extreme.id);
    for (const [n, puzzle] of records.entries()) {
      const restored = new SudokuGame(puzzle, { saved: loadSave(puzzle.id) }).snapshot();
      for (const key of ['values', 'notes', 'history', 'mistakes', 'hintsUsed', 'selectedCell']) assert.deepEqual(restored[key], snapshots[n][key], `${puzzle.id}: ${key}`);
    }
  } finally { delete globalThis.localStorage; }
});
