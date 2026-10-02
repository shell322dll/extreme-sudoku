"""Fixed conjugate patterns and grouped Empty Rectangle implications."""

import unittest

from generator.solver.human_solver import apply_step
from generator.solver.techniques.single_digit_patterns import (
    Skyscraper, TwoStringKite, TurbotFish, EmptyRectangle,
)
from generator.sudoku.candidates import ALL, SudokuState, digit_mask
from generator.sudoku.grid import ROWS, COLS, BOXES


def restrict(*restrictions, transpose=False):
    candidates = [ALL] * 81
    for unit, allowed in restrictions:
        for cell in unit:
            if cell not in allowed:
                mapped = cell % 9 * 9 + cell // 9 if transpose else cell
                candidates[mapped] &= ~digit_mask(5)
    return SudokuState([0] * 81, candidates)


class SingleDigitPatternTests(unittest.TestCase):
    def assert_effect(self, technique, restrictions, expected, transpose=False):
        state = restrict(*restrictions, transpose=transpose)
        before = (state.grid.copy(), state.candidates.copy())
        steps = technique.find_steps(state)
        self.assertEqual(len(steps), 1, steps)
        mapped = tuple(sorted((c % 9 * 9 + c // 9 if transpose else c, 5) for c in expected))
        self.assertEqual(steps[0].eliminations, mapped)
        self.assertEqual(steps[0].placements, ())
        self.assertEqual(steps[0].technique, technique.name)
        self.assertEqual(steps[0].rating, technique.difficulty)
        self.assertTrue(steps[0].premises)
        self.assertTrue(steps[0].explanation)
        self.assertEqual(steps, technique.find_steps(state))
        self.assertEqual(before, (state.grid, state.candidates))
        after = apply_step(state, steps[0])
        after.validate()
        for cell, digit in mapped:
            self.assertFalse(after.candidates[cell] & digit_mask(digit))
        self.assertEqual(before, (state.grid, state.candidates))

    def assert_negative(self, technique, restrictions):
        state = restrict(*restrictions)
        before = (state.grid.copy(), state.candidates.copy())
        self.assertEqual(technique.find_steps(state), [])
        self.assertEqual(before, (state.grid, state.candidates))

    def test_skyscraper_rows_and_columns(self):
        for transpose in (False, True):
            self.assert_effect(Skyscraper(), ((ROWS[0], (0, 4)), (ROWS[3], (27, 32))), (14, 23, 40, 49), transpose)

    def test_skyscraper_negative_third_candidate(self):
        self.assert_negative(Skyscraper(), ((ROWS[0], (0, 4, 8)), (ROWS[3], (27, 32))))

    def test_skyscraper_negative_unaligned_bases(self):
        self.assert_negative(Skyscraper(), ((ROWS[0], (0, 4)), (ROWS[3], (28, 32))))

    def test_kite_both_orientations(self):
        for transpose in (False, True):
            self.assert_effect(TwoStringKite(), ((ROWS[0], (1, 6)), (COLS[0], (9, 54))), (60,), transpose)

    def test_kite_negative_no_common_box(self):
        self.assert_negative(TwoStringKite(), ((ROWS[0], (3, 6)), (COLS[0], (9, 54))))

    def test_kite_negative_broken_conjugate(self):
        self.assert_negative(TwoStringKite(), ((ROWS[0], (1, 6, 8)), (COLS[0], (9, 54))))

    def test_turbot_box_conjugate_both_orientations(self):
        for transpose in (False, True):
            self.assert_effect(TurbotFish(), ((BOXES[0], (0, 10)), (ROWS[4], (37, 42))), (6,), transpose)

    def test_turbot_includes_skyscraper(self):
        self.assert_effect(TurbotFish(), ((ROWS[0], (0, 4)), (ROWS[3], (27, 32))), (14, 23, 40, 49))

    def test_turbot_negative_broken_box_pair(self):
        self.assert_negative(TurbotFish(), ((BOXES[0], (0, 10, 20)), (ROWS[4], (37, 42))))

    def test_turbot_negative_disconnected_pairs(self):
        self.assert_negative(TurbotFish(), ((BOXES[0], (0, 10)), (ROWS[4], (39, 42))))

    def test_empty_rectangle_grouped_arms_both_orientations(self):
        for transpose in (False, True):
            self.assert_effect(EmptyRectangle(), ((BOXES[0], (1, 2, 9, 18)), (COLS[4], (4, 40))), (36,), transpose)

    def test_empty_rectangle_intersection_candidate_is_valid(self):
        self.assert_effect(EmptyRectangle(), ((BOXES[0], (0, 1, 2, 9, 18)), (COLS[4], (4, 40))), (36,))

    def test_empty_rectangle_two_candidate_box(self):
        self.assert_effect(EmptyRectangle(), ((BOXES[0], (1, 9)), (COLS[4], (4, 40))), (36,))

    def test_empty_rectangle_different_box(self):
        self.assert_effect(EmptyRectangle(), ((BOXES[4], (31, 32, 39, 48)), (COLS[7], (34, 70))), (66,))

    def test_empty_rectangle_negative_candidate_outside_arms(self):
        self.assert_negative(EmptyRectangle(), ((BOXES[0], (1, 2, 9, 18, 20)), (COLS[4], (4, 40))))

    def test_empty_rectangle_negative_broken_external_pair(self):
        self.assert_negative(EmptyRectangle(), ((BOXES[0], (1, 2, 9, 18)), (COLS[4], (4, 40, 76))))

    def test_empty_rectangle_negative_only_one_arm(self):
        self.assert_negative(EmptyRectangle(), ((BOXES[0], (0, 1, 2)), (COLS[4], (4, 40))))


if __name__ == "__main__":
    unittest.main()
