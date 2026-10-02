import unittest

from generator.sudoku.grid import (
    ALL_UNITS, BOXES, COLS, PEERS, ROWS, UNITS,
    box_of, col_of, is_complete, is_consistent, row_of, validate_grid,
)


class GridTests(unittest.TestCase):
    def test_topology(self):
        self.assertEqual(len(ALL_UNITS), 27)
        for family in (ROWS, COLS, BOXES):
            self.assertEqual(sorted(cell for unit in family for cell in unit), list(range(81)))
        for cell in range(81):
            self.assertEqual(len(PEERS[cell]), 20)
            self.assertNotIn(cell, PEERS[cell])
            self.assertEqual(len(UNITS[cell]), 3)
            self.assertTrue(all(cell in unit and len(unit) == 9 for unit in UNITS[cell]))
            self.assertTrue(all(cell in PEERS[peer] for peer in PEERS[cell]))
        self.assertEqual((row_of(80), col_of(80), box_of(80)), (8, 8, 8))
        self.assertEqual(box_of(40), 4)

    def test_validation_copies_and_rejects_malformed_input(self):
        board = [0] * 81
        self.assertEqual(validate_grid(board), board)
        self.assertIsNot(validate_grid(board), board)
        for bad in (None, [], [0] * 80, [0] * 82, '0' * 81,
                    [True] + [0] * 80, [1.0] + [0] * 80,
                    [-1] + [0] * 80, [10] + [0] * 80):
            with self.subTest(bad=str(bad)[:20]), self.assertRaises(ValueError):
                validate_grid(bad)

    def test_conflicts_and_completion(self):
        self.assertTrue(is_consistent([0] * 81))
        self.assertFalse(is_complete([0] * 81))
        for a, b in ((0, 8), (0, 72), (0, 10)):
            board = [0] * 81
            board[a] = board[b] = 1
            self.assertFalse(is_consistent(board))
        board = [(r * 3 + r // 3 + c) % 9 + 1 for r in range(9) for c in range(9)]
        self.assertTrue(is_complete(board))
        board[80] = board[79]
        self.assertFalse(is_complete(board))

    def test_invalid_cells(self):
        for function in (row_of, col_of, box_of):
            for cell in (-1, 81, True, 0.5):
                with self.assertRaises(ValueError):
                    function(cell)
