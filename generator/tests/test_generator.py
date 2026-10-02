import random
import unittest
from dataclasses import FrozenInstanceError

from generator.chromosome import Individual
from generator.clue_generator import generate_clue_mask, is_minimal, minimize_puzzle
from generator.solution_generator import generate_solution
from generator.solver.exact_solver import count_solutions, solve_one
from generator.sudoku.grid import ALL_UNITS


class GeneratorTests(unittest.TestCase):
    def test_solutions_are_valid_diverse_and_reproducible(self):
        solutions = []
        rng_state = random.getstate()
        for seed in range(20):
            board = generate_solution(seed)
            self.assertEqual(board, generate_solution(seed))
            self.assertEqual(len(board), 81)
            for unit in ALL_UNITS:
                self.assertEqual({board[cell] for cell in unit}, set(range(1, 10)))
            solutions.append(tuple(board))
        self.assertGreater(len(set(solutions)), 1)
        self.assertEqual(random.getstate(), rng_state)

    def test_chromosome_boundaries_and_immutability(self):
        board = generate_solution(1)
        original = board.copy()
        for mask, count in ((0, 0), ((1 << 81) - 1, 81), (1 | (1 << 80), 2)):
            chromosome = Individual(mask, board)
            self.assertEqual(chromosome.clue_count, count)
            self.assertIsInstance(chromosome.solution, tuple)
            puzzle = chromosome.to_puzzle()
            self.assertEqual(sum(bool(n) for n in puzzle), count)
            self.assertEqual(puzzle, [n if mask & (1 << i) else 0 for i, n in enumerate(board)])
            puzzle[0] = 0
            self.assertEqual(chromosome.solution, tuple(original))
            with self.assertRaises(FrozenInstanceError):
                chromosome.clue_mask = 0
        board[0] = 0
        self.assertEqual(chromosome.solution, tuple(original))

    def test_reject_invalid_chromosomes_and_solutions(self):
        solution = generate_solution(1)
        for mask in (-1, 1 << 81, True, 2.0):
            with self.assertRaises(ValueError):
                Individual(mask, solution)
        for bad in ([0] * 81, [1] * 81, [], [True] * 81):
            for function in (minimize_puzzle, generate_clue_mask):
                with self.assertRaises(ValueError):
                    function(bad)
            with self.assertRaises(ValueError):
                Individual(0, bad)

    def test_generated_puzzles_unique_minimal_and_reproducible(self):
        for seed in (0, 7, 42):
            with self.subTest(seed=seed):
                solution = generate_solution(seed)
                original = solution.copy()
                puzzle = minimize_puzzle(solution, seed)
                self.assertEqual(solution, original)
                self.assertEqual(puzzle, minimize_puzzle(solution, seed))
                self.assertEqual(count_solutions(puzzle), 1)
                self.assertEqual(solve_one(puzzle), solution)
                self.assertTrue(is_minimal(puzzle))
                self.assertLess(sum(bool(n) for n in puzzle), 81)
                for cell, value in enumerate(puzzle):
                    if value:
                        reduced = puzzle.copy()
                        reduced[cell] = 0
                        self.assertEqual(count_solutions(reduced), 2)
                mask = generate_clue_mask(solution, seed)
                self.assertEqual(Individual(mask, solution).to_puzzle(), puzzle)

    def test_minimality_rejects_nonunique_or_redundant_puzzles(self):
        self.assertFalse(is_minimal([0] * 81))
        self.assertFalse(is_minimal([1] * 81))
        self.assertFalse(is_minimal(generate_solution(5)))
