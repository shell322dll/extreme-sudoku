import { isProductionPuzzle } from './data.js';

/**
 * Choose the puzzle for "New Game". Pure: storage facts and the random source are passed in.
 *
 *   puzzles   loaded production puzzles (re-checked here: only production-eligible records are selectable)
 *   currentId the puzzle on screen; never chosen while any other selectable puzzle exists
 *   solved    solved IDs, most recently solved first (storage `loadRecent()` order)
 *   started   IDs with saved progress (in progress or completed)
 *   difficulty optional filter, e.g. 'Extreme'
 *   random    () => [0, 1); inject a seeded function for deterministic tests
 *
 * Preference: unsolved and never opened → unsolved in progress (resumes its own save) → solved, least
 * recently solved first (a replay, started fresh). Only when the current puzzle is the sole selectable
 * one is it returned (as a replay). Returns { puzzle, replay } or null when nothing is selectable.
 */
export function nextPuzzle(puzzles, { currentId = null, solved = [], started = [], difficulty = null, random = Math.random } = {}) {
  const solvedOrder = [...solved];
  const solvedSet = new Set(solvedOrder), startedSet = new Set(started);
  const selectable = (Array.isArray(puzzles) ? puzzles : []).filter((puzzle) => isProductionPuzzle(puzzle) && (!difficulty || puzzle.difficulty === difficulty));
  const others = selectable.filter((puzzle) => puzzle.id !== currentId);
  const unsolved = others.filter((puzzle) => !solvedSet.has(puzzle.id));
  const fresh = unsolved.filter((puzzle) => !startedSet.has(puzzle.id));
  const pool = fresh.length ? fresh : unsolved;
  if (pool.length) return { puzzle: pickRandom(pool, random), replay: false };
  if (others.length) {
    // Everything else is solved: replay the one solved longest ago (never the one just finished).
    const age = (puzzle) => solvedOrder.indexOf(puzzle.id);
    return { puzzle: others.reduce((oldest, puzzle) => age(puzzle) > age(oldest) ? puzzle : oldest), replay: true };
  }
  const current = selectable.find((puzzle) => puzzle.id === currentId);
  return current ? { puzzle: current, replay: true } : null;
}

/** Puzzle to open on start-up when no active save exists: a random unsolved one, else a random one. */
export function startupPuzzle(puzzles, { solved = [], random = Math.random } = {}) {
  const solvedSet = new Set(solved);
  const selectable = (Array.isArray(puzzles) ? puzzles : []).filter(isProductionPuzzle);
  const unsolved = selectable.filter((puzzle) => !solvedSet.has(puzzle.id));
  const pool = unsolved.length ? unsolved : selectable;
  return pool.length ? pickRandom(pool, random) : null;
}

function pickRandom(pool, random) {
  const value = Number(random());
  const index = Number.isFinite(value) ? Math.floor(Math.min(Math.max(value, 0), 1 - Number.EPSILON) * pool.length) : 0;
  return pool[Math.min(index, pool.length - 1)];
}
