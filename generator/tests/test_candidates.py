import unittest

from generator.sudoku.candidates import ALL, SudokuState, digit_mask, mask_digits
from generator.sudoku.grid import PEERS


class CandidateTests(unittest.TestCase):
    def test_masks(self):
        self.assertEqual(ALL, 511)
        self.assertEqual(mask_digits(ALL), tuple(range(1, 10)))
        self.assertEqual(mask_digits(0), ())
        for digit in range(1, 10):
            self.assertEqual(mask_digits(digit_mask(digit)), (digit,))
        for bad in (0, 10, True, 1.0):
            with self.assertRaises(ValueError):
                digit_mask(bad)
        for bad in (-1, 512, True, 1.0):
            with self.assertRaises(ValueError):
                mask_digits(bad)

    def test_candidates_from_givens(self):
        board = [0] * 81
        board[0], board[10] = 1, 2
        state = SudokuState(board)
        self.assertEqual(state.candidates[0], 0)
        self.assertEqual(mask_digits(state.candidates[1]), (3, 4, 5, 6, 7, 8, 9))
        self.assertEqual(state.candidates[80], ALL)
        board[0] = 9
        self.assertEqual(state.grid[0], 1)

    def test_place_updates_only_peers_and_preserves_eliminations(self):
        state = SudokuState([0] * 81)
        state.eliminate(80, 9)
        state.eliminate(1, 8)
        state.place(0, 1)
        self.assertEqual(state.grid[0], 1)
        self.assertEqual(state.candidates[0], 0)
        for peer in PEERS[0]:
            self.assertFalse(state.candidates[peer] & 1)
        self.assertFalse(state.candidates[1] & digit_mask(8))
        self.assertEqual(state.candidates[80], ALL & ~digit_mask(9))
        self.assertFalse(state.is_solved)

    def test_explicit_masks_and_copy_are_independent(self):
        masks = [ALL] * 81
        masks[0] = 3
        state = SudokuState([0] * 81, masks)
        clone = state.copy()
        masks[0] = ALL
        clone.eliminate(0, 1)
        self.assertEqual(state.candidates[0], 3)
        self.assertEqual(clone.candidates[0], 2)
        self.assertEqual(clone.grid[0], 0)  # No implicit singles.

    def test_failed_mutations_are_atomic(self):
        masks = [ALL] * 81
        masks[0] = masks[1] = 1
        state = SudokuState([0] * 81, masks)
        before = state.copy()
        for operation in (lambda: state.place(0, 1), lambda: state.eliminate(0, 1),
                          lambda: state.place(0, 9)):
            with self.assertRaises(ValueError):
                operation()
            self.assertEqual(state.grid, before.grid)
            self.assertEqual(state.candidates, before.candidates)

    def test_missing_unit_support_is_rejected_atomically(self):
        state = SudokuState([0] * 81)
        for cell in range(8):
            state.eliminate(cell, 9)
        before = state.candidates.copy()
        with self.assertRaises(ValueError):
            state.eliminate(8, 9)
        self.assertEqual(state.candidates, before)

    def test_invalid_candidate_states(self):
        for masks in ([ALL] * 80, [0] + [ALL] * 80,
                      [512] + [ALL] * 80, [True] + [ALL] * 80,
                      [ALL & ~1] * 9 + [ALL] * 72):
            with self.assertRaises(ValueError):
                SudokuState([0] * 81, masks)
        board = [0] * 81
        board[0] = 1
        with self.assertRaises(ValueError):
            SudokuState(board, [ALL] * 81)
        with self.assertRaises(ValueError):
            SudokuState(board, [0] + [ALL] * 80)
        board[1] = 1
        with self.assertRaises(ValueError):
            SudokuState(board)

    def test_solved_state_and_filled_mutations(self):
        board = [(r * 3 + r // 3 + c) % 9 + 1 for r in range(9) for c in range(9)]
        state = SudokuState(board)
        self.assertTrue(state.is_solved)
        self.assertEqual(state.candidates, [0] * 81)
        with self.assertRaises(ValueError):
            state.place(0, 1)
        with self.assertRaises(ValueError):
            state.eliminate(0, 1)
