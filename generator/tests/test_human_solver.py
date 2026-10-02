import ast
import inspect
import unittest
from unittest.mock import patch

from generator.sudoku.candidates import SudokuState
from generator.solver import human_solver
from generator.solver.human_solver import HumanSolver, apply_step
from generator.solver.models import LogicStep
from generator.solver.techniques import FullHouse, NakedSingle, default_techniques, phase1_techniques
from generator.solver.techniques.base import Technique


PUZZLE = [int(c) for c in "530070000600195000098000060800060003400803001700020006060000280000419005000080079"]
SOLUTION = [int(c) for c in "534678912672195348198342567859761423426853791713924856961537284287419635345286179"]


class HumanSolverTests(unittest.TestCase):
    def test_known_puzzle_and_metrics(self):
        original = PUZZLE.copy()
        result = HumanSolver().solve(PUZZLE)
        self.assertTrue(result.solved)
        self.assertFalse(result.invalid or result.stuck)
        self.assertEqual(result.grid, SOLUTION)
        self.assertEqual(PUZZLE, original)
        self.assertEqual(sum(result.technique_counts.values()), len(result.steps))
        self.assertEqual(result.max_rating, max(s.rating for s in result.steps))
        self.assertEqual(result.total_score, sum(s.rating ** 2 for s in result.steps))
        self.assertEqual(result.advanced_steps, 0)
        self.assertEqual(result.bottlenecks, [])
        self.assertFalse(result.used_backtracking)
        self.assertEqual(result.guesses, 0)

    def test_deterministic_replay_and_easiest_available_at_each_step(self):
        result = HumanSolver().solve(PUZZLE)
        self.assertEqual(result, HumanSolver().solve(PUZZLE))
        state = SudokuState(PUZZLE)
        for step in result.steps:
            self.assertEqual(step.rating, HumanSolver().minimum_available_rating(state))
            state = apply_step(state, step)
            state.validate()
        self.assertEqual(state.grid, SOLUTION)

    def test_solved_input_has_empty_path(self):
        result = HumanSolver().solve(SOLUTION)
        self.assertTrue(result.solved)
        self.assertEqual(result.steps, [])
        self.assertIsNone(result.hardest_technique)
        self.assertEqual(result.total_score, 0)

    def test_stuck_and_empty_registry_do_not_guess(self):
        for result in (HumanSolver().solve([0] * 81), HumanSolver([]).solve(PUZZLE)):
            self.assertTrue(result.stuck)
            self.assertFalse(result.solved or result.invalid or result.used_backtracking)
            self.assertEqual(result.guesses, 0)
            self.assertEqual(result.steps, [])

    def test_invalid_input(self):
        duplicate = PUZZLE.copy()
        duplicate[2] = 5
        no_candidate = [1, 2, 3, 4, 5, 6, 7, 8, 0] + [0] * 72
        no_candidate[17] = 9
        for grid in (duplicate, no_candidate):
            with self.subTest(grid=grid):
                result = HumanSolver().solve(grid)
                self.assertTrue(result.invalid)
                self.assertFalse(result.solved or result.stuck)

    def test_malformed_input_raises_value_error(self):
        for grid in ([], [0] * 80, [10] * 81, [True] * 81, [0.0] * 81, None):
            with self.subTest(grid=grid), self.assertRaises(ValueError):
                HumanSolver().solve(grid)

    def test_real_puzzle_deductions_against_independent_exact_oracle(self):
        # Fixed minimal puzzles from full-grid/clue-removal seeds 11, 75, 106.
        # Together they exercise every elimination technique on actual clues.
        # Exact solving is an independent test oracle, never a human dependency.
        from generator.solver.exact_solver import count_solutions, solve_one

        puzzles = (
            "060098000004100000700002100010000900008005000002400080000670800005000003000809004",
            "050064009020300000000000700000001042209080076000000080090730200410000000036000000",
            "001070086000000004000682000820010907700004000010000000040108390000090002090000800",
        )
        seen = set()
        for text in puzzles:
            puzzle = [int(c) for c in text]
            self.assertEqual(count_solutions(puzzle), 1)
            solution = solve_one(puzzle)
            result = HumanSolver(phase1_techniques()).solve(puzzle)
            self.assertFalse(result.invalid)
            self.assertTrue(result.stuck)  # Phase 1 must stop honestly here.
            state = SudokuState(puzzle)
            for step in result.steps:
                for cell, digit in step.placements:
                    self.assertEqual(solution[cell], digit)
                for cell, digit in step.eliminations:
                    self.assertNotEqual(solution[cell], digit)
                    forced = puzzle.copy()
                    forced[cell] = digit
                    self.assertEqual(count_solutions(forced), 0)
                    seen.add(step.technique)
                state = apply_step(state, step)
                state.validate()
            self.assertEqual(state.grid, result.grid)
        self.assertEqual(seen, {"Locked Candidates", "Naked Pair", "Hidden Pair",
                                "Naked Triple", "Hidden Triple"})

    def test_configurable_weights_and_validation(self):
        grid = SOLUTION.copy()
        grid[0] = 0
        result = HumanSolver(weights={"Full House": 7, "Naked Single": 0.1}).solve(grid)
        self.assertEqual(result.steps[0].technique, "Naked Single")
        self.assertEqual(result.steps[0].rating, 0.1)
        for weights in ({"missing": 1}, {"Full House": -1}, {"Full House": float("nan")}):
            with self.assertRaises(ValueError):
                HumanSolver(weights=weights)
        with self.assertRaises(ValueError):
            HumanSolver([], weights={})

    def test_custom_plugin_priority_restart_and_stable_step_selection(self):
        calls = []

        class Easy(Technique):
            name, difficulty = "Easy test plugin", 1

            def find_steps(self, state):
                calls.append("easy")
                if state.grid[0] and not state.grid[1]:
                    return [self.step(placements=((1, 3),))]
                return []

        class Hard(Technique):
            name, difficulty = "Hard test plugin", 2

            def find_steps(self, state):
                calls.append("hard")
                if not state.grid[0]:
                    return [self.step(placements=((1, 3),)), self.step(placements=((0, 5),))]
                return []

        grid = SOLUTION.copy()
        grid[0] = grid[1] = 0
        result = HumanSolver([Hard(), Easy()]).solve(grid)
        self.assertTrue(result.solved)
        self.assertEqual(calls, ["easy", "hard", "easy"])
        self.assertEqual([s.placements for s in result.steps], [((0, 5),), ((1, 3),)])

    def test_no_exact_fallback(self):
        from generator.solver import exact_solver
        with patch.object(exact_solver, "solve_one", side_effect=AssertionError("Exact solver called")), \
             patch.object(exact_solver, "count_solutions", side_effect=AssertionError("Exact solver called")):
            self.assertTrue(HumanSolver().solve(PUZZLE).solved)
            self.assertTrue(HumanSolver().solve([0] * 81).stuck)
        tree = ast.parse(inspect.getsource(human_solver))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any("exact" in name or "solution_generator" in name for name in imports))

    def test_apply_step_is_atomic_and_rejects_no_progress(self):
        state = SudokuState(PUZZLE)
        before = state.copy()
        for step in (LogicStep("bad", 1), LogicStep("bad", 1, placements=((0, 5),)),
                     LogicStep("bad", 1, eliminations=((2, 5),))):
            with self.assertRaises(ValueError):
                apply_step(state, step)
            self.assertEqual(state.grid, before.grid)
            self.assertEqual(state.candidates, before.candidates)


if __name__ == "__main__":
    unittest.main()
