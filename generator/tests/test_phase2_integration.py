"""Real clue puzzles: frozen Phase 1 stalls and Phase 2 solves by replayable logic."""

import ast
import inspect
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from generator.solver import exact_solver, human_solver
from generator.solver.human_solver import HumanSolver, apply_step
from generator.solver.techniques import (
    DEFAULT_WEIGHTS, INTERMEDIATE_TECHNIQUE_NAMES, TECHNIQUE_TYPES,
    default_techniques, phase1_techniques, phase2_techniques,
)
from generator.sudoku.candidates import SudokuState
from generator.sudoku.grid import is_complete


FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "phase2_puzzles.json")
                      .read_text(encoding="utf-8"))


class Phase2IntegrationTests(unittest.TestCase):
    def assert_puzzle(self, technique_name):
        fixture = next(f for f in FIXTURES if f["required_technique"] == technique_name)
        puzzle = [int(digit) for digit in fixture["puzzle"]]
        original = puzzle.copy()
        # Exact solving checks only the input's uniqueness, outside HumanSolver.
        self.assertEqual(exact_solver.count_solutions(puzzle, limit=2), 1)
        basic = HumanSolver(phase1_techniques()).solve(puzzle)
        self.assertTrue(basic.stuck)
        self.assertFalse(basic.invalid or basic.solved)
        self.assertEqual(basic.intermediate_steps, 0)
        with patch.object(exact_solver, "solve_one", side_effect=AssertionError("No exact fallback")), \
             patch.object(exact_solver, "count_solutions", side_effect=AssertionError("No exact fallback")), \
             patch.object(exact_solver, "has_unique_solution", side_effect=AssertionError("No exact fallback")):
            result = HumanSolver().solve(puzzle)
            self.assertEqual(result, HumanSolver().solve(puzzle))
        self.assertTrue(result.solved)
        self.assertFalse(result.stuck or result.invalid or result.used_backtracking)
        self.assertEqual(result.guesses, 0)
        self.assertTrue(is_complete(result.grid))
        self.assertGreater(result.technique_counts.get(technique_name, 0), 0)
        self.assertGreater(result.intermediate_steps, 0)
        self.assertEqual(result.intermediate_steps,
                         sum(count for name, count in result.technique_counts.items()
                             if name in INTERMEDIATE_TECHNIQUE_NAMES))
        self.assertEqual(sum(result.technique_counts.values()), len(result.steps))
        self.assertEqual(result.max_rating, max(step.rating for step in result.steps))
        self.assertEqual(result.total_score, sum(step.rating ** 2 for step in result.steps))
        self.assertIn(result.hardest_technique,
                      {s.technique for s in result.steps if s.rating == result.max_rating})
        state = SudokuState(puzzle)
        techniques = phase2_techniques()
        for step in result.steps:
            easiest = min(t.difficulty for t in techniques if t.find_steps(state))
            self.assertEqual(step.rating, easiest)
            state = apply_step(state, step)
            state.validate()
        self.assertEqual(state.grid, result.grid)
        self.assertEqual(puzzle, original)

    def test_x_wing_puzzle(self):
        self.assert_puzzle("X-Wing")

    def test_swordfish_puzzle(self):
        self.assert_puzzle("Swordfish")

    def test_xy_wing_puzzle(self):
        self.assert_puzzle("XY-Wing")

    def test_default_order_and_weights(self):
        expected = ["Full House", "Naked Single", "Hidden Single", "Locked Candidates",
                    "Naked Pair", "Hidden Pair", "Naked Triple", "Hidden Triple",
                    "Naked Quad", "Hidden Quad", "X-Wing", "Skyscraper", "2-String Kite",
                    "Turbot Fish", "Empty Rectangle", "Swordfish", "XY-Wing", "XYZ-Wing",
                    "W-Wing", "Jellyfish"]
        self.assertEqual([t.name for t in HumanSolver(phase2_techniques()).techniques], expected)
        self.assertEqual(set(DEFAULT_WEIGHTS) & set(expected), set(expected))
        self.assertEqual([t.name for t in phase1_techniques()], expected[:8])
        for cls in TECHNIQUE_TYPES:
            self.assertEqual(cls().difficulty, DEFAULT_WEIGHTS[cls.name])

    def test_intermediate_count_does_not_depend_on_custom_weight(self):
        fixture = next(f for f in FIXTURES if f["required_technique"] == "XY-Wing")
        result = HumanSolver(weights={"XY-Wing": 0.1}).solve([int(c) for c in fixture["puzzle"]])
        self.assertTrue(result.solved)
        self.assertGreater(result.technique_counts.get("XY-Wing", 0), 0)
        self.assertGreaterEqual(result.intermediate_steps, result.technique_counts["XY-Wing"])
        self.assertTrue(all(s.rating == 0.1 for s in result.steps if s.technique == "XY-Wing"))

    def test_candidate_techniques_do_not_import_exact_or_solution_generator(self):
        modules = {inspect.getmodule(cls) for cls in TECHNIQUE_TYPES} | {human_solver}
        for module in modules:
            with self.subTest(module=module.__name__):
                tree = ast.parse(inspect.getsource(module))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        names = [node.module or ""] + [alias.name for alias in node.names]
                    elif isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    else:
                        continue
                    self.assertFalse(any("exact_solver" in n or "solution_generator" in n
                                         for n in names))


if __name__ == "__main__":
    unittest.main()
