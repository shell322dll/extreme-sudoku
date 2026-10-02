import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseProductionDatabase, loadProductionPuzzles, certificationLabel, hardestStep, slimDatabase } from '../lib/data.js';
import { SudokuGame } from '../lib/game.js';
import { STORAGE_KEYS, STORAGE_SCHEMA_VERSION, loadSave, saveGame, activePuzzleId, reconcileStorage } from '../lib/storage.js';

const production = JSON.parse(await readFile(new URL('../../data/production/puzzles.json', import.meta.url), 'utf8'));
const demo = JSON.parse(await readFile(new URL('../../data/puzzles.json', import.meta.url), 'utf8'));
const real = production.puzzles[0];
const quiet = () => {};
const withStatus = (status, id = 'x-' + status) => ({ ...real, id, certification: { ...real.certification, status } });
const db = (puzzles, extra = {}) => ({ ...production, puzzles, ...extra });

test('the production file loads and its puzzle is the certified Extreme record', () => {
  const puzzles = parseProductionDatabase(production, quiet);
  assert.equal(puzzles.length, production.puzzles.length);
  assert.equal(real.id, 'puzzle-8e2b144cecb50551d96b');
  assert.equal(certificationLabel(puzzles[0]), 'Certified Extreme');
  assert.equal(puzzles[0].clues, 22);
});

test('only CERTIFIED_EXTREME / CERTIFIED_ULTRA_EXTREME records are accepted', () => {
  const rejected = ['PRELIMINARY', 'SEARCH_INCONCLUSIVE', 'INCONCLUSIVE', 'SEARCH_TIMEOUT', 'REJECTED', 'UNRATED', '', undefined];
  const warnings = [];
  const parsed = parseProductionDatabase(db([...rejected.map((s, i) => withStatus(s, 'bad' + i)), real,
    withStatus('CERTIFIED_ULTRA_EXTREME', 'ultra-wrong-difficulty'),
    { ...withStatus('CERTIFIED_ULTRA_EXTREME', 'ultra'), difficulty: 'Ultra Extreme' }]), (...a) => warnings.push(a));
  assert.deepEqual(parsed.map(p => p.id), [real.id, 'ultra']);
  assert.equal(certificationLabel(parsed[1]), 'Certified Ultra Extreme');
  assert.equal(warnings.length, rejected.length + 1);
  const noCertification = { ...real, id: 'legacy' };
  delete noCertification.certification;
  assert.deepEqual(parseProductionDatabase(db([noCertification]), quiet), []);
});

test('broken records are skipped with a warning, never thrown', () => {
  const warnings = [];
  const bad = [{ ...real, id: 'short', puzzle: '0'.repeat(80) }, { ...real, id: 'clues', clues: 21 },
    { ...real, id: 'mismatch', solution: real.solution.replace(/^2/, '3') }, { ...real, id: 'chars', puzzle: 'x'.repeat(81) },
    { ...real, id: '' }, { ...real, id: 'diff', difficulty: 'Impossible' }, null, 'text', real, real];
  const parsed = parseProductionDatabase(db(bad), (...a) => warnings.push(a));
  assert.deepEqual(parsed.map(p => p.id), [real.id]);
  assert.equal(warnings.length, bad.length - 1);
});

test('unsupported schema or dataset kind is an error; unknown fields are ignored; empty is not an error', () => {
  assert.throws(() => parseProductionDatabase(db([real], { schemaVersion: 2 }), quiet), /schemaVersion/);
  assert.throws(() => parseProductionDatabase(demo, quiet), /production/);
  assert.throws(() => parseProductionDatabase(null, quiet), /Invalid/);
  assert.throws(() => parseProductionDatabase(db('nope'), quiet), /Invalid/);
  assert.equal(parseProductionDatabase(db([{ ...real, brandNewField: { a: 1 } }], { futureRootField: 1 }), quiet).length, 1);
  assert.deepEqual(parseProductionDatabase(db([]), quiet), []);
});

test('loader: fetch errors reject, bad schema rejects, valid JSON loads; there is no mock fallback', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => ({ ok: true, json: async () => production });
    assert.equal((await loadProductionPuzzles(new URL('https://u.github.io/repo/data/production/puzzles.json'), quiet)).length, 1);
    globalThis.fetch = async () => ({ ok: false, status: 503 });
    await assert.rejects(loadProductionPuzzles(new URL('https://u.github.io/x.json')), /503/);
    globalThis.fetch = async () => { throw new TypeError('offline'); };
    await assert.rejects(loadProductionPuzzles(new URL('https://u.github.io/x.json')), /offline/);
    globalThis.fetch = async () => ({ ok: true, json: async () => { throw new SyntaxError('bad json'); } });
    await assert.rejects(loadProductionPuzzles(new URL('https://u.github.io/x.json')), /bad json/);
    globalThis.fetch = async () => ({ ok: true, json: async () => ({ ...production, schemaVersion: 9 }) });
    await assert.rejects(loadProductionPuzzles(new URL('https://u.github.io/x.json')), /schemaVersion/);
  } finally { globalThis.fetch = original; }
});

test('slimDatabase drops proof evidence/config and keeps a compact hardest step', () => {
  assert.deepEqual(hardestStep(real.certification), { technique: 'Grouped AIC', rating: 35 });
  const slim = slimDatabase(production);
  const cert = slim.puzzles[0].certification;
  assert.equal(slim.derived, true);
  assert.equal(production.derived, undefined);
  assert.equal(cert.evidence, undefined);
  assert.equal(cert.config, undefined);
  assert.deepEqual(cert.hardestStep, { technique: 'Grouped AIC', rating: 35 });
  assert.equal(cert.genuineBottlenecks, real.certification.genuineBottlenecks);
  assert.ok(JSON.stringify(slim).length < JSON.stringify(production).length / 20);
  assert.equal(parseProductionDatabase(slim, quiet).length, 1);
  assert.notEqual(production.puzzles[0].certification.evidence, undefined, 'input must not be mutated');
});

test('the real puzzle is solved only by its exact solution; clues never change', () => {
  const game = new SudokuGame(real);
  const empty = [...real.puzzle].flatMap((d, i) => d === '0' ? [i] : []);
  assert.equal(empty.length, 81 - 22);
  for (const i of empty.slice(0, -1)) { game.select(i); game.input(Number(real.solution[i])); }
  assert.equal(game.state.status, 'playing');
  const last = empty.at(-1);
  game.select(last);
  game.input(Number(real.solution[last]) % 9 + 1);
  assert.equal(game.state.status, 'playing');
  game.input(Number(real.solution[last]));
  assert.equal(game.state.status, 'completed');
  assert.equal(game.state.values.join(''), real.solution);
});

test('version comes from package.json only (0.1.0)', async () => {
  const pkg = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'));
  assert.equal(pkg.version, '0.1.0');
  for (const file of ['../app.js', '../index.html', '../lib/data.js', '../lib/game.js', '../lib/storage.js']) {
    assert.doesNotMatch(await readFile(new URL(file, import.meta.url), 'utf8'), /\b[01]\.\d+\.\d+\b(?!\.)/, `${file} hardcodes a version`);
  }
});

test('timer is wall-clock: keeps running in the background, survives reload, never goes negative, pause freezes', () => {
  let now = 1000000;
  const game = new SudokuGame(real, { now: () => now });
  now += 5000;
  assert.equal(game.elapsedSeconds(), 5);
  const saved = game.snapshot(); // e.g. saved when the page was hidden or unloaded
  now += 600000; // browser backgrounded / closed for 10 minutes
  assert.equal(game.elapsedSeconds(), 605, 'a live hidden page keeps counting');
  assert.equal(new SudokuGame(real, { saved, now: () => now }).elapsedSeconds(), 605, 'reload adds the elapsed wall-clock time');
  now -= 3600000; // system clock moved back an hour
  assert.equal(new SudokuGame(real, { saved, now: () => now }).elapsedSeconds(), 5, 'restore never subtracts');
  assert.ok(game.elapsedMilliseconds() >= 5000, 'a live game never goes below its accumulated time');
  game.pause();
  const frozen = game.elapsedSeconds();
  now += 900000;
  assert.equal(game.elapsedSeconds(), frozen);
  assert.equal(new SudokuGame(real, { saved: game.snapshot(), now: () => now + 900000 }).elapsedSeconds(), frozen, 'paused saves stay frozen across reload');
});

function memoryStorage(initial = {}) {
  const memory = new Map(Object.entries(initial));
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, String(value)), removeItem: key => memory.delete(key) } });
  return memory;
}
const restoreStorage = () => delete globalThis.localStorage;

test('storage is per puzzle ID with a schema version; resume restores the whole game', () => {
  const memory = memoryStorage();
  try {
    const game = new SudokuGame(real);
    const empty = [...real.puzzle].flatMap((d, i) => d === '0' ? [i] : []);
    game.select(empty[0]); game.input(Number(real.solution[empty[0]]));
    game.select(empty[1]); game.toggleNotes(); game.input(3); game.input(5);
    game.toggleNotes(); game.select(empty[2]); game.input(Number(real.solution[empty[2]]) % 9 + 1);
    game.reveal(empty[3]);
    assert.equal(saveGame(game.snapshot()), true);
    assert.equal(saveGame({ ...new SudokuGame(demo.puzzles[0]).snapshot() }), true);
    const stored = JSON.parse(memory.get(STORAGE_KEYS.game));
    assert.equal(stored.storageSchemaVersion, STORAGE_SCHEMA_VERSION);
    assert.deepEqual(Object.keys(stored.games).sort(), [real.id, demo.puzzles[0].id].sort());
    assert.equal(activePuzzleId(), demo.puzzles[0].id);
    const restored = new SudokuGame(real, { saved: loadSave(real.id) });
    assert.deepEqual(restored.state.values, game.state.values);
    assert.deepEqual(restored.state.notes, game.state.notes);
    assert.equal(restored.state.mistakes, 1);
    assert.equal(restored.state.hintsUsed, 1);
    assert.equal(restored.state.selectedCell, game.state.selectedCell);
  } finally { restoreStorage(); }
});

test('completed saves restore as completed; edited clues and wrong fingerprints are rejected', () => {
  memoryStorage();
  try {
    const game = new SudokuGame(real);
    for (let i = 0; i < 81; i++) if (real.puzzle[i] === '0') { game.select(i); game.input(Number(real.solution[i])); }
    saveGame(game.snapshot());
    assert.equal(new SudokuGame(real, { saved: loadSave(real.id) }).state.status, 'completed');
    const tampered = { ...loadSave(real.id), values: Array(81).fill(1) };
    assert.equal(new SudokuGame(real, { saved: tampered }).state.status, 'playing');
    assert.equal(new SudokuGame(real, { saved: { ...loadSave(real.id), puzzleFingerprint: 'other' } }).state.values.filter(Boolean).length, 22);
  } finally { restoreStorage(); }
});

test('corrupted, future-version, legacy and unknown-ID storage is handled safely', () => {
  const legacyKnown = new SudokuGame(real).snapshot();
  let memory = memoryStorage({ [STORAGE_KEYS.game]: '{broken' });
  try {
    assert.equal(loadSave(), null);
    assert.equal(loadSave(real.id), null);
    memory.set(STORAGE_KEYS.game, JSON.stringify({ storageSchemaVersion: 99, activePuzzleId: real.id, games: { [real.id]: legacyKnown } }));
    assert.equal(loadSave(), null);
    memory.set(STORAGE_KEYS.game, JSON.stringify({ storageSchemaVersion: 2, activePuzzleId: 5, games: { a: 5, [real.id]: { ...legacyKnown, puzzleId: 'mismatch' } } }));
    assert.equal(activePuzzleId(), null);
    assert.equal(loadSave(real.id), null);
    // a pre-0.1 single-slot save is adopted into the per-puzzle store and the legacy key removed
    memory = memoryStorage({ [STORAGE_KEYS.legacyGame]: JSON.stringify(legacyKnown) });
    reconcileStorage([real.id]);
    assert.equal(loadSave(real.id).puzzleId, real.id);
    assert.equal(memory.has(STORAGE_KEYS.legacyGame), false);
    // saves of unknown (removed) puzzle IDs are kept; only saves untouched for 90+ days are discarded
    const day = 24 * 60 * 60 * 1000, now = Date.now();
    memory = memoryStorage();
    saveGame({ ...legacyKnown, savedAt: now });
    saveGame({ ...legacyKnown, puzzleId: 'gone-recent', savedAt: now - 5 * day });
    saveGame({ ...legacyKnown, puzzleId: 'gone-old', savedAt: now - 120 * day });
    reconcileStorage([], now);
    assert.notEqual(loadSave('gone-old'), null, 'an empty database never wipes progress');
    reconcileStorage([real.id], now);
    assert.notEqual(loadSave('gone-recent'), null);
    assert.equal(loadSave('gone-old'), null);
    assert.notEqual(loadSave(real.id), null);
    memory = memoryStorage({ [STORAGE_KEYS.legacyGame]: JSON.stringify({ ...legacyKnown, puzzleId: 'old-demo-id' }) });
    reconcileStorage([real.id], now);
    assert.notEqual(loadSave('old-demo-id'), null);
    assert.equal(memory.has(STORAGE_KEYS.legacyGame), false);
  } finally { restoreStorage(); }
});

test('storage cache re-reads when the stored value changes and stays correct after failed writes', () => {
  const memory = memoryStorage();
  try {
    const game = new SudokuGame(real);
    saveGame(game.snapshot());
    assert.equal(loadSave(real.id).puzzleId, real.id);
    memory.set(STORAGE_KEYS.game, JSON.stringify({ storageSchemaVersion: 2, activePuzzleId: null, games: {} }));
    assert.equal(loadSave(real.id), null, 'external change must be seen');
    const snapshots = new SudokuGame(real);
    for (let i = 0; i < 150; i++) { snapshots.state.history.push({ values: snapshots.state.values, notes: snapshots.state.notes, selectedCell: 0 }); }
    assert.equal(snapshots.snapshot().history.length, 100);
  } finally { restoreStorage(); }
});
