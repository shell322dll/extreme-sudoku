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
 * Only never-started puzzles qualify. Exhaustion returns null, never a replay or an implicit resume.
 */
export function nextPuzzle(puzzles, { currentId = null, solved = [], started = [], difficulty = null, random = Math.random } = {}) {
  const seen = new Set([...solved, ...started, currentId]);
  const selectable = (Array.isArray(puzzles) ? puzzles : []).filter((puzzle) => isProductionPuzzle(puzzle) && (!difficulty || puzzle.difficulty === difficulty));
  const pool = selectable.filter((puzzle) => !seen.has(puzzle.id));
  if (pool.length) return { puzzle: pickRandom(pool, random), replay: false };
  return null;
}

/** Puzzle to open on start-up when no active save exists: a random unsolved one, else a random one. */
export function startupPuzzle(puzzles, options = {}) {
  return nextPuzzle(puzzles, options)?.puzzle ?? null;
}

function pickRandom(pool, random) {
  const value = Number(random());
  const index = Number.isFinite(value) ? Math.floor(Math.min(Math.max(value, 0), 1 - Number.EPSILON) * pool.length) : 0;
  return pool[Math.min(index, pool.length - 1)];
}
