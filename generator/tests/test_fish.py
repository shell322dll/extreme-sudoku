"""Ordinary fish in both orientations, exact effects and broken covers."""

import unittest

from generator.solver.human_solver import apply_step
from generator.solver.techniques.fish import XWing, Swordfish, Jellyfish
from generator.sudoku.candidates import ALL, SudokuState, digit_mask


def fish_state(rows, supports, transpose=False, digit=5):
    candidates = [ALL] * 81
    for row, cols in zip(rows, supports):
        for col in range(9):
            cell = col * 9 + row if transpose else row * 9 + col
            if col not in cols:
                candidates[cell] &= ~digit_mask(digit)
    return SudokuState([0] * 81, candidates)


class FishTests(unittest.TestCase):
    def assert_fish(self, technique, rows, supports, transpose=False, digit=5):
        state = fish_state(rows, supports, transpose, digit)
        before = (state.grid.copy(), state.candidates.copy())
        steps = technique.find_steps(state)
        self.assertEqual(len(steps), 1, steps)
        expected = tuple(sorted((col * 9 + row if transpose else row * 9 + col, digit)
                                for row in range(9) if row not in rows
                                for col in set().union(*supports)))
        self.assertEqual(steps[0].eliminations, expected)
        self.assertEqual(steps[0].placements, ())
        self.assertTrue(steps[0].premises)
        self.assertTrue(steps[0].explanation)
        self.assertEqual(steps[0].technique, technique.name)
        self.assertEqual(steps[0].rating, technique.difficulty)
        self.assertEqual(technique.find_steps(state), steps)
        self.assertEqual(before, (state.grid, state.candidates))
        updated = apply_step(state, steps[0])
        updated.validate()
        for cell, value in expected:
            self.assertFalse(updated.candidates[cell] & digit_mask(value))
        self.assertEqual(before, (state.grid, state.candidates))

    def test_x_wing_both_orientations(self):
        for transpose in (False, True):
            with self.subTest(transpose=transpose):
                self.assert_fish(XWing(), (0, 3), ({1, 5}, {1, 5}), transpose)

    def test_x_wing_different_digit_and_lines(self):
        self.assert_fish(XWing(), (2, 7), ({0, 8}, {0, 8}), digit=9)

    def test_x_wing_negative_extra_cover(self):
        for transpose in (False, True):
            state = fish_state((0, 3), ({1, 5}, {1, 5, 8}), transpose)
            self.assertEqual(XWing().find_steps(state), [])

    def test_swordfish_sparse_both_orientations(self):
        for transpose in (False, True):
            with self.subTest(transpose=transpose):
                self.assert_fish(Swordfish(), (0, 3, 6), ({1, 4}, {4, 7}, {1, 7}), transpose)

    def test_swordfish_three_candidates_per_base(self):
        self.assert_fish(Swordfish(), (1, 4, 7), ({0, 3, 8},) * 3, digit=2)

    def test_swordfish_negative_four_cover_lines(self):
        for transpose in (False, True):
            state = fish_state((0, 3, 6), ({1, 4}, {4, 7}, {1, 7, 8}), transpose)
            self.assertEqual(Swordfish().find_steps(state), [])

    def test_jellyfish_sparse_both_orientations(self):
        for transpose in (False, True):
            with self.subTest(transpose=transpose):
                self.assert_fish(Jellyfish(), (0, 2, 4, 6), ({0, 2}, {2, 4}, {4, 6}, {0, 6}), transpose)

    def test_jellyfish_negative_fifth_cover(self):
        state = fish_state((0, 2, 4, 6), ({0, 2}, {2, 4}, {4, 6}, {0, 6, 8}))
        self.assertEqual(Jellyfish().find_steps(state), [])

    def test_no_effect_is_not_a_step(self):
        state = fish_state((0, 3), ({1, 5}, {1, 5}))
        for row in range(9):
            if row not in (0, 3):
                for col in (1, 5):
                    state.candidates[row * 9 + col] &= ~digit_mask(5)
        state.validate()
        self.assertEqual(XWing().find_steps(state), [])

    def test_finds_all_independent_digit_patterns(self):
        state = fish_state((0, 3), ({1, 5}, {1, 5}), digit=5)
        second = fish_state((2, 7), ({0, 8}, {0, 8}), digit=9)
        state = SudokuState([0] * 81, [a & b for a, b in zip(state.candidates, second.candidates)])
        steps = XWing().find_steps(state)
        self.assertEqual(len(steps), 2)
        self.assertEqual({step.eliminations[0][1] for step in steps}, {5, 9})


if __name__ == "__main__":
    unittest.main()
