"""Wing premises, precise effects and read-only detection on candidate states."""

import unittest

from generator.solver.human_solver import apply_step
from generator.solver.techniques.wings import XYWing, XYZWing, WWing
from generator.sudoku.candidates import ALL, SudokuState, digit_mask
from generator.sudoku.grid import BOXES, ROWS


def mask(*digits):
    return sum(digit_mask(d) for d in digits)


def candidate_state(changes, transpose=False):
    candidates = [ALL] * 81
    for cell, value in changes.items():
        candidates[cell % 9 * 9 + cell // 9 if transpose else cell] = value
    return SudokuState([0] * 81, candidates)


class WingTests(unittest.TestCase):
    def assert_effect(self, technique, changes, expected, transpose=False):
        state = candidate_state(changes, transpose)
        before = (state.grid.copy(), state.candidates.copy())
        steps = technique.find_steps(state)
        self.assertEqual(len(steps), 1, steps)
        step = steps[0]
        if transpose:
            expected = [(c % 9 * 9 + c // 9, d) for c, d in expected]
        self.assertEqual(step.eliminations, tuple(sorted(expected)))
        self.assertEqual(step.placements, ())
        self.assertEqual(step.technique, technique.name)
        self.assertEqual(step.rating, technique.difficulty)
        self.assertTrue(step.premises)
        self.assertTrue(step.explanation)
        self.assertEqual(steps, technique.find_steps(state))
        self.assertEqual(before, (state.grid, state.candidates))
        after = apply_step(state, step)
        after.validate()
        for cell, digit in expected:
            self.assertFalse(after.candidates[cell] & digit_mask(digit))
        self.assertEqual(before, (state.grid, state.candidates))
        return state, after

    def assert_no_steps(self, technique, changes):
        state = candidate_state(changes)
        before = (state.grid.copy(), state.candidates.copy())
        self.assertEqual(technique.find_steps(state), [])
        self.assertEqual(before, (state.grid, state.candidates))

    def test_xy_wing_row_column_and_transpose(self):
        changes = {0: mask(1, 2), 4: mask(1, 3), 36: mask(2, 3)}
        for transpose in (False, True):
            with self.subTest(transpose=transpose):
                self.assert_effect(XYWing(), changes, [(40, 3)], transpose)

    def test_xy_wing_box_and_row(self):
        self.assert_effect(XYWing(), {0: mask(4, 5), 10: mask(4, 9), 4: mask(5, 9)},
                           [(1, 9), (2, 9), (12, 9), (13, 9), (14, 9)])

    def test_xy_wing_requires_distinct_pivot_links(self):
        self.assert_no_steps(XYWing(), {0: mask(1, 2), 4: mask(1, 3), 36: mask(1, 3)})

    def test_xy_wing_requires_bivalue_wings_and_visibility(self):
        self.assert_no_steps(XYWing(), {0: mask(1, 2), 4: mask(1, 3, 4), 36: mask(2, 3)})
        self.assert_no_steps(XYWing(), {0: mask(1, 2), 4: mask(1, 3), 50: mask(2, 3)})

    def test_xy_wing_returns_all_distinct_effects(self):
        state = candidate_state({0: mask(1, 2), 4: mask(1, 3), 36: mask(2, 3),
                                 8: mask(1, 4), 72: mask(2, 4)})
        before = (state.grid.copy(), state.candidates.copy())
        steps = XYWing().find_steps(state)
        self.assertEqual([step.eliminations for step in steps], [((40, 3),), ((80, 4),)])
        self.assertEqual(steps, XYWing().find_steps(state))
        for step in steps:
            apply_step(state, step).validate()
        self.assertEqual(before, (state.grid, state.candidates))

    def test_xyz_wing_and_transpose(self):
        changes = {0: mask(1, 2, 3), 1: mask(1, 3), 27: mask(2, 3)}
        for transpose in (False, True):
            with self.subTest(transpose=transpose):
                self.assert_effect(XYZWing(), changes, [(9, 3), (18, 3)], transpose)

    def test_xyz_wing_does_not_eliminate_without_pivot_visibility(self):
        before, after = self.assert_effect(
            XYZWing(), {0: mask(1, 2, 3), 1: mask(1, 3), 27: mask(2, 3)}, [(9, 3), (18, 3)])
        # r4c2 sees both wings, but not r1c1 (the pivot).
        self.assertEqual(before.candidates[28], after.candidates[28])

    def test_xyz_wing_second_box_column_fixture(self):
        self.assert_effect(XYZWing(), {10: mask(4, 7, 9), 11: mask(4, 9), 37: mask(7, 9)},
                           [(1, 9), (19, 9)])

    def test_xyz_wing_requires_two_distinct_subsets_and_pivot_visibility(self):
        self.assert_no_steps(XYZWing(), {0: mask(1, 2, 3), 1: mask(1, 3), 27: mask(1, 3)})
        self.assert_no_steps(XYZWing(), {0: mask(1, 2, 3), 1: mask(1, 3), 28: mask(2, 3)})
        self.assert_no_steps(XYZWing(), {0: mask(1, 2, 3), 1: mask(1, 4), 27: mask(2, 3)})

    def w_fixture(self, box_bridge=False):
        unit, supports = (BOXES[1], (3, 13)) if box_bridge else (ROWS[1], (9, 13))
        changes = {c: ALL & ~mask(1) for c in unit if c not in supports}
        changes.update({0: mask(1, 2), 40: mask(1, 2)})
        return changes

    def test_w_wing_row_and_column_bridge(self):
        for transpose in (False, True):
            with self.subTest(transpose=transpose):
                self.assert_effect(WWing(), self.w_fixture(), [(4, 2), (36, 2)], transpose)

    def test_w_wing_box_bridge(self):
        self.assert_effect(WWing(), self.w_fixture(box_bridge=True), [(4, 2), (36, 2)])

    def test_w_wing_can_link_the_other_digit(self):
        changes = {c: ALL & ~mask(2) for c in ROWS[1] if c not in (9, 13)}
        changes.update({0: mask(1, 2), 40: mask(1, 2)})
        self.assert_effect(WWing(), changes, [(4, 1), (36, 1)])

    def test_w_wing_requires_strong_bridge(self):
        changes = self.w_fixture()
        changes[17] = ALL
        self.assert_no_steps(WWing(), changes)

    def test_w_wing_requires_both_wing_connections(self):
        changes = self.w_fixture()
        changes[13] = ALL & ~mask(1)
        changes[16] = ALL
        self.assert_no_steps(WWing(), changes)

    def test_w_wing_requires_identical_bivalue_wings(self):
        changes = self.w_fixture()
        changes[40] = mask(1, 3)
        self.assert_no_steps(WWing(), changes)

    def test_wings_without_effect_are_not_steps(self):
        fixtures = (
            (XYWing(), {0: mask(1, 2), 4: mask(1, 3), 36: mask(2, 3), 40: ALL & ~mask(3)}),
            (XYZWing(), {0: mask(1, 2, 3), 1: mask(1, 3), 27: mask(2, 3),
                         9: ALL & ~mask(3), 18: ALL & ~mask(3)}),
            (WWing(), {**self.w_fixture(), 4: ALL & ~mask(2), 36: ALL & ~mask(2)}),
        )
        for technique, changes in fixtures:
            with self.subTest(technique=technique.name):
                self.assert_no_steps(technique, changes)


if __name__ == "__main__":
    unittest.main()
