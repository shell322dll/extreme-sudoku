"""Exact effect fixtures on valid, deliberately restricted candidate states."""

import unittest

from generator.sudoku.candidates import ALL, SudokuState, digit_mask
from generator.sudoku.grid import ROWS, COLS, BOXES
from generator.solver.techniques import (
    TECHNIQUE_TYPES, FullHouse, NakedSingle, HiddenSingle, LockedCandidates,
    NakedPair, HiddenPair, NakedTriple, HiddenTriple,
)


def mask(*digits):
    return sum(digit_mask(d) for d in digits)


def state_with(changes):
    candidates = [ALL] * 81
    for cell, value in changes.items():
        candidates[cell] = value
    return SudokuState([0] * 81, candidates=candidates)


class TechniqueTests(unittest.TestCase):
    def assert_effect(self, technique, state, placements=(), eliminations=()):
        before = (state.grid.copy(), state.candidates.copy())
        steps = technique.find_steps(state)
        self.assertEqual(len(steps), 1, steps)
        step = steps[0]
        self.assertEqual(step.placements, tuple(sorted(placements)))
        self.assertEqual(step.eliminations, tuple(sorted(eliminations)))
        self.assertTrue(step.premises)
        self.assertTrue(step.explanation)
        self.assertEqual(step.technique, technique.name)
        self.assertEqual(step.rating, technique.difficulty)
        self.assertEqual(before, (state.grid, state.candidates))
        self.assertEqual(steps, technique.find_steps(state))

    def test_all_techniques_negative_and_no_mutation(self):
        state = SudokuState([0] * 81)
        for cls in TECHNIQUE_TYPES:
            with self.subTest(technique=cls.name):
                self.assertEqual(cls().find_steps(state), [])
        self.assertEqual(state.candidates, [ALL] * 81)

    def test_full_house_rows_columns_boxes(self):
        for unit in (ROWS[0], COLS[0], BOXES[0]):
            with self.subTest(unit=unit):
                grid = [0] * 81
                for digit, cell in enumerate(unit[:-1], 1):
                    grid[cell] = digit
                self.assert_effect(FullHouse(), SudokuState(grid), placements=((unit[-1], 9),))

    def test_full_house_negative_two_empty_cells(self):
        grid = [1, 2, 3, 4, 5, 6, 7, 0, 0] + [0] * 72
        self.assertEqual(FullHouse().find_steps(SudokuState(grid)), [])

    def test_naked_single(self):
        self.assert_effect(NakedSingle(), state_with({40: mask(7)}), placements=((40, 7),))
        self.assertEqual(NakedSingle().find_steps(state_with({40: mask(7, 8)})), [])

    def test_hidden_single_rows_columns_boxes(self):
        for unit in (ROWS[0], COLS[0], BOXES[0]):
            with self.subTest(unit=unit):
                changes = {c: ALL & ~mask(1) for c in unit[1:]}
                self.assert_effect(HiddenSingle(), state_with(changes), placements=((unit[0], 1),))
                changes.pop(unit[1])
                self.assertEqual(HiddenSingle().find_steps(state_with(changes)), [])

    def test_pointing_rows_columns(self):
        for cells, target in (((0, 1), ROWS[0]), ((0, 9), COLS[0])):
            with self.subTest(cells=cells):
                changes = {c: ALL & ~mask(1) for c in BOXES[0] if c not in cells}
                expected = [(c, 1) for c in target if c not in BOXES[0]]
                self.assert_effect(LockedCandidates(), state_with(changes), eliminations=expected)
                changes.pop(20)
                self.assertEqual(LockedCandidates().find_steps(state_with(changes)), [])

    def test_claiming_rows_columns(self):
        for cells, source in (((0, 1), ROWS[0]), ((0, 9), COLS[0])):
            with self.subTest(cells=cells):
                changes = {c: ALL & ~mask(1) for c in source if c not in cells}
                expected = [(c, 1) for c in BOXES[0] if c not in source]
                self.assert_effect(LockedCandidates(), state_with(changes), eliminations=expected)
                changes.pop(source[-1])
                self.assertEqual(LockedCandidates().find_steps(state_with(changes)), [])

    def test_naked_pair_rows_columns_boxes(self):
        cases = ((ROWS[0], (0, 4)), (COLS[0], (0, 36)), (BOXES[0], (0, 10)))
        for unit, cells in cases:
            with self.subTest(unit=unit):
                changes = {c: mask(1, 2) for c in cells}
                expected = [(c, d) for c in unit if c not in cells for d in (1, 2)]
                self.assert_effect(NakedPair(), state_with(changes), eliminations=expected)
                changes[cells[-1]] = mask(1, 2, 3)
                self.assertEqual(NakedPair().find_steps(state_with(changes)), [])

    def test_naked_triple_nonidentical_rows_columns_boxes(self):
        cases = ((ROWS[0], (0, 3, 6)), (COLS[0], (0, 27, 54)), (BOXES[0], (0, 10, 20)))
        for unit, cells in cases:
            with self.subTest(unit=unit):
                changes = dict(zip(cells, (mask(1, 2), mask(2, 3), mask(1, 3))))
                expected = [(c, d) for c in unit if c not in cells for d in (1, 2, 3)]
                self.assert_effect(NakedTriple(), state_with(changes), eliminations=expected)
                changes[cells[-1]] = mask(1, 4)
                self.assertEqual(NakedTriple().find_steps(state_with(changes)), [])

    def test_hidden_pair_rows_columns_boxes(self):
        cases = ((ROWS[0], (0, 4)), (COLS[0], (0, 36)), (BOXES[0], (0, 10)))
        for unit, cells in cases:
            with self.subTest(unit=unit):
                changes = {c: ALL & ~mask(1, 2) for c in unit}
                changes.update({cells[0]: mask(1, 2, 4), cells[1]: mask(1, 2, 5)})
                self.assert_effect(HiddenPair(), state_with(changes),
                                   eliminations=((cells[0], 4), (cells[1], 5)))
                extra = next(c for c in unit if c not in cells)
                changes[extra] |= mask(1, 2)
                self.assertEqual(HiddenPair().find_steps(state_with(changes)), [])

    def test_hidden_triple_nonidentical_rows_columns_boxes(self):
        cases = ((ROWS[0], (0, 3, 6)), (COLS[0], (0, 27, 54)), (BOXES[0], (0, 10, 20)))
        for unit, cells in cases:
            with self.subTest(unit=unit):
                changes = {c: ALL & ~mask(1, 2, 3) for c in unit}
                changes.update(dict(zip(cells, (mask(1, 2, 4), mask(2, 3, 5), mask(1, 3, 6)))))
                self.assert_effect(HiddenTriple(), state_with(changes),
                                   eliminations=tuple(zip(cells, (4, 5, 6))))
                extra = next(c for c in unit if c not in cells)
                changes[extra] |= mask(1, 2, 3)
                self.assertEqual(HiddenTriple().find_steps(state_with(changes)), [])

    def test_subsets_without_elimination_are_not_steps(self):
        for cls, size in ((NakedPair, 2), (NakedTriple, 3), (HiddenPair, 2), (HiddenTriple, 3)):
            with self.subTest(technique=cls.name):
                digits = tuple(range(1, size + 1))
                cells = (0, 3, 6)[:size]
                changes = {c: ALL & ~mask(*digits) for c in ROWS[0]}
                changes.update({c: mask(*digits) for c in cells})
                self.assertEqual(cls().find_steps(state_with(changes)), [])


if __name__ == "__main__":
    unittest.main()
