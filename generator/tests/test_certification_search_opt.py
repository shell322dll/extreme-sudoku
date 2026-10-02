"""Phase 7.1 search optimizations: performance only, never relaxation."""
from dataclasses import replace
import random
import unittest
from unittest.mock import patch

from generator.certification import (CertificationConfig, CertificationStatus, SearchStatus,
                                     FailureReason, EnumerationResult, certify_puzzle)
from generator.certification.enumeration import (StepEnumerator, EnumerationCache, canonical_effects,
                                                 canonical_steps, effect_key)
from generator.certification.proofs import ProofValidationResult
from generator.certification.search import threshold_search, minimax_descent, select_transitions
from generator.certification.transitions import SudokuTransitions, apply_step as fast_apply
from generator.certification.enum_als import enumerate_als_steps
from generator.certification.enum_chains import enumerate_chains
from generator.solver.human_solver import apply_step as reference_apply
from generator.solver.models import LogicStep
from generator.solver.techniques import default_techniques
from generator.solver.techniques.singles import FullHouse, NakedSingle, HiddenSingle
from generator.sudoku.candidates import SudokuState
from generator.tests.test_certification_engine import SOLUTION, almost

HARD = "009000001000050008010000640028004000000190000000002030002403000100000206000070003"
# Review P2-1 case (state #14 of the reviewer's rv_states.txt).
REVIEW_STATE_14 = ("030900000409000003001003540000062090020000008900070000004107026700006900300050780/"
                   "0b20000f000008b0190a30610430000f00000600830910a30610000a20e00000600820000000001420910d80d4"
                   "09c00000000d00005903100007401c1051190290750000000b80b409c00009902f03501b09019000000018000"
                   "000400000000008108208e08c00000001501900012102200a000108000000009")
# These tests pin the exhaustive-search semantics; SSL-v1 has its own tests.
EXHAUSTIVE = CertificationConfig(use_stuck_state_lemma=False)


def technique(name):
    return next(t for t in default_techniques() if t.name == name)


class GraphProvider:
    """Abstract state graph: ``edges[state] = [(target, rating), ...]``."""

    def __init__(self, edges, solved=("goal",), progress=None):
        self.edges, self.solved, self.priority = edges, set(solved), progress or {}
        self.validated, self.enumerated = [], []

    def initial(self, state):
        return state

    def signature(self, state):
        return state

    def is_solved(self, state):
        return state in self.solved

    def progress(self, state):
        return self.priority.get(state, 0)

    def depth_bound(self, state):
        return None

    def enumerate(self, state, threshold, deadline):
        self.enumerated.append((state, threshold))
        return EnumerationResult([LogicStep("Mock", float(rating), placements=((i, 1),), explanation=target)
                                  for i, (target, rating) in enumerate(self.edges.get(state, ()))
                                  if rating <= threshold])

    def child(self, state, step):
        return step.explanation

    def apply_checked(self, state, step):
        return step.explanation

    def validate(self, state, step, signature=None):
        self.validated.append((state, step.explanation, step.rating))
        return ProofValidationResult(True)


MINIMAX = {"root": [("a1", 2), ("b1", 4), ("c1", 3)],
           "a1": [("a2", 8)], "a2": [("a3", 2)], "a3": [("goal", 2)],
           "b1": [("b2", 5)], "b2": [("b3", 4)], "b3": [("goal", 4)],
           "c1": [("goal", 7)]}


class MinimaxDescentTests(unittest.TestCase):
    def test_mock_graph_minimax_is_five_with_conclusive_failure_at_four(self):
        provider = GraphProvider(MINIMAX)
        outcome = minimax_descent("root", [2, 3, 4, 5, 7, 8], CertificationConfig(), provider=provider)
        self.assertEqual(outcome.upper, 5)
        self.assertTrue(outcome.conclusive)
        self.assertEqual(outcome.stop_reason, "EXHAUSTED_BELOW")
        self.assertEqual([s.explanation for s in outcome.witness], ["b1", "b2", "b3", "goal"])
        self.assertEqual(outcome.last.threshold, 4)
        self.assertEqual(outcome.last.status, SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)
        # Upper-bound pruning: every search ceiling is strictly below the witness known then.
        upper = float("inf")
        for search in outcome.threshold_results:
            self.assertLess(search.threshold, upper)
            if search.status == SearchStatus.SOLVED:
                upper = max(s.rating for s in search.path)

    def test_initial_witness_bounds_first_ceiling(self):
        provider = GraphProvider(MINIMAX)
        initial = [LogicStep("Mock", 7.0)]
        outcome = minimax_descent("root", [2, 3, 4, 5, 7, 8], CertificationConfig(), provider=provider,
                                  initial_witness=initial)
        self.assertEqual(outcome.threshold_results[0].threshold, 5)
        self.assertEqual(outcome.upper, 5)
        self.assertTrue(all(t <= 5 for _, t in provider.enumerated))

    def test_inconclusive_search_stops_descent_without_certificate(self):
        class Limited(GraphProvider):
            def enumerate(self, state, threshold, deadline):
                found = super().enumerate(state, threshold, deadline)
                if threshold < 5:
                    found.limit_reasons, found.complete = ["CONTROLLED_LIMIT"], False
                return found
        outcome = minimax_descent("root", [2, 3, 4, 5, 7, 8], CertificationConfig(), provider=Limited(MINIMAX))
        self.assertFalse(outcome.conclusive)
        self.assertEqual(outcome.upper, 5)
        self.assertEqual(outcome.stop_reason, "INCONCLUSIVE")
        self.assertEqual(outcome.last.status, SearchStatus.INCONCLUSIVE_BUDGET)
        self.assertFalse(outcome.last.negative_proof_possible)

    def test_threshold_pruning_never_explores_above_ceiling(self):
        provider = GraphProvider(MINIMAX)
        result = threshold_search("root", 4, CertificationConfig(), provider=provider)
        self.assertEqual(result.status, SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)
        self.assertTrue(provider.validated)
        self.assertTrue(all(rating <= 4 for _, _, rating in provider.validated))

        class Leaky(GraphProvider):
            def enumerate(self, state, threshold, deadline):
                return EnumerationResult([LogicStep("Mock", 9.0, placements=((0, 1),), explanation="goal")])
        result = threshold_search("root", 4, CertificationConfig(), provider=Leaky(MINIMAX))
        self.assertEqual(result.status, SearchStatus.ERROR)


class DedupTests(unittest.TestCase):
    def test_identical_successor_keeps_only_lowest_rating(self):
        provider = GraphProvider({})
        steps = [LogicStep("Mock", 8.0, placements=((1, 1),), explanation="x"),
                 LogicStep("Mock", 5.0, placements=((2, 1),), explanation="x"),
                 LogicStep("Mock", 6.0, placements=((3, 1),), explanation="y")]
        telemetry = {}
        chosen = select_transitions(provider, "root", steps, telemetry)
        self.assertEqual(sorted((c, s.rating) for s, c, _ in chosen), [("x", 5.0), ("y", 6.0)])
        self.assertEqual(telemetry["duplicate_children_removed"], 1)
        for order in (steps[::-1], [steps[1], steps[2], steps[0]]):
            self.assertEqual(select_transitions(provider, "root", order), chosen)

    def test_real_singles_same_placement_one_branch(self):
        state = SudokuState(almost(0))
        steps = FullHouse().find_steps(state) + NakedSingle().find_steps(state) + HiddenSingle().find_steps(state)
        self.assertGreater(len(steps), 1)
        chosen = select_transitions(SudokuTransitions(CertificationConfig()), state, steps)
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen[0][0].technique, "Full House")
        self.assertEqual(canonical_effects(steps), [chosen[0][0]])
        # The per-rating canonical form is unchanged (bottleneck semantics).
        self.assertEqual(len(canonical_steps(steps)), len({s.rating for s in steps}))

    def _raw(self, module, fixture, names):
        from generator.tests.test_certification_proofs import fixtures
        state = fixtures()[fixture]
        steps = []
        with patch(f"generator.certification.{module}.canonical_steps", side_effect=lambda s: s):
            for name in names:
                runner = enumerate_als_steps if name.startswith("ALS") else enumerate_chains
                steps += runner(state, technique(name), CertificationConfig(max_chain_length=9)).steps
        return state, steps

    def _check_equivalent_proofs(self, state, steps):
        effects = {effect_key(s) for s in steps}
        self.assertLess(len(effects), len(steps), "fixture must contain equivalent proofs")
        expected = canonical_effects(steps)
        self.assertEqual(len(expected), len(effects))
        rng = random.Random(7)
        for _ in range(5):
            shuffled = list(steps)
            rng.shuffle(shuffled)
            self.assertEqual(canonical_effects(shuffled), expected)
        provider = SudokuTransitions(CertificationConfig())
        chosen = select_transitions(provider, state, steps)
        self.assertEqual(len(chosen), len({provider.signature(provider.child(state, s)) for s in steps}))
        self.assertEqual([(s, k) for s, _, k in select_transitions(provider, state, steps[::-1])],
                         [(s, k) for s, _, k in chosen])
        for step, _, _ in chosen:
            self.assertEqual(step.rating, min(s.rating for s in steps if effect_key(s) == effect_key(step)))
            self.assertTrue(provider.validate(state, step).valid)

    def test_equivalent_aic_proofs_one_branch(self):
        self._check_equivalent_proofs(*self._raw("enum_chains", "AIC", ["AIC"]))

    def test_equivalent_als_proofs_one_branch(self):
        self._check_equivalent_proofs(*self._raw("enum_als", "ALS-XZ", ["ALS-XZ", "ALS-XY-Wing"]))


class StateDominanceTests(unittest.TestCase):
    EDGES = {"root": [("p", 8), ("q", 2), ("r", 2)], "p": [("x", 1)], "q": [("x", 1)],
             "r": [("x", 1)], "x": [("goal", 1)]}
    PROGRESS = {"root": 20, "p": 1, "q": 5, "r": 6, "x": 10, "goal": 0}

    def test_no_reexpansion_for_lower_max_rating(self):
        """Review P2-1: within one ceiling the verdict depends only on reachability,
        so a lower max rating so far never re-opens a state (visited semantics)."""
        provider = GraphProvider(self.EDGES, progress=self.PROGRESS)
        result = threshold_search("root", 8, CertificationConfig(), provider=provider)
        self.assertEqual(result.status, SearchStatus.SOLVED)
        self.assertEqual([s.explanation for s in result.path], ["p", "x", "goal"])  # first arrival kept
        self.assertEqual(result.telemetry["repushes"], 0)
        self.assertEqual(result.telemetry["transposition_hits"], 2)    # via q and r, same depth
        self.assertEqual(result.states_explored, 5)                    # x expanded once
        # Validation happens only for transitions that create frontier entries.
        self.assertEqual(sum(1 for _, child, _ in provider.validated if child == "x"), 1)
        # The descent still reaches the minimax witness (q, x, goal; max 2).
        outcome = minimax_descent("root", [1, 2, 8], CertificationConfig(), provider=GraphProvider(
            self.EDGES, progress=self.PROGRESS))
        self.assertEqual(outcome.upper, 2)
        self.assertTrue(outcome.conclusive)

    def test_shallower_arrival_reopens_only_when_depth_can_bind(self):
        edges = {"root": [("a", 1), ("m", 1)], "a": [("b", 1)], "b": [("m", 1)], "m": [("n", 1)],
                 "n": [("goal", 1)]}
        progress = {"root": 9, "a": 1, "b": 1, "m": 5, "n": 4, "goal": 0}
        result = threshold_search("root", 1, CertificationConfig(max_path_depth=3),
                                  provider=GraphProvider(edges, progress=progress))
        self.assertEqual(result.status, SearchStatus.SOLVED)
        self.assertEqual([s.explanation for s in result.path], ["m", "n", "goal"])
        self.assertEqual(result.telemetry["depth_reopens"], 0)
        # Deep arrival first (via a, b) at depth 3 hits the limit; the shallow one re-opens m.
        progress2 = {"root": 9, "a": 1, "b": 1, "m": 0, "n": 4, "goal": 0}
        edges2 = {"root": [("a", 1), ("c", 1)], "a": [("b", 1)], "b": [("m", 1)], "c": [("m", 1)],
                  "m": [("n", 1)], "n": [("goal", 1)]}
        progress2["c"] = 8
        result = threshold_search("root", 1, CertificationConfig(max_path_depth=4),
                                  provider=GraphProvider(edges2, progress=progress2))
        self.assertEqual(result.status, SearchStatus.SOLVED)
        self.assertEqual([s.explanation for s in result.path], ["c", "m", "n", "goal"])
        self.assertEqual(result.telemetry["depth_reopens"], 2)  # m, then its child n

    def test_review_state_14_node_budget_not_worse_than_baseline(self):
        """Review P2-1 reproduction: state #14 at T=22 needs 300 unique states; the
        baseline proves it within node_budget=320 and so must this code."""
        from generator.certification.stuck_state import parse_signature_text
        state = parse_signature_text(REVIEW_STATE_14)
        config = replace(EXHAUSTIVE, node_budget=320, state_budget=3000, time_budget=60)
        result = threshold_search(state, 22.0, config)
        self.assertEqual(result.status, SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)
        self.assertEqual(result.states_explored, result.telemetry["unique_states"])
        self.assertLessEqual(result.states_explored, 300)

    def test_duplicate_states_are_pruned_in_exhaustive_search(self):
        edges = {"root": [("a", 1), ("b", 1)], "a": [("m", 1)], "b": [("m", 1)], "m": [("dead", 1)]}
        provider = GraphProvider(edges)
        result = threshold_search("root", 1, CertificationConfig(), provider=provider)
        self.assertEqual(result.status, SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)
        self.assertEqual(result.states_explored, 5)
        self.assertEqual(result.states_generated, 5)
        self.assertEqual(result.telemetry["transposition_hits"], 1)

    def test_sudoku_depth_rule_is_exact_visited_when_depth_cannot_bind(self):
        # Exhaustive-search semantics (the SSL shortcut would never expand states).
        result = threshold_search(almost(0, 9), .5, EXHAUSTIVE)
        self.assertEqual(result.telemetry["depth_rule"], "visited")
        result = threshold_search(almost(0, 9, 18), .5, replace(EXHAUSTIVE, max_path_depth=2))
        self.assertEqual(result.telemetry["depth_rule"], "shallower-reopen")
        self.assertIn("PATH_DEPTH_LIMIT", result.limit_reasons)


class FastApplyTests(unittest.TestCase):
    def _same(self, state, step):
        try:
            expected = reference_apply(state, step).signature()
        except ValueError:
            expected = ValueError
        try:
            actual = fast_apply(state, step).signature()
        except ValueError:
            actual = ValueError
        self.assertEqual(actual, expected, step)

    def test_matches_reference_apply_including_failures(self):
        state = SudokuState([int(c) for c in HARD])
        enumerator = StepEnumerator(CertificationConfig(max_chain_search_nodes=2000, max_forcing_starts=5))
        rng = random.Random(3)
        for _ in range(6):
            steps = enumerator.enumerate(state, 32).steps
            for step in steps:
                self._same(state, step)
            free = [(c, d) for c in range(81) for d in range(1, 10) if state.candidates[c] & (1 << (d - 1))]
            for _ in range(40):
                picks = rng.sample(free, 3)
                for kind in ("p", "e", "pe", "pp"):
                    placements = tuple(picks[:2]) if kind == "pp" else (picks[0],) if "p" in kind else ()
                    eliminations = (picks[1],) if kind == "pe" else tuple(picks) if kind == "e" else ()
                    self._same(state, LogicStep("Mock", 1.0, placements=placements, eliminations=eliminations))
            self._same(state, LogicStep("Mock", 1.0, placements=((0, 1),)))
            state = fast_apply(state, steps[0])
        # Emptying a cell / unit via eliminations is rejected by both.
        cell = next(c for c in range(81) if not state.grid[c])
        digits = [d for d in range(1, 10) if state.candidates[cell] & (1 << (d - 1))]
        self._same(state, LogicStep("Mock", 1.0, eliminations=tuple((cell, d) for d in digits)))


class CacheTests(unittest.TestCase):
    def test_cached_and_uncached_enumeration_identical(self):
        config = CertificationConfig(max_chain_search_nodes=3000, max_als_search_nodes=3000, max_forcing_starts=10)
        cached, plain = StepEnumerator(config), StepEnumerator(config, cache=False)
        state = SudokuState([int(c) for c in HARD])
        states = [state, fast_apply(state, plain.enumerate(state, 32).steps[0])]
        for s in states:
            for threshold in (50, 32, 18, 50):
                self.assertEqual(cached.enumerate(s, threshold), plain.enumerate(s, threshold))
        stats = cached.cache.stats()
        self.assertGreater(stats["hits"], 0)
        # Different signature never hits: a state differing by one candidate.
        other = state.copy()
        cell = next(c for c in range(81) if state.candidates[c].bit_count() > 2)
        other.eliminate(cell, next(d for d in range(1, 10) if other.candidates[cell] & (1 << (d - 1))))
        before = cached.cache.hits
        self.assertEqual(cached.enumerate(other, 18), plain.enumerate(other, 18))
        self.assertEqual(cached.cache.hits, before)

    def test_time_limited_results_are_never_cached(self):
        cache = EnumerationCache()
        cache.put(("sig", "AIC"), EnumerationResult([], False, ["TIME_LIMIT"]))
        cache.put(("sig", "X-Chain"), EnumerationResult([], False, ["CHAIN_NODE_LIMIT"]))
        self.assertIsNone(cache.get(("sig", "AIC")))
        self.assertIsNotNone(cache.get(("sig", "X-Chain")))
        self.assertEqual(cache.skipped_time_limited, 1)
        enumerator = StepEnumerator(CertificationConfig())
        state = SudokuState([int(c) for c in HARD])
        with patch("generator.certification.enum_chains.perf_counter", return_value=float("inf")):
            first = enumerator.enumerate(state, 32, deadline=1e300)
        self.assertIn("AIC:TIME_LIMIT", first.limit_reasons)
        keys = {key[-1] for key in enumerator.cache.entries}
        self.assertNotIn("AIC", keys)
        self.assertIn("Hidden Single", keys)
        second = enumerator.enumerate(state, 32)
        self.assertNotIn("AIC:TIME_LIMIT", second.limit_reasons)
        self.assertEqual(second, StepEnumerator(CertificationConfig(), cache=False).enumerate(state, 32))

    def test_cache_is_bounded(self):
        cache = EnumerationCache(max_entries=2)
        for i in range(5):
            cache.put((i, "x"), EnumerationResult())
        self.assertEqual(len(cache.entries), 2)
        self.assertEqual(cache.evictions, 3)

    def test_validation_cache_is_keyed_by_full_signature(self):
        provider = SudokuTransitions(CertificationConfig())
        state = SudokuState(almost(0))
        step = FullHouse().find_steps(state)[0]
        first = provider.validate(state, step, state.signature())
        second = provider.validate(state, step, state.signature())
        self.assertTrue(first.valid and second.valid)
        self.assertEqual(provider.validation_cache.hits, 1)
        bad = replace(step, placements=((0, 2),))
        self.assertFalse(provider.validate(state, bad, state.signature()).valid)


class SemanticsTests(unittest.TestCase):
    def test_deterministic_runs(self):
        config = replace(EXHAUSTIVE, node_budget=25)
        grid = [int(c) for c in HARD]
        first, second = threshold_search(grid, 32, config), threshold_search(grid, 32, config)
        self.assertEqual(first, second)
        self.assertEqual(first.limit_reasons, ["NODE_LIMIT"])
        self.assertEqual(first.telemetry["transposition_hits"], second.telemetry["transposition_hits"])

    def test_tiny_budgets_are_inconclusive_never_proven(self):
        grid = [int(c) for c in HARD]
        cases = [(replace(EXHAUSTIVE, time_budget=0), "TIME_LIMIT"),
                 (replace(EXHAUSTIVE, node_budget=2), "NODE_LIMIT"),
                 (replace(EXHAUSTIVE, state_budget=3), "STATE_LIMIT"),
                 (replace(EXHAUSTIVE, max_path_depth=1), "PATH_DEPTH_LIMIT")]
        for config, reason in cases:
            with self.subTest(reason=reason):
                result = threshold_search(grid, 32, replace(config, node_budget=min(config.node_budget, 40)))
                self.assertEqual(result.status, SearchStatus.INCONCLUSIVE_BUDGET)
                self.assertIn(reason, result.limit_reasons)
                self.assertFalse(result.negative_proof_possible)
                self.assertIn(reason, result.telemetry["limit_reason_first_expansion"])
        result = threshold_search(grid, 32, EXHAUSTIVE, provider=None, max_records=4)
        self.assertEqual(result.status, SearchStatus.INCONCLUSIVE_BUDGET)
        self.assertIn("MEMORY_LIMIT", result.limit_reasons)

    def test_exhausted_graph_is_proven_and_flag_kept(self):
        result = threshold_search(almost(0), 0, CertificationConfig())
        self.assertEqual(result.status, SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)
        self.assertTrue(result.negative_proof_possible)

    def test_witness_below_extreme_rejects_even_if_lower_search_inconclusive(self):
        limited = EnumerationResult([], False, ["CONTROLLED_LIMIT"])
        with patch.object(StepEnumerator, "enumerate", return_value=limited):
            result = certify_puzzle(almost(0), SOLUTION)
        self.assertEqual(result.status, CertificationStatus.REJECTED)
        self.assertEqual(result.failure_reasons, [FailureReason.RATING_BELOW_EXTREME])
        self.assertIsNone(result.minimum_required_rating)
        self.assertEqual(result.observed_upper_rating, .5)
        self.assertEqual(result.search_status, SearchStatus.INCONCLUSIVE_BUDGET)
        self.assertIn("CONTROLLED_LIMIT", result.diagnostics)
        self.assertFalse(result.production_eligible)

    def test_descent_shares_node_budget(self):
        provider = GraphProvider(MINIMAX)
        outcome = minimax_descent("root", [2, 3, 4, 5, 7, 8], CertificationConfig(node_budget=3), provider=provider)
        self.assertFalse(outcome.conclusive)
        self.assertIn(outcome.stop_reason, ("NODE_BUDGET", "INCONCLUSIVE"))
        self.assertLessEqual(sum(t.states_explored for t in outcome.threshold_results), 3)

    def test_real_certificate_unchanged_for_easy_grid(self):
        result = certify_puzzle(almost(0), SOLUTION)
        self.assertEqual(result.minimum_required_rating, .5)
        self.assertEqual(result.threshold_results[0].status, SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)
        self.assertEqual(result.failure_reasons, [FailureReason.RATING_BELOW_EXTREME])


if __name__ == "__main__":
    unittest.main()
