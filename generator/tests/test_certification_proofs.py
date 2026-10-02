"""Certificates are checked independently of the code that discovers them."""

from dataclasses import replace
from pathlib import Path
import ast
import json
import random
import unittest
from unittest.mock import patch

from generator.certification.proofs import validate_step, validate_path
from generator.solver.advanced_config import AdvancedConfig
from generator.solver.human_solver import HumanSolver
from generator.solver.models import CandidateNode, LogicStep
from generator.solver.techniques import default_techniques, advanced_techniques, phase2_techniques
from generator.solver.techniques.forcing import propagate, proof_for
from generator.solution_generator import generate_solution
from generator.sudoku.candidates import ALL, SudokuState, digit_mask
from generator.sudoku.grid import ROWS, COLS, BOXES
from generator.tests.test_chains import state_with_cells, restricted_digit
from generator.tests.test_fish import fish_state


def fixtures():
    result = {}
    result["Full House"] = SudokuState(list(range(1, 9)) + [0] * 73)
    result["Naked Single"] = state_with_cells({40: (7,)})
    masks = [ALL] * 81
    for c in ROWS[0][1:]:
        masks[c] &= ~digit_mask(1)
    result["Hidden Single"] = SudokuState([0] * 81, masks)
    result["Locked Candidates"] = restricted_digit((BOXES[0], (0, 1)))
    for size, word in ((2, "Pair"), (3, "Triple"), (4, "Quad")):
        cells = (0, 2, 4, 7)[:size]
        digits = tuple(range(1, size + 1))
        result["Naked " + word] = state_with_cells(dict.fromkeys(cells, digits))
        mapping = {c: tuple(range(size + 1, 10)) for c in ROWS[0] if c not in cells}
        mapping.update({c: digits + (size + 1,) for c in cells})
        result["Hidden " + word] = state_with_cells(mapping)
    result["X-Wing"] = fish_state((0, 3), ({1, 5}, {1, 5}))
    result["Swordfish"] = fish_state((0, 3, 6), ({1, 4}, {4, 7}, {1, 7}))
    result["Jellyfish"] = fish_state((0, 2, 4, 6), ({0, 2}, {2, 4}, {4, 6}, {0, 6}))
    result["Skyscraper"] = restricted_digit((ROWS[0], (0, 4)), (ROWS[3], (27, 32)))
    result["2-String Kite"] = restricted_digit((ROWS[0], (1, 6)), (COLS[0], (9, 54)))
    result["Turbot Fish"] = restricted_digit((BOXES[0], (0, 10)), (ROWS[4], (37, 42)))
    result["Empty Rectangle"] = restricted_digit((BOXES[0], (1, 2, 9, 18)), (COLS[4], (4, 40)))
    result["XY-Wing"] = state_with_cells({0: (1, 2), 4: (1, 3), 36: (2, 3)})
    result["XYZ-Wing"] = state_with_cells({0: (1, 2, 3), 1: (1, 3), 27: (2, 3)})
    mapping = {c: tuple(range(2, 10)) for c in ROWS[1] if c not in (9, 13)}
    mapping.update({0: (1, 2), 40: (1, 2)})
    result["W-Wing"] = state_with_cells(mapping)
    result["X-Chain"] = result["Skyscraper"]
    result["XY-Chain"] = state_with_cells({0: (1, 2), 4: (2, 3), 40: (1, 3)})
    result["AIC"] = result["XY-Chain"]
    result["Nice Loop"] = restricted_digit((ROWS[0], (0, 4)), (ROWS[3], (27, 31)))
    result["Grouped AIC"] = result["Empty Rectangle"]
    result["ALS-XZ"] = state_with_cells({0: (1, 2), 1: (2, 3), 4: (1, 4), 13: (3, 4)})
    result["ALS-XY-Wing"] = result["XY-Chain"]
    result["ALS Chain"] = state_with_cells({0: (1, 2), 4: (2, 3), 40: (3, 4), 36: (1, 4)})
    result["Forcing Chain"] = result["XY-Chain"]
    result["Nishio"] = result["XY-Chain"]
    return result


class CertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.states = fixtures()
        cls.steps = {}
        for technique in default_techniques():
            state = cls.states[technique.name]
            if technique.name == "Nishio":
                proof = proof_for(propagate(state, (36, 1, True)))
                steps = [technique.step(eliminations=((36, 1),), premises=((36, 1, True),),
                                       assumptions=(proof,), contradiction=proof.contradiction)]
            else:
                steps = technique.find_steps(state)
            if not steps:
                raise AssertionError("missing positive fixture for " + technique.name)
            cls.steps[technique.name] = steps

    def check_family(self, name):
        state = self.states[name]
        before = state.signature()
        for step in self.steps[name]:
            result = validate_step(state, step)
            self.assertTrue(result.valid, (name, result.errors, step))
            self.assertFalse(validate_step(state, replace(step, premises=())).valid)
            self.assertFalse(validate_step(state, replace(step, rating=step.rating + .25)).valid)
            # Keep all original premises; attach a live conclusion that the
            # stated proof does not license. No solution oracle reaches checker.
            wrong = replace(step, placements=((80, 9),), eliminations=())
            self.assertFalse(validate_step(state, wrong).valid, (name, wrong))
        self.assertEqual(before, state.signature())

    def test_corrupted_strong_and_weak_links(self):
        state = self.states["AIC"]
        step = self.steps["AIC"][0]
        for index, edge in enumerate(step.chain.links):
            bad = replace(edge, kind="weak" if edge.kind == "strong" else "strong")
            links = step.chain.links[:index] + (bad,) + step.chain.links[index + 1:]
            self.assertFalse(validate_step(state, replace(step, chain=replace(step.chain, links=links))).valid)
            bad = replace(edge, reason=("unit", 26))
            links = step.chain.links[:index] + (bad,) + step.chain.links[index + 1:]
            self.assertFalse(validate_step(state, replace(step, chain=replace(step.chain, links=links))).valid)

    def test_broken_strong_support_and_weak_visibility(self):
        state = self.states["X-Chain"]
        step = self.steps["X-Chain"][0]
        masks = state.candidates[:]
        masks[8] |= digit_mask(5)
        self.assertFalse(validate_step(SudokuState(state.grid, masks), step).valid)
        step = self.steps["AIC"][0]
        node = CandidateNode((80,), step.chain.nodes[1].digit)
        nodes = step.chain.nodes[:1] + (node,) + step.chain.nodes[2:]
        links = tuple(replace(e, source=nodes[i], target=nodes[i + 1]) for i, e in enumerate(step.chain.links))
        self.assertFalse(validate_step(self.states["AIC"], replace(step, chain=replace(step.chain, nodes=nodes, links=links))).valid)

    def test_chain_endpoints_repeated_nodes_and_missing_candidates(self):
        state = self.states["AIC"]
        step = self.steps["AIC"][0]
        self.assertFalse(validate_step(state, replace(step, premises=step.premises[::-1])).valid)
        for bad_node in (step.chain.nodes[0], CandidateNode((-1,), 1), CandidateNode((True,), 1), CandidateNode((80,), 10)):
            nodes = step.chain.nodes[:1] + (bad_node,) + step.chain.nodes[2:]
            chain = replace(step.chain, nodes=nodes)
            self.assertFalse(validate_step(state, replace(step, chain=chain)).valid)

    def test_aic_discontinuities(self):
        state = restricted_digit((ROWS[0], (0, 1)), (COLS[0], (0, 9)))
        detector = next(t for t in default_techniques() if t.name == "AIC")
        steps = [s for s in detector.find_steps(state) if s.chain.closed]
        self.assertTrue(any(s.placements for s in steps))
        self.assertTrue(any(s.eliminations for s in steps))
        for step in steps:
            self.assertTrue(validate_step(state, step).valid)
            self.assertFalse(validate_step(state, replace(step, placements=step.eliminations,
                                                         eliminations=step.placements)).valid)

    def test_grouped_partition_and_metadata(self):
        state = self.states["Grouped AIC"]
        step = next(s for s in self.steps["Grouped AIC"] if (36, 5) in s.eliminations)
        self.assertFalse(validate_step(state, replace(step, grouped_nodes=())).valid)
        masks = state.candidates[:]
        masks[20] |= digit_mask(5)
        self.assertFalse(validate_step(SudokuState(state.grid, masks), step).valid)
        node = step.grouped_nodes[0]
        bad_node = replace(node, cells=node.cells + (80,))
        nodes = tuple(bad_node if n == node else n for n in step.chain.nodes)
        links = tuple(replace(e, source=nodes[i], target=nodes[i + 1]) for i, e in enumerate(step.chain.links))
        corrupt = replace(step, chain=replace(step.chain, nodes=nodes, links=links),
                          grouped_nodes=tuple(n for n in nodes if len(n.cells) > 1), premises=(nodes[0], nodes[-1]))
        self.assertFalse(validate_step(state, corrupt).valid)

    def test_als_corrupted_rcc_and_masks(self):
        for name in ("ALS-XZ", "ALS-XY-Wing", "ALS Chain"):
            state, step = self.states[name], self.steps[name][0]
            edge = replace(step.chain.links[0], digit=9)
            chain = replace(step.chain, links=(edge,) + step.chain.links[1:])
            self.assertFalse(validate_step(state, replace(step, chain=chain)).valid)
            masks = state.candidates[:]
            masks[step.als[0].cells[0]] |= digit_mask(9)
            self.assertFalse(validate_step(SudokuState(state.grid, masks), step).valid)
            self.assertFalse(validate_step(state, replace(step, als=step.als[::-1])).valid)

    def test_forcing_corrupted_conclusion_and_duplicate_branch(self):
        state, step = self.states["Forcing Chain"], self.steps["Forcing Chain"][0]
        self.assertFalse(validate_step(state, replace(step, assumptions=(step.assumptions[0],) * 2)).valid)
        self.assertFalse(validate_step(state, replace(step, placements=(), eliminations=((80, 9),))).valid)
        self.assertFalse(validate_step(state, replace(step, placements=step.eliminations,
                                                     eliminations=step.placements)).valid)

    def test_forcing_nested_assumption_bad_parent_and_fake_clause(self):
        for name in ("Forcing Chain", "Nishio"):
            state, step = self.states[name], self.steps[name][0]
            proof = next(p for p in step.assumptions if len(p.inferences) > 1)
            index = step.assumptions.index(proof)
            for inference in (replace(proof.inferences[-1], rule="assumption"),
                              replace(proof.inferences[-1], parents=(len(proof.inferences),)),
                              replace(proof.inferences[-1], clause=((80, 9),)),
                              replace(proof.inferences[-1], depth=999)):
                bad = replace(proof, inferences=proof.inferences[:-1] + (inference,))
                branches = step.assumptions[:index] + (bad,) + step.assumptions[index + 1:]
                self.assertFalse(validate_step(state, replace(step, assumptions=branches)).valid)

    def test_nishio_fake_contradiction_and_budgets(self):
        state, step = self.states["Nishio"], self.steps["Nishio"][0]
        for contradiction in (("opposite", 0, 0), ("empty-clause", ((80, 9),), (0,)), (), ("budget",)):
            proof = replace(step.assumptions[0], contradiction=contradiction)
            self.assertFalse(validate_step(state, replace(step, assumptions=(proof,), contradiction=contradiction)).valid)
        self.assertFalse(validate_step(state, step, config=AdvancedConfig(max_forcing_nodes=1)).valid)
        self.assertFalse(validate_step(state, self.steps["AIC"][0], config=AdvancedConfig(max_aic_length=1)).valid)

    def test_illegal_targets_givens_and_contradictory_poststate(self):
        state, step = self.states["Naked Single"], self.steps["Naked Single"][0]
        for cell, digit in ((True, 7), (-1, 7), (81, 7), (40, True), (40, 0), (40, 10), (40, 8)):
            self.assertFalse(validate_step(state, replace(step, placements=((cell, digit),))).valid)
        given = SudokuState([7] + [0] * 80)
        self.assertFalse(validate_step(given, replace(step, placements=((0, 7),))).valid)
        contradictory = state_with_cells({0: (1,), 1: (1,)})
        bad = LogicStep("Naked Single", 1, placements=((0, 1),), premises=((0, (1,)),))
        self.assertFalse(validate_step(contradictory, bad).valid)
        self.assertFalse(validate_step(state, replace(step, placements=step.placements * 2)).valid)

    def test_unknown_techniques_nan_and_invalid_state(self):
        state, step = self.states["Naked Single"], self.steps["Naked Single"][0]
        self.assertFalse(validate_step(state, replace(step, technique="Guess")).valid)
        self.assertFalse(validate_step(state, replace(step, rating=float("nan"))).valid)
        state = state.copy()
        state.candidates[80] = 0
        self.assertFalse(validate_step(state, step).valid)

    def test_empty_rectangle_duplicate_bridge_fails_closed(self):
        state, step = self.states["Empty Rectangle"], self.steps["Empty Rectangle"][0]
        pair = step.premises[-1]
        corrupted = replace(step, premises=step.premises[:-1] + ((pair[0], pair[0]),))
        self.assertFalse(validate_step(state, corrupted).valid)

    def test_no_detector_or_exact_solver_calls(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for technique in default_techniques():
                stack.enter_context(patch.object(type(technique), "find_steps", side_effect=AssertionError("detector called")))
            for name in ("solve_one", "count_solutions", "has_unique_solution", "collect_solutions"):
                stack.enter_context(patch("generator.solver.exact_solver." + name, side_effect=AssertionError("exact called")))
            for name, steps in self.steps.items():
                self.assertTrue(validate_step(self.states[name], steps[0]).valid, name)
        source = Path(__file__).parents[1] / "certification" / "proofs.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("exact_solver", node.module or "")
                self.assertNotIn("techniques", node.module or "")

    def test_real_phase3_complete_fresh_replay(self):
        path = Path(__file__).parent / "fixtures" / "phase3_puzzles.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        techniques = {t.name: t for t in default_techniques()}
        for row in rows:
            grid = [int(c) for c in row["puzzle"]]
            target = row.get("target_technique")
            repertoire = phase2_techniques() + [techniques[target]] if target in techniques else default_techniques()
            result = HumanSolver(repertoire).solve(grid)
            self.assertTrue(result.solved, row["id"])
            checked = validate_path(grid, result.steps)
            self.assertTrue(checked.valid, (row["id"], checked.errors))
            self.assertTrue(validate_path(grid, result.steps).valid)
            self.assertFalse(validate_path(grid, result.steps[:-1]).valid)

    def test_varied_advanced_certificates_preserve_oracle_separation(self):
        rng = random.Random(9824)
        config = AdvancedConfig(max_chain_search_nodes=10000, max_als_search_nodes=3000, max_forcing_starts=40)
        counts = {}
        for sample in range(18):
            oracle = generate_solution(sample)
            state = SudokuState([d if rng.random() < .25 else 0 for d in oracle])
            for c, mask in enumerate(state.candidates):
                if mask:
                    state.candidates[c] = digit_mask(oracle[c]) | sum(
                        digit_mask(d) for d in range(1, 10)
                        if d != oracle[c] and mask & digit_mask(d) and rng.random() < .7)
            state.validate()
            for technique in advanced_techniques(config=config):
                for step in technique.find_steps(state):
                    checked = validate_step(state, step, config=config)
                    self.assertTrue(checked.valid, (sample, technique.name, checked.errors, step))
                    counts[technique.name] = counts.get(technique.name, 0) + 1
        self.assertEqual(set(counts), {t.name for t in advanced_techniques()})
        self.assertGreater(sum(counts.values()), 1000)


for _name in fixtures():
    def _check(self, name=_name):
        self.check_family(name)
    setattr(CertificateTests, "test_family_" + _name.lower().replace(" ", "_").replace("-", "_"), _check)


if __name__ == "__main__":
    unittest.main()
