"""Exact quad effects on rows, columns and boxes, with near-miss negatives."""

import unittest

from generator.solver.human_solver import apply_step
from generator.solver.techniques.subsets import NakedQuad, HiddenQuad
from generator.sudoku.candidates import ALL, SudokuState, digit_mask
from generator.sudoku.grid import ROWS, COLS, BOXES


def mask(*digits):
    return sum(digit_mask(digit) for digit in digits)


def state_with(changes):
    candidates = [ALL] * 81
    for cell, value in changes.items():
        candidates[cell] = value
    return SudokuState([0] * 81, candidates)


CASES = ((ROWS[0], (0, 2, 4, 7)), (COLS[0], (0, 18, 36, 63)),
         (BOXES[0], (0, 10, 18, 20)))


class QuadTests(unittest.TestCase):
    def assert_step(self, technique, state, expected):
        before = state.grid.copy(), state.candidates.copy()
        steps = technique.find_steps(state)
        self.assertEqual(len(steps), 1, steps)
        step = steps[0]
        self.assertEqual(step.eliminations, tuple(sorted(expected)))
        self.assertEqual(step.placements, ())
        self.assertEqual(step.technique, technique.name)
        self.assertEqual(step.rating, technique.difficulty)
        self.assertTrue(step.premises)
        self.assertTrue(step.explanation)
        self.assertEqual(steps, technique.find_steps(state))
        apply_step(state, step).validate()
        self.assertEqual(before, (state.grid, state.candidates))

    def test_naked_quad_rows_columns_boxes(self):
        for unit, cells in CASES:
            with self.subTest(unit=unit):
                changes = dict(zip(cells, (mask(1, 2), mask(2, 3), mask(3, 4), mask(1, 4))))
                expected = [(c, d) for c in unit if c not in cells for d in (1, 2, 3, 4)]
                self.assert_step(NakedQuad(), state_with(changes), expected)

    def test_naked_quad_extra_digit_is_not_a_quad(self):
        for _, cells in CASES:
            changes = dict(zip(cells, (mask(1, 2), mask(2, 3), mask(3, 4), mask(1, 4, 5))))
            state = state_with(changes)
            before = state.candidates.copy()
            self.assertEqual(NakedQuad().find_steps(state), [])
            self.assertEqual(state.candidates, before)

    def test_hidden_quad_rows_columns_boxes(self):
        for unit, cells in CASES:
            with self.subTest(unit=unit):
                changes = {c: ALL & ~mask(1, 2, 3, 4) for c in unit}
                changes.update(dict(zip(cells, (mask(1, 2, 5), mask(2, 3, 6),
                                                mask(3, 4, 7), mask(1, 4, 8)))))
                self.assert_step(HiddenQuad(), state_with(changes), zip(cells, (5, 6, 7, 8)))

    def test_hidden_quad_extra_support_is_not_a_quad(self):
        for unit, cells in CASES:
            changes = {c: ALL & ~mask(1, 2, 3, 4) for c in unit}
            changes.update(dict(zip(cells, (mask(1, 2, 5), mask(2, 3, 6),
                                            mask(3, 4, 7), mask(1, 4, 8)))))
            changes[next(c for c in unit if c not in cells)] |= mask(1, 2, 3, 4)
            state = state_with(changes)
            before = state.candidates.copy()
            self.assertEqual(HiddenQuad().find_steps(state), [])
            self.assertEqual(state.candidates, before)

    def test_quad_without_elimination_is_not_a_step(self):
        for technique in (NakedQuad(), HiddenQuad()):
            unit, cells = CASES[0]
            changes = {c: ALL & ~mask(1, 2, 3, 4) for c in unit}
            changes.update({c: mask(1, 2, 3, 4) for c in cells})
            self.assertEqual(technique.find_steps(state_with(changes)), [])


if __name__ == "__main__":
    unittest.main()
