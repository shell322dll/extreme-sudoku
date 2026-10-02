"""Phase 5 construction and acceptance invariants, with controlled rating cases."""
from dataclasses import replace
import random
import unittest
from unittest.mock import patch

from generator import (GeneratorConfig, GenerationError, PuzzleGenerator,
                       generate_many, generate_puzzle)
from generator.chromosome import Individual
from generator.clue_generator import minimize_puzzle
from generator.construction import (FULL_MASK, UniquenessCache, check_minimal,
                                    minimalize, remove_clues, validate_candidate)
from generator.models import RejectionReason
from generator.rating.models import DifficultyResult
from generator.solution_generator import generate_solution
from generator.solver.exact_solver import count_solutions
from generator.sudoku.grid import ALL_UNITS


def config(**kwargs):
    return GeneratorConfig(**dict(dict(seed=42, min_clues=35, max_clues=35,
                                       require_minimal=False, max_attempts=3,
                                       rating_mode="quick"), **kwargs))


def individual(puzzle, solution):
    return Individual(sum(1 << i for i, value in enumerate(puzzle) if value), solution)


class ConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.solution = generate_solution(42)
        cls.minimal = individual(minimize_puzzle(cls.solution, 42), cls.solution)

    def test_clue_removal_preserves_unique_and_never_mutates_solution(self):
        source = Individual(FULL_MASK, self.solution)
        result = remove_clues(source, 40, rng=random.Random(12))
        self.assertEqual(result.clue_count, 40)
        self.assertTrue(validate_candidate(result))
        self.assertEqual(source.clue_count, 81)
        self.assertEqual(source.solution, result.solution)
        self.assertEqual(self.solution, generate_solution(42))
        for unit in ALL_UNITS:
            self.assertEqual({result.solution[cell] for cell in unit}, set(range(1, 10)))

    def test_minimalization_removes_redundant_clue_and_preserves_minimal_input(self):
        missing = next(i for i in range(81) if not self.minimal.clue_mask & (1 << i))
        redundant = Individual(self.minimal.clue_mask | (1 << missing), self.solution)
        self.assertFalse(check_minimal(redundant))
        result = minimalize(redundant, rng=random.Random(10))
        self.assertLess(result.clue_count, redundant.clue_count)
        self.assertTrue(check_minimal(result))
        self.assertEqual(minimalize(self.minimal, rng=random.Random(3)), self.minimal)
        for cell, value in enumerate(result.to_puzzle()):
            if value:
                reduced = result.to_puzzle()
                reduced[cell] = 0
                self.assertEqual(count_solutions(reduced, 2), 2)

    def test_unreachable_target_stops_at_valid_minimal_state(self):
        result = remove_clues(self.minimal, 0, rng=random.Random(7))
        self.assertEqual(result, self.minimal)
        self.assertGreaterEqual(result.clue_count, 17)

    def test_validation_does_not_trust_warm_uniqueness_cache(self):
        cache = UniquenessCache()
        self.assertTrue(cache.unique(self.minimal))
        with patch("generator.construction.count_solutions", return_value=2) as exact:
            self.assertTrue(cache.unique(self.minimal))
            self.assertFalse(validate_candidate(self.minimal))
            exact.assert_called_once()

    def test_uniqueness_cache_includes_solution_and_is_bounded(self):
        cache = UniquenessCache(size=1)
        first = Individual(FULL_MASK, generate_solution(1))
        second = Individual(FULL_MASK, generate_solution(2))
        with patch("generator.construction.count_solutions", side_effect=[1, 2, 1]) as exact:
            self.assertTrue(cache.unique(first))
            self.assertFalse(cache.unique(second))
            self.assertTrue(cache.unique(first))
            self.assertEqual(exact.call_count, 3)

    def test_reject_invalid_construction_requests(self):
        for target in (-1, 82, 1.0, True):
            with self.assertRaises(ValueError):
                remove_clues(self.minimal, target)
        with self.assertRaises(ValueError):
            minimalize(Individual(0, self.solution))


class GenerationConfigTests(unittest.TestCase):
    def test_invalid_configuration(self):
        invalid = (dict(seed=True), dict(seed="42"), dict(min_clues=16),
                   dict(min_clues=30, max_clues=20), dict(max_clues=82),
                   dict(min_clues=True), dict(target_difficulty="Impossible"),
                   dict(require_unique=False), dict(require_unique=1),
                   dict(require_minimal=1), dict(max_attempts=0), dict(max_attempts=True),
                   dict(rating_mode="fast"), dict(symmetry="rotational_180"),
                   dict(timeout_seconds=0), dict(timeout_seconds=float("inf")),
                   dict(timeout_seconds=float("nan")), dict(timeout_seconds=True),
                   dict(difficulty_config={}),
                   dict(rating_mode="quick", target_difficulty="Extreme"))
        for value in invalid:
            with self.subTest(config=value), self.assertRaises(ValueError):
                GeneratorConfig(**value)

    def test_invalid_batch_count_and_config(self):
        for count in (0, -1, True, 1.0):
            with self.assertRaises(ValueError):
                generate_many(count, config())
        with self.assertRaises(ValueError):
            PuzzleGenerator({})


class GenerationPipelineTests(unittest.TestCase):
    def test_reproducible_real_generation_and_global_random_untouched(self):
        state = random.getstate()
        first = generate_puzzle(config())
        second = generate_puzzle(config())
        self.assertEqual(first, second)
        self.assertEqual(random.getstate(), state)
        self.assertEqual(first.clues, sum(c != "0" for c in first.puzzle))
        self.assertTrue(first.unique and first.difficulty_result.solved)
        self.assertEqual(count_solutions(list(map(int, first.puzzle)), 2), 1)
        self.assertEqual(first.human_result.grid, list(map(int, first.solution)))

    def test_seed_none_records_effective_replayable_seed(self):
        result = generate_many(1, config(seed=None))
        repeated = generate_many(1, config(seed=result.seed))
        self.assertEqual(result.puzzles, repeated.puzzles)

    def test_batch_ids_duplicates_and_total_budget(self):
        generator = PuzzleGenerator(config(max_attempts=3))
        fixed, cache = generator._construct(123)
        with patch.object(generator, "_construct", return_value=(fixed, cache)):
            result = generator.generate_many(2)
        self.assertFalse(result.complete)
        self.assertEqual(len(result.puzzles), 1)
        self.assertEqual(result.stats.attempts, 3)
        self.assertEqual(result.stats.rejections[RejectionReason.DUPLICATE], 2)
        self.assertEqual(len({record.id for record in result.puzzles}), 1)

    def test_batch_continues_after_rejection_and_reports_progress(self):
        generator = PuzzleGenerator(config(max_attempts=2))
        original = generator._attempt
        calls = []
        def attempt(*args):
            if generator.stats.attempts == 1:
                return None, RejectionReason.HUMAN_UNSOLVED
            return original(*args)
        with patch.object(generator, "_attempt", side_effect=attempt):
            result = generator.generate_many(1, progress=lambda stats, latest: calls.append(stats))
        self.assertTrue(result.complete)
        self.assertEqual([snapshot.attempts for snapshot in calls], [1, 2])
        self.assertEqual(result.stats.rejections[RejectionReason.HUMAN_UNSOLVED], 1)

    def test_difficulty_filtering_does_not_infer_difficulty_from_clues(self):
        generator = PuzzleGenerator(config(target_difficulty="Expert", max_attempts=2))
        easy = DifficultyResult(True, "quick", difficulty_class="Easy", hardest_rating=1)
        with patch.object(generator, "_rate_validated", return_value=easy):
            result = generator.generate_many(1)
        self.assertFalse(result.complete)
        self.assertEqual(result.stats.rejections[RejectionReason.WRONG_DIFFICULTY], 2)
        self.assertEqual(result.stats.attempts, 2)

    def test_solved_matching_difficulty_is_accepted(self):
        first = generate_puzzle(config())
        matching = generate_puzzle(config(target_difficulty=first.difficulty))
        self.assertEqual(first.puzzle, matching.puzzle)
        self.assertEqual(matching.difficulty, first.difficulty)

    def test_single_failure_exposes_structured_partial_result(self):
        with patch("generator.pipeline.PuzzleGenerator._attempt",
                   return_value=(None, RejectionReason.OUTSIDE_CLUE_RANGE)):
            with self.assertRaises(GenerationError) as error:
                generate_puzzle(config(max_attempts=2))
        self.assertEqual(error.exception.result.stats.attempts, 2)
        self.assertIn("0/1", str(error.exception))

    def test_minimalization_precedes_strict_clue_range(self):
        result = generate_many(1, config(min_clues=81, max_clues=81,
                                        require_minimal=True, max_attempts=1))
        self.assertFalse(result.complete)
        self.assertEqual(result.stats.rejections[RejectionReason.OUTSIDE_CLUE_RANGE], 1)
        self.assertEqual(result.stats.stage_calls["minimalization"], 1)
        self.assertNotIn("quick_rating", result.stats.stage_calls)

    def test_fresh_final_uniqueness_gate_prevents_rating(self):
        generator = PuzzleGenerator(config(max_attempts=1))
        with patch("generator.pipeline.validate_candidate", return_value=False), \
             patch.object(generator, "_rate_validated", side_effect=AssertionError("must not rate")):
            result = generator.generate_many(1)
        self.assertEqual(result.stats.rejections[RejectionReason.NOT_UNIQUE], 1)

    def test_timeout_returns_partial_status_without_fake_puzzle(self):
        with patch("generator.pipeline.perf_counter", side_effect=[0, 2, 3]):
            result = generate_many(1, config(timeout_seconds=1))
        self.assertTrue(result.stats.timed_out)
        self.assertEqual(result.stats.attempts, 0)
        self.assertFalse(result.complete)

    def test_completed_batch_has_unique_ids_and_timing_stats(self):
        result = generate_many(2, config(max_attempts=5))
        self.assertTrue(result.complete)
        self.assertEqual(len({p.id for p in result.puzzles}), 2)
        self.assertEqual(len({p.puzzle for p in result.puzzles}), 2)
        self.assertGreater(result.stats.stage_seconds["attempt"], 0)
        self.assertEqual(result.stats.to_dict()["accepted"], 2)


class RatingIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.candidate = Individual(FULL_MASK, generate_solution(42))

    def test_quick_then_deep_skips_deep_for_weak_candidate(self):
        generator = PuzzleGenerator(config(rating_mode="quick_then_deep"))
        with patch.object(generator.analyzer, "deep", side_effect=AssertionError("unnecessary Deep")):
            result = generator.rate_candidate(self.candidate)
        self.assertEqual(result.mode, "quick")

    def test_high_quick_rating_reaches_deep_before_extreme_target_filter(self):
        generator = PuzzleGenerator(config(rating_mode="quick_then_deep", target_difficulty="Extreme"))
        quick = DifficultyResult(True, "quick", difficulty_class="Expert", hardest_rating=30)
        deep = DifficultyResult(True, "deep", difficulty_class="Extreme", hardest_required_rating=30)
        with patch.object(generator.analyzer, "quick", return_value=quick), \
             patch.object(generator.analyzer, "deep", return_value=deep) as analyzer:
            result = generator.rate_candidate(self.candidate)
        self.assertEqual(result.difficulty_class, "Extreme")
        self.assertEqual(analyzer.call_args.kwargs, {"check_unique": True})

    def test_quick_stuck_is_not_rejected_before_deep(self):
        generator = PuzzleGenerator(config(rating_mode="quick_then_deep"))
        with patch.object(generator.analyzer, "quick", return_value=DifficultyResult(False, "quick")), \
             patch.object(generator.analyzer, "deep", return_value=DifficultyResult(True, "deep")) as deep:
            self.assertTrue(generator.rate_candidate(self.candidate).solved)
        deep.assert_called_once()

    def test_warm_rating_cache_isolation_and_policy_invalidation(self):
        generator = PuzzleGenerator(config())
        first = generator.rate_candidate(self.candidate)
        first.profile_statuses["polluted"] = "YES"
        first.difficulty_profile.append(999)
        second = generator.rate_candidate(self.candidate)
        self.assertNotIn("polluted", second.profile_statuses)
        self.assertNotIn(999, second.difficulty_profile)
        self.assertEqual(generator.stats.stage_calls["quick_rating"], 1)
        generator.config = replace(generator.config, difficulty_config=replace(
            generator.config.difficulty_config, total_rating_factor=.5))
        generator.rate_candidate(self.candidate)
        self.assertEqual(generator.stats.stage_calls["quick_rating"], 2)

    def test_reusable_rating_validates_uniqueness_even_with_warm_cache(self):
        generator = PuzzleGenerator(config())
        generator.rate_candidate(self.candidate)
        with patch("generator.pipeline.validate_candidate", return_value=False):
            with self.assertRaises(ValueError):
                generator.rate_candidate(self.candidate)

    def test_deep_real_simple_candidate(self):
        generator = PuzzleGenerator(config(rating_mode="deep"))
        result = generator.rate_candidate(self.candidate)
        self.assertTrue(result.solved and result.required_level_verified and result.unique)
        self.assertEqual(result.mode, "deep")

    def test_preliminary_extreme_is_archived_when_target_does_not_match(self):
        generator = PuzzleGenerator(config(target_difficulty="Easy", max_attempts=1))
        candidate = generate_puzzle(config())
        high = replace(candidate, difficulty="Extreme")
        with patch.object(generator, "_attempt", return_value=(high, RejectionReason.WRONG_DIFFICULTY)):
            result = generator.generate_many(1)
        self.assertFalse(result.complete)
        self.assertEqual(result.puzzles, ())
        self.assertEqual(result.preliminary_candidates, (high,))
        self.assertEqual(result.stats.rejections[RejectionReason.WRONG_DIFFICULTY], 1)


if __name__ == "__main__":
    unittest.main()
