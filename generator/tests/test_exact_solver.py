import unittest

from generator.solver.exact_solver import count_solutions, has_unique_solution, solve_one
from generator.sudoku.grid import is_complete, is_consistent

PUZZLE = list(map(int, '530070000600195000098000060800060003400803001700020006060000280000419005000080079'))
SOLUTION = list(map(int, '534678912672195348198342567859761423426853791713924856961537284287419635345286179'))


class ExactSolverTests(unittest.TestCase):
    def test_known_unique_solution(self):
        board = PUZZLE.copy()
        self.assertEqual(solve_one(board), SOLUTION)
        self.assertEqual(count_solutions(board), 1)
        self.assertTrue(has_unique_solution(board))
        self.assertEqual(board, PUZZLE)

    def test_complete_and_one_missing(self):
        self.assertEqual(count_solutions(SOLUTION), 1)
        self.assertEqual(solve_one(SOLUTION), SOLUTION)
        self.assertIsNot(solve_one(SOLUTION), SOLUTION)
        board = SOLUTION.copy()
        board[80] = 0
        self.assertEqual(solve_one(board), SOLUTION)

    def test_conflicting_givens_have_no_solution(self):
        for a, b in ((0, 8), (0, 72), (0, 10)):
            board = [0] * 81
            board[a] = board[b] = 1
            original = board.copy()
            self.assertEqual(count_solutions(board), 0)
            self.assertIsNone(solve_one(board))
            self.assertFalse(has_unique_solution(board))
            self.assertEqual(board, original)

    def test_unsatisfiable_without_duplicate_givens(self):
        board = PUZZLE.copy()
        board[2] = 1  # Legal against givens, but the unique solution needs 4.
        self.assertTrue(is_consistent(board))
        original = board.copy()
        self.assertEqual(count_solutions(board), 0)
        self.assertIsNone(solve_one(board))
        self.assertFalse(has_unique_solution(board))
        self.assertEqual(board, original)

    def test_multiple_solutions_and_early_limit(self):
        # Enumerating the full empty grid is infeasible; this also guards cutoff.
        board = [0] * 81
        for limit in (1, 2, 3):
            self.assertEqual(count_solutions(board, limit), limit)
        self.assertFalse(has_unique_solution(board))
        self.assertTrue(is_complete(solve_one(board)))
        self.assertEqual(board, [0] * 81)
        # Swap all 1s and 2s to exhibit two completions of this fixed puzzle.
        two_digits_missing = [0 if n in (1, 2) else n for n in SOLUTION]
        self.assertEqual(count_solutions(two_digits_missing), 2)

    def test_invalid_input_and_limits(self):
        for function in (solve_one, count_solutions, has_unique_solution):
            for board in ([], None, '0' * 81, [True] + [0] * 80):
                with self.assertRaises(ValueError):
                    function(board)
        for limit in (0, -1, True, 2.0, None):
            with self.assertRaises(ValueError):
                count_solutions(PUZZLE, limit)
