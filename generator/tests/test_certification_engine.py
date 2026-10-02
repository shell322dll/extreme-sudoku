"""Certification gates, genuine logical branching, and budget semantics."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from generator.certification import (CertificationConfig, CertificationResult, CertificationStatus,
    SearchStatus, FailureReason, certify_puzzle, EnumerationResult)
from generator.certification.enumeration import canonical_steps, StepEnumerator
from generator.certification.search import threshold_search
from generator.certification.pipeline import classify_certificate, algorithm_fingerprint
from generator.sudoku.candidates import SudokuState
from generator.solver.techniques.singles import FullHouse, NakedSingle, HiddenSingle
from generator.solver.techniques.chains import XChain
from generator.certification.enum_chains import enumerate_chains
from generator.certification.enum_als import enumerate_als_steps
from generator.certification.enum_forcing import enumerate_forcing
from generator.solver.techniques.als import ALSXZ
from generator.solver.techniques.forcing import ForcingChain

SOLUTION = "123456789456789123789123456214365897365897214897214365531642978642978531978531642"


def almost(*cells):
    grid = list(map(int, SOLUTION))
    for cell in cells:
        grid[cell] = 0
    return grid


class SimpleProvider:
    """A small complete rule catalogue, with real independently checked steps."""
    def __init__(self, technique=FullHouse, incomplete=False):
        self.technique, self.incomplete = technique, incomplete

    def enumerate(self, state, threshold, **kwargs):
        steps = [s for s in self.technique().find_steps(state) if s.rating <= threshold]
        return EnumerationResult(steps, not self.incomplete,
                                 ["CONTROLLED_LIMIT"] if self.incomplete else [])


class CertificationEngineTests(unittest.TestCase):
    def test_config_roundtrip_and_official_scale(self):
        config = CertificationConfig()
        self.assertEqual(config, CertificationConfig.from_dict(json.loads(json.dumps(config.to_dict()))))
        self.assertEqual(config.fingerprint(), CertificationConfig().fingerprint())
        for kwargs in ({"extreme_threshold": 1}, {"required_bottlenecks_extreme": 1},
                       {"ultra_minimum_chain": 1}, {"node_budget": True}, {"time_budget": float("nan")},
                       {"advanced_threshold": 1}, {"max_als_size": 9}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CertificationConfig(**kwargs)

    def test_signature_contains_candidate_masks(self):
        state = SudokuState([0] * 81)
        other = state.copy()
        other.eliminate(0, 1)
        self.assertNotEqual(state.signature(), other.signature())

    def test_effect_dedup_preserves_rating_and_first_proof(self):
        state = SudokuState(almost(0))
        steps = FullHouse().find_steps(state)
        other = NakedSingle().find_steps(state)
        dedup = canonical_steps(steps + steps + other)
        self.assertEqual(len(dedup), 2)
        self.assertEqual([s.rating for s in dedup], [.5, 1])
        self.assertEqual(dedup, canonical_steps(list(reversed(steps + steps + other))))

    def test_threshold_proven_failure_then_real_valid_solution(self):
        cfg = CertificationConfig()
        low = threshold_search(almost(0), 0, cfg)
        right = threshold_search(almost(0), .5, cfg)
        self.assertEqual(low.status, SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)
        self.assertEqual(right.status, SearchStatus.SOLVED)
        self.assertEqual(right.path[0].technique, "Full House")

    def test_alternative_order_avoids_more_expensive_greedy_path(self):
        class AlternateProvider:
            def enumerate(self, state, threshold, **kwargs):
                steps = NakedSingle().find_steps(state)
                cheap = FullHouse().find_steps(state)
                # Solving cell 9 first exposes the cheaper path. A rating-1
                # greedy witness selecting cell 0 exists independently.
                steps += [s for s in cheap if s.placements[0][0] == 9 or state.grid[9]]
                return EnumerationResult([s for s in steps if s.rating <= threshold])
        result = threshold_search(almost(0, 9), .5, CertificationConfig(), enumerator=AlternateProvider())
        self.assertEqual(result.status, SearchStatus.SOLVED)
        self.assertEqual([s.placements[0][0] for s in result.path], [9, 0])
        self.assertEqual(max(s.rating for s in result.path), .5)

    def test_model_requires_highest_allowed_real_technique(self):
        provider = SimpleProvider(HiddenSingle)
        cfg = CertificationConfig()
        self.assertEqual(threshold_search(almost(0), 1, cfg, enumerator=provider).status,
                         SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)
        self.assertEqual(threshold_search(almost(0), 1.2, cfg, enumerator=provider).status,
                         SearchStatus.SOLVED)

    def test_incomplete_empty_enumeration_never_proven(self):
        result = threshold_search(almost(0), 0, CertificationConfig(), enumerator=SimpleProvider(incomplete=True))
        self.assertEqual(result.status, SearchStatus.INCONCLUSIVE_BUDGET)
        self.assertIn("CONTROLLED_LIMIT", result.limit_reasons)

    def test_node_depth_state_and_timeout_limits(self):
        cases = [(CertificationConfig(node_budget=1), "NODE_LIMIT"),
                 (CertificationConfig(max_path_depth=1), "PATH_DEPTH_LIMIT"),
                 (CertificationConfig(state_budget=1), "STATE_LIMIT"),
                 (CertificationConfig(time_budget=0), "TIME_LIMIT")]
        for config, reason in cases:
            with self.subTest(reason=reason):
                result = threshold_search(almost(0, 9, 18), .5, config, enumerator=SimpleProvider())
                self.assertEqual(result.status, SearchStatus.INCONCLUSIVE_BUDGET)
                self.assertIn(reason, result.limit_reasons)

    def test_invalid_proof_search_error(self):
        class Bad:
            def enumerate(self, state, threshold, **kwargs):
                step = FullHouse().find_steps(state)[0]
                return EnumerationResult([replace(step, placements=((0, 2),))])
        result = threshold_search(almost(0), .5, CertificationConfig(), enumerator=Bad())
        self.assertEqual(result.status, SearchStatus.ERROR)
        self.assertIn("Invalid logic proof", result.error)

    def test_fresh_real_easy_certificate_is_rejected_without_misrating(self):
        result = certify_puzzle(almost(0), SOLUTION)
        self.assertEqual(result.status, CertificationStatus.REJECTED)
        self.assertEqual(result.minimum_required_rating, .5)
        self.assertTrue(result.unique and result.human_solved and result.proof_valid and result.reproducible)
        self.assertFalse(result.minimal)
        self.assertEqual(result.failure_reasons, [FailureReason.RATING_BELOW_EXTREME])
        self.assertFalse(result.production_eligible)
        self.assertEqual(result.threshold_results[0].status, SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)

    def test_fresh_uniqueness_and_all_clues_minimality_even_with_fresh_false(self):
        from generator.certification import pipeline
        original = pipeline.count_solutions
        with patch.object(pipeline, "count_solutions", wraps=original) as counter:
            result = certify_puzzle(almost(0), SOLUTION, fresh=False)
        self.assertEqual(counter.call_count, 81)
        self.assertTrue(result.fresh)

    def test_malformed_multiple_and_wrong_solution(self):
        self.assertEqual(certify_puzzle("x").failure_reasons, [FailureReason.INVALID_FORMAT])
        self.assertEqual(certify_puzzle("0" * 81).failure_reasons, [FailureReason.NOT_UNIQUE])
        target = SOLUTION.translate(str.maketrans("12", "21"))
        self.assertEqual(certify_puzzle(almost(0), target).failure_reasons, [FailureReason.SOLUTION_MISMATCH])

    def test_timeout_is_not_certified(self):
        result = certify_puzzle(almost(0), SOLUTION, config=CertificationConfig(time_budget=0))
        self.assertEqual(result.status, CertificationStatus.CERTIFICATION_TIMEOUT)
        self.assertFalse(result.production_eligible)
        self.assertIsNone(result.minimum_required_rating)

    def test_stored_path_mismatch_is_not_ignored(self):
        result = certify_puzzle(almost(0), SOLUTION, previous_path=[])
        self.assertEqual(result.failure_reasons, [FailureReason.STORED_PATH_MISMATCH])

    def test_deterministic_result_excluding_explicit_timings(self):
        first = certify_puzzle(almost(0), SOLUTION)
        second = certify_puzzle(almost(0), SOLUTION)
        self.assertEqual(first, second)
        self.assertEqual(first.algorithm_fingerprint, algorithm_fingerprint())

    def test_decision_requires_all_evidence_and_real_policy(self):
        result = CertificationResult(unique=True, human_solved=True, proof_valid=True,
            reproducible=True, search_status=SearchStatus.SOLVED, minimum_required_rating=30,
            certified_bottlenecks=2, advanced_steps=3)
        result.status = classify_certificate(result, CertificationConfig())
        self.assertEqual(result.status, CertificationStatus.CERTIFIED_EXTREME)
        self.assertTrue(result.production_eligible)
        result.search_status = SearchStatus.INCONCLUSIVE_BUDGET
        self.assertFalse(result.production_eligible)
        self.assertEqual(classify_certificate(result, CertificationConfig()), CertificationStatus.SEARCH_INCONCLUSIVE)

    def test_ultra_decision_requires_chain_and_distribution(self):
        from generator.tests.test_certification_proofs import fixtures
        from generator.solver.techniques import default_techniques
        technique = next(t for t in default_techniques() if t.name == "AIC")
        step = technique.find_steps(fixtures()["AIC"])[0]
        result = CertificationResult(unique=True, human_solved=True, proof_valid=True,
            reproducible=True, search_status=SearchStatus.SOLVED, minimum_required_rating=36,
            certified_bottlenecks=3, advanced_steps=5, longest_chain=8, distributed_bins=2,
            certified_path=[step])
        self.assertEqual(classify_certificate(result, CertificationConfig()), CertificationStatus.CERTIFIED_ULTRA_EXTREME)
        result.distributed_bins = 1
        self.assertEqual(classify_certificate(result, CertificationConfig()), CertificationStatus.CERTIFIED_EXTREME)
        result.distributed_bins = 2
        result.longest_chain = 7
        self.assertEqual(classify_certificate(result, CertificationConfig()), CertificationStatus.CERTIFIED_EXTREME)

    def test_shallower_arrival_reopens_state_under_depth_budget(self):
        # Pure graph-search regression, deliberately isolates scheduling from
        # Sudoku theorem checking (covered by real proof tests above).
        from generator.solver.models import LogicStep
        from generator.certification.proofs import ProofValidationResult
        priorities = {"root": 9, "deep1": 1, "deep2": 1, "merge": 1, "shallow": 8, "goal": 0}
        graph = {"root": ("deep1", "shallow"), "deep1": ("deep2",), "deep2": ("merge",),
                 "shallow": ("merge",), "merge": ("goal",), "goal": ()}
        class State(SudokuState):
            def __init__(self, key):
                self.key, self.candidates = key, [(1 << priorities[key]) - 1]
            def copy(self): return State(self.key)
            def signature(self): return self.key
            @property
            def is_solved(self): return self.key == "goal"
        class Provider:
            def enumerate(self, state, threshold, **kwargs):
                return EnumerationResult([LogicStep("Naked Single", 1, placements=((i, 1),),
                    explanation=target) for i, target in enumerate(graph[state.key])])
        with patch("generator.certification.proofs.validate_step", return_value=ProofValidationResult(True)), \
             patch("generator.certification.search.apply_step", side_effect=lambda state, step: State(step.explanation)):
            result = threshold_search(State("root"), 1, CertificationConfig(max_path_depth=3), enumerator=Provider())
        self.assertEqual(result.status, SearchStatus.SOLVED)
        self.assertEqual([s.explanation for s in result.path], ["shallow", "merge", "goal"])

    def test_actual_advanced_enumerator_witnesses_pass_independent_validator(self):
        from generator.tests.test_certification_proofs import fixtures
        from generator.solver.techniques import default_techniques
        from generator.certification.proofs import validate_step
        config = CertificationConfig(max_chain_search_nodes=3000, max_als_search_nodes=10000,
                                      max_forcing_starts=10)
        states = fixtures()
        for name in ("X-Chain", "XY-Chain", "AIC", "Nice Loop", "Grouped AIC", "ALS-XZ", "ALS-XY-Wing", "ALS Chain", "Forcing Chain", "Nishio"):
            with self.subTest(technique=name):
                technique = next(t for t in default_techniques() if t.name == name)
                provider = enumerate_als_steps if name.startswith("ALS") else enumerate_forcing if name in ("Forcing Chain", "Nishio") else enumerate_chains
                result = provider(states[name], technique, config)
                for step in result.steps:
                    proof = validate_step(states[name], step, config=config)
                    self.assertTrue(proof.valid, (name, proof.errors))
                self.assertTrue(result.steps or not result.complete)

    def test_actual_chain_length_and_als_size_omissions_are_explicit(self):
        from generator.tests.test_certification_proofs import fixtures
        state = fixtures()["X-Chain"]
        result = enumerate_chains(state, XChain(), CertificationConfig(max_chain_length=1))
        self.assertIn("CHAIN_LENGTH_LIMIT", result.limit_reasons)
        result = enumerate_als_steps(fixtures()["ALS-XZ"], ALSXZ(), CertificationConfig(max_als_size=1))
        self.assertIn("ALS_SIZE_LIMIT", result.limit_reasons)

    def test_equal_length_valid_loop_orientation_tie_is_order_independent(self):
        from generator.tests.test_certification_proofs import fixtures
        from generator.solver.techniques.chains import AIC
        from generator.solver.models import Chain
        from generator.certification.proofs import validate_step
        state = fixtures()["AIC"]
        with patch("generator.certification.enum_chains.canonical_steps", side_effect=lambda steps: steps):
            raw = enumerate_chains(state, AIC(), CertificationConfig(max_chain_length=9))
        original = next(s for s in raw.steps if s.chain.closed)
        links = tuple(replace(edge, source=edge.target, target=edge.source)
                      for edge in reversed(original.chain.links))
        alternate = replace(original, chain=Chain(tuple(reversed(original.chain.nodes)), links, True))
        self.assertNotEqual(original, alternate)
        self.assertTrue(validate_step(state, original).valid)
        self.assertTrue(validate_step(state, alternate).valid)
        self.assertEqual(canonical_steps([original, alternate]), canonical_steps([alternate, original]))

    def test_complete_empty_advanced_catalogue(self):
        state = SudokuState(list(map(int, SOLUTION)))
        result = StepEnumerator(CertificationConfig()).enumerate(state, 55)
        self.assertTrue(result.complete)
        self.assertEqual(result.steps, [])

    def test_forcing_start_limit_and_real_chain_work_limit(self):
        cfg = CertificationConfig(max_forcing_starts=1, max_chain_search_nodes=1)
        state = SudokuState(almost(0, 9))
        result = enumerate_forcing(state, ForcingChain(), cfg)
        self.assertIn("FORCING_START_LIMIT", result.limit_reasons)
        # Four bivalue candidates form actual conjugate-unit graph edges.
        state = SudokuState([0] * 81)
        for c in range(2, 9):
            state.eliminate(c, 1)
        result = enumerate_chains(state, XChain(), cfg)
        self.assertIn("CHAIN_NODE_LIMIT", result.limit_reasons)

    def test_logical_modules_import_without_exact_solver(self):
        code = """
import builtins
old = builtins.__import__
def guarded(name, *args, **kwargs):
    if 'exact_solver' in name:
        raise AssertionError('Exact dependency: ' + name)
    return old(name, *args, **kwargs)
builtins.__import__ = guarded
from generator.certification.search import threshold_search
from generator.certification.proofs import validate_step
from generator.certification.enumeration import StepEnumerator
"""
        completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
