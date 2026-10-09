import test from 'node:test';
import assert from 'node:assert/strict';
import { STRATEGIES, STRATEGY_INTRO } from '../lib/strategy-content.js';

const lesson = (id) => STRATEGIES.find((entry) => entry.id === id);
const start = (id) => lesson(id).steps[0].diagram;
const finish = (id) => lesson(id).steps.at(-1).diagram;
const row = (i) => Math.floor(i / 9);
const column = (i) => i % 9;
const box = (i) => Math.floor(row(i) / 3) * 3 + Math.floor(column(i) / 3);
const sees = (a, b) => a !== b && (row(a) === row(b) || column(a) === column(b) || box(a) === box(b));
const scope = ({ type, index }) => Array.from({ length: 81 }, (_, i) => i).filter((i) => ({ row, column, box })[type](i) === index);
const digits = [1, 2, 3, 4, 5, 6, 7, 8, 9];

// Independent finite constraint enumeration, used only to prove the teaching
// examples. This is not a difficulty scorer or a production solving technique.
function assignments(cells) {
  const ordered = [...cells].sort((a, b) => a.candidates.length - b.candidates.length);
  const result = [];
  const current = new Map();
  function visit(offset) {
    if (offset === ordered.length) { result.push(new Map(current)); return; }
    const entry = ordered[offset];
    for (const digit of entry.candidates) {
      if ([...current].some(([other, value]) => value === digit && sees(entry.index, other))) continue;
      current.set(entry.index, digit);
      visit(offset + 1);
      current.delete(entry.index);
    }
  }
  visit(0);
  return result;
}

function checkDeductions(id) {
  const alternatives = assignments(start(id).cells);
  assert.ok(alternatives.length > 0, `${id}: premises must be satisfiable`);
  for (const { cell, digit } of finish(id).eliminations) {
    assert.ok(alternatives.every((values) => values.get(cell) !== digit), `${id}: ${cell} cannot be ${digit}`);
  }
  for (const { cell, digit } of finish(id).placements) {
    assert.ok(alternatives.every((values) => values.get(cell) === digit), `${id}: ${cell} must be ${digit}`);
  }
  return alternatives;
}

// For one-digit schematics choose exactly one occurrence in each base unit.
// A target is forbidden only if it sees an occurrence in EVERY possible case.
function digitCases(diagram, baseUnits) {
  const domains = baseUnits.map((unit) => {
    const indices = scope(unit);
    assert.ok(indices.every((i) => diagram.cells.some((entry) => entry.index === i)), 'the complete base unit is visible');
    return diagram.cells.filter((entry) => indices.includes(entry.index) && entry.candidates.includes(diagram.digit)).map((entry) => entry.index);
  });
  const result = [];
  function visit(chosen) {
    if (chosen.length === domains.length) { result.push(chosen); return; }
    for (const index of domains[chosen.length]) {
      if (chosen.some((other) => sees(index, other))) continue;
      visit([...chosen, index]);
    }
  }
  visit([]);
  return result;
}

test('nine Russian lessons have self-contained, internally consistent diagram stages', () => {
  assert.equal(STRATEGIES.length, 9);
  assert.equal(new Set(STRATEGIES.map(({ id }) => id)).size, STRATEGIES.length);
  assert.match(STRATEGY_INTRO.text, /не целые задачи/);
  for (const entry of STRATEGIES) {
    for (const field of ['title', 'when', 'why', 'mistake']) assert.match(entry[field], /[а-яё]/i);
    assert.ok(entry.sources.every(({ url }) => new URL(url).protocol === 'https:'));
    assert.ok(entry.steps.length >= 3);
    for (const { text, diagram } of entry.steps) {
      assert.match(text, /[а-яё]/i);
      assert.match(diagram.caption, /^Учебная схема\./);
      assert.equal(new Set(diagram.cells.map(({ index }) => index)).size, diagram.cells.length);
      for (const cell of diagram.cells) {
        assert.ok(Number.isInteger(cell.index) && cell.index >= 0 && cell.index < 81);
        if (cell.value) assert.ok(digits.includes(cell.value));
        else {
          assert.ok(Array.isArray(cell.candidates));
          assert.equal(new Set(cell.candidates).size, cell.candidates.length);
          assert.ok(cell.candidates.every((digit) => digits.includes(digit)));
        }
      }
      for (const unit of diagram.units) assert.equal(scope(unit).length, 9);
      for (const { from, to } of diagram.arrows) {
        assert.ok(diagram.cells.some(({ index }) => index === from));
        assert.ok(diagram.cells.some(({ index }) => index === to));
      }
      for (const { cell, digit } of diagram.eliminations) assert.ok(diagram.cells.find(({ index }) => index === cell)?.candidates.includes(digit));
      for (const { cell, digit } of diagram.placements) assert.equal(diagram.cells.find(({ index }) => index === cell)?.value, digit);
    }
  }
});

test('full house places the only missing digit of the complete row', () => {
  const first = start('full-house');
  assert.deepEqual(first.cells.map(({ index }) => index), scope(first.units[0]));
  const given = first.cells.filter(({ value }) => value).map(({ value }) => value);
  assert.equal(new Set(given).size, 8);
  assert.deepEqual(digits.filter((digit) => !given.includes(digit)), finish('full-house').placements.map(({ digit }) => digit));
});

test('naked single excludes all eight alternatives with actual visible peer givens', () => {
  const first = start('naked-single');
  const { cell, digit } = finish('naked-single').placements[0];
  const givens = first.cells.filter(({ value }) => value);
  for (const a of givens) for (const b of givens) assert.ok(!sees(a.index, b.index) || a.value !== b.value, 'givens do not contradict each other');
  const forbidden = givens.filter(({ index }) => sees(index, cell)).map(({ value }) => value);
  assert.deepEqual(digits.filter((value) => !forbidden.includes(value)), [digit]);
});

test('hidden single really has multiple candidates but only one possible location for its digit', () => {
  const { cell, digit } = finish('hidden-single').placements[0];
  assert.ok(start('hidden-single').cells.find(({ index }) => index === cell).candidates.length > 1);
  assert.deepEqual(start('hidden-single').cells.filter(({ candidates }) => candidates.includes(digit)).map(({ index }) => index), [cell]);
  checkDeductions('hidden-single');
});

for (const id of ['naked-pair', 'hidden-pair']) {
  test(`${id}: every illustrated elimination follows in all legal assignments; neither order is chosen`, () => {
    const alternatives = checkDeductions(id);
    const pairCells = start(id).cells.filter(({ highlight }) => highlight === 'focus');
    assert.equal(pairCells.length, 2);
    for (const { index } of pairCells) assert.equal(new Set(alternatives.map((values) => values.get(index))).size, 2);
    assert.equal(finish(id).placements.length, 0);
  });
}

for (const [id, bases] of [
  ['pointing', [{ type: 'box', index: 0 }]],
  ['claiming', [{ type: 'row', index: 4 }]],
  ['x-wing', [{ type: 'row', index: 1 }, { type: 'row', index: 6 }]],
]) {
  test(`${id}: the whole base scope is shown and every digit placement forbids all crossed candidates`, () => {
    const first = start(id);
    assert.equal(first.candidateMode, 'digit');
    const alternatives = digitCases(first, bases);
    assert.equal(alternatives.length, 2);
    for (const { cell, digit } of finish(id).eliminations) {
      assert.equal(digit, first.digit);
      assert.ok(alternatives.every((positions) => positions.some((index) => sees(index, cell))));
    }
    assert.equal(finish(id).placements.length, 0);
  });
}

test('X-Wing needs exactly two source positions: an extra position supplies a counterexample', () => {
  const first = structuredClone(start('x-wing'));
  first.cells.find(({ index }) => index === 9).candidates = [first.digit];
  const alternatives = digitCases(first, [{ type: 'row', index: 1 }, { type: 'row', index: 6 }]);
  assert.ok(finish('x-wing').eliminations.some(({ cell }) => alternatives.some((positions) => positions.every((index) => !sees(index, cell)))));
});

test('naked pair needs exactly two candidates: a third supplies a counterexample', () => {
  const cells = structuredClone(start('naked-pair').cells);
  cells.find(({ index }) => index === 55).candidates.push(4);
  const alternatives = assignments(cells);
  assert.ok(finish('naked-pair').eliminations.some(({ cell, digit }) => alternatives.some((values) => values.get(cell) === digit)));
});

test('hidden pair needs exclusive locations: an outside candidate supplies a counterexample', () => {
  const cells = structuredClone(start('hidden-pair').cells);
  cells.find(({ index }) => index === 7).candidates.push(3);
  const alternatives = assignments(cells);
  assert.ok(finish('hidden-pair').eliminations.some(({ cell, digit }) => alternatives.some((values) => values.get(cell) === digit)));
});

test('XY-Wing proves both pivot branches, with a target seeing both wings but not the pivot', () => {
  const first = start('xy-wing');
  const pivot = first.cells.find(({ highlight }) => highlight === 'focus');
  const wings = first.cells.filter(({ highlight }) => highlight === 'support');
  const target = first.cells.find(({ highlight }) => highlight === 'target');
  assert.equal(pivot.candidates.length, 2);
  assert.equal(wings.length, 2);
  assert.ok(wings.every(({ index, candidates }) => sees(index, pivot.index) && sees(index, target.index) && candidates.length === 2));
  assert.equal(sees(target.index, pivot.index), false);
  const alternatives = checkDeductions('xy-wing');
  const excluded = finish('xy-wing').eliminations[0].digit;
  for (const digit of pivot.candidates) {
    const branch = alternatives.filter((values) => values.get(pivot.index) === digit);
    assert.ok(branch.length > 0);
    assert.ok(branch.every((values) => wings.some(({ index }) => values.get(index) === excluded)));
  }
  assert.deepEqual([...new Set(alternatives.map((values) => values.get(target.index)))].sort(), target.candidates.filter((digit) => digit !== excluded));
  assert.equal(finish('xy-wing').placements.length, 0);
});

test('XY-Wing cannot eliminate in a cell seeing only one wing', () => {
  const cells = structuredClone(start('xy-wing').cells);
  const target = cells.find(({ highlight }) => highlight === 'target');
  target.index = 16; // row 2 column 8: sees the right wing only.
  assert.equal(cells.filter(({ highlight, index }) => highlight === 'support' && sees(target.index, index)).length, 1);
  assert.ok(assignments(cells).some((values) => values.get(target.index) === 9));
});
