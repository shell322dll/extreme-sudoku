"""Validated clues, full proof replay and the exact/human dependency boundary."""

import ast
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from generator.solver import exact_solver
from generator.solver.human_solver import HumanSolver, apply_step, all_available_steps
from generator.solver.techniques import (
    phase1_techniques, phase2_techniques, advanced_techniques,
    ADVANCED_TECHNIQUE_NAMES, DEFAULT_WEIGHTS, TECHNIQUE_TYPES,
)
from generator.solver.techniques.chains import InferenceGraph
from generator.solver.techniques.forcing import logical_clauses
from generator.sudoku.candidates import SudokuState


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((Path(__file__).parent / "fixtures/phase3_puzzles.json").read_text())


class Phase3IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validated = {}
        for fixture in FIXTURES:
            text = fixture["puzzle"]
            if text not in cls.validated:
                puzzle = list(map(int, text))
                assert exact_solver.count_solutions(puzzle, 2) == 1
                solution = exact_solver.solve_one(puzzle)
                assert "".join(map(str, solution)) == fixture["solution"]
                cls.validated[text] = (puzzle, solution)

    def replay(self, puzzle, solution, result, solver):
        self.assertTrue(result.solved)
        self.assertFalse(result.invalid or result.stuck or result.used_backtracking)
        self.assertEqual(result.guesses, 0)
        self.assertEqual(result.grid, solution)
        state = SudokuState(puzzle)
        for step in result.steps:
            self.assertEqual(step.rating, solver.minimum_available_rating(state))
            for cell, digit in step.eliminations:
                self.assertNotEqual(solution[cell], digit, step)
            for cell, digit in step.placements:
                self.assertEqual(solution[cell], digit, step)
            if step.chain and not step.als:
                mode = "x" if step.technique == "X-Chain" else "xy" if step.technique == "XY-Chain" else "aic"
                self.assertTrue(InferenceGraph(state, mode=mode, grouped=bool(step.grouped_nodes)).valid_chain(step.chain))
            if step.assumptions:
                clauses = logical_clauses(state)
                for proof in step.assumptions:
                    for index, inference in enumerate(proof.inferences):
                        self.assertTrue(all(parent < index for parent in inference.parents))
                        if inference.rule != "assumption":
                            self.assertIn(inference.clause, clauses)
            state = apply_step(state, step)
        self.assertEqual(state.grid, solution)
        self.assertEqual(result.advanced_steps, sum(s.technique in ADVANCED_TECHNIQUE_NAMES for s in result.steps))
        self.assertEqual(result.chain_step_count, sum(bool(s.chain or s.assumptions) for s in result.steps))
        self.assertEqual(result.longest_chain, max(s.chain_length for s in result.steps))
        self.assertEqual(result.als_step_count, sum(bool(s.als) for s in result.steps))
        self.assertEqual(result.forcing_step_count, sum(bool(s.assumptions) for s in result.steps))

    def test_basic_stuck_intermediate_stuck_advanced_solved(self):
        for text, (puzzle, solution) in self.validated.items():
            with self.subTest(puzzle=text):
                self.assertTrue(HumanSolver(phase1_techniques()).solve(puzzle).stuck)
                self.assertTrue(HumanSolver(phase2_techniques()).solve(puzzle).stuck)
                solver = HumanSolver()
                result = solver.solve(puzzle)
                self.assertEqual(result, solver.solve(puzzle))
                self.replay(puzzle, solution, result, solver)
                self.assertGreater(result.advanced_steps, 0)
                self.assertEqual(puzzle, list(map(int, text)))

    def test_target_repertoires_solve_with_required_technique(self):
        techniques = {t.name: t for t in advanced_techniques()}
        for fixture in FIXTURES:
            puzzle, solution = self.validated[fixture["puzzle"]]
            with self.subTest(fixture=fixture["id"]):
                if fixture["target_repertoire"] == "default":
                    solver = HumanSolver()
                    expected = fixture["target_techniques"]
                else:
                    expected = [fixture["target_technique"]]
                    solver = HumanSolver(phase2_techniques() + [techniques[expected[0]]])
                result = solver.solve(puzzle)
                self.assertEqual(result, solver.solve(puzzle))
                for name in expected:
                    self.assertGreater(result.technique_counts.get(name, 0), 0)
                self.replay(puzzle, solution, result, solver)

    def test_every_available_bounded_deduction_matches_independent_solution(self):
        puzzle, solution = self.validated[FIXTURES[0]["puzzle"]]
        phase2 = HumanSolver(phase2_techniques()).solve(puzzle)
        state = SudokuState(puzzle)
        for step in phase2.steps:
            state = apply_step(state, step)
        before = (state.grid[:], state.candidates[:])
        steps = all_available_steps(state)
        self.assertTrue(steps)
        self.assertEqual(min(s.rating for s in steps), HumanSolver().minimum_available_rating(state))
        for step in steps:
            for cell, digit in step.placements:
                self.assertEqual(solution[cell], digit, step)
            for cell, digit in step.eliminations:
                self.assertNotEqual(solution[cell], digit, step)
        self.assertEqual(before, (state.grid, state.candidates))

    def test_registry_weights_and_metrics_are_backwards_compatible(self):
        self.assertEqual([t.name for t in HumanSolver().techniques][-10:],
                         ["X-Chain", "XY-Chain", "AIC", "Nice Loop", "Grouped AIC", "ALS-XZ",
                          "ALS-XY-Wing", "ALS Chain", "Forcing Chain", "Nishio"])
        self.assertEqual(set(DEFAULT_WEIGHTS), {cls.name for cls in TECHNIQUE_TYPES})
        self.assertEqual(len(phase2_techniques()), 20)
        fixture = next(f for f in FIXTURES if f.get("target_technique") == "X-Chain")
        result = HumanSolver(weights={"X-Chain": 0.1}).solve(list(map(int, fixture["puzzle"])))
        self.assertGreater(result.advanced_steps, 0)
        self.assertGreater(result.technique_counts.get("X-Chain", 0), 0)

    def test_runtime_exact_api_traps_for_all_advanced_detectors(self):
        puzzle, _ = self.validated[FIXTURES[0]["puzzle"]]
        state = SudokuState(puzzle)
        for step in HumanSolver(phase2_techniques()).solve(puzzle).steps:
            state = apply_step(state, step)
        with ExitStack() as stack:
            for name in ("solve_one", "count_solutions", "has_unique_solution"):
                stack.enter_context(patch.object(exact_solver, name, side_effect=AssertionError("Exact API forbidden")))
            for technique in advanced_techniques():
                technique.find_steps(state)
            self.assertTrue(HumanSolver().solve(puzzle).solved)

    def test_dependency_boundary_static_and_clean_process(self):
        solver_dir = ROOT / "solver"
        paths = list((solver_dir / "techniques").glob("*.py")) + list((ROOT / "sudoku").glob("*.py"))
        paths += [solver_dir / n for n in ("human_solver.py", "models.py", "advanced_config.py", "__init__.py")]
        forbidden = ("exact_solver", "count_solutions", "solve_one", "has_unique_solution",
                     "solution_generator", "clue_generator", "backtracking", "dfs")
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [alias.name for alias in node.names] + [getattr(node, "module", "") or ""]
                    self.assertFalse(any(word in name.lower() for name in names for word in forbidden), path)
                    self.assertFalse(any(name.startswith(("importlib", "subprocess")) for name in names), path)
                elif isinstance(node, ast.Call):
                    name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                    self.assertNotIn(name, ("eval", "exec", "__import__", "open") + forbidden, path)
        script = """
import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if 'exact_solver' in name or 'solution_generator' in name or 'clue_generator' in name:
        raise AssertionError('Forbidden dependency: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from generator.solver.human_solver import HumanSolver
result = HumanSolver().solve(list(map(int, sys.argv[1])))
assert result.solved and not result.used_backtracking
assert not any('exact_solver' in name for name in sys.modules)
"""
        subprocess.run([sys.executable, "-c", script, FIXTURES[0]["puzzle"]],
                       cwd=ROOT.parent, check=True, capture_output=True, text=True)

    def test_hash_seed_does_not_change_solution_path(self):
        script = """
import hashlib, sys
from generator.solver.human_solver import HumanSolver
print(hashlib.sha256(repr(HumanSolver().solve(list(map(int,sys.argv[1])))).encode()).hexdigest())
"""
        outputs = []
        for seed in ("1", "974"):
            result = subprocess.run([sys.executable, "-c", script, FIXTURES[-1]["puzzle"]],
                                    cwd=ROOT.parent, env={**os.environ, "PYTHONHASHSEED": seed},
                                    check=True, capture_output=True, text=True)
            outputs.append(result.stdout)
        self.assertEqual(*outputs)


if __name__ == "__main__":
    unittest.main()
