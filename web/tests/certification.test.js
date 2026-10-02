import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseDatabase } from '../lib/data.js';
import { SudokuGame } from '../lib/game.js';

test('optional certification evidence preserves schema-v1 parsing and gameplay', async () => {
  const database = JSON.parse(await readFile(new URL('../../data/puzzles.json', import.meta.url), 'utf8'));
  const original = database.puzzles[0];
  // Contract-only fixture: this does not certify or relabel the underlying demo.
  const extended = { ...original, certification: {
    status: 'PRELIMINARY', version: '1', searchConclusive: false,
    proofValidated: true, evidence: { futureProofField: ['ignored by the frontend'] },
  } };
  const parsed = parseDatabase({ ...database, puzzles: [extended] });
  assert.equal(parsed[0].id, original.id);
  assert.equal(parsed[0].difficulty, original.difficulty);
  assert.deepEqual(new SudokuGame(parsed[0]).state.values, [...original.puzzle].map(Number));
});
