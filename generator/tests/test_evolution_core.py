"""Property tests for Phase 6 mask operators, exact repair and objective policy."""
from dataclasses import FrozenInstanceError, replace
import random
import unittest

from generator.chromosome import Individual
from generator.construction import FULL_MASK
from generator.evolution.config import EvolutionConfig, EXTREME_SEARCH, MONSTER_SEARCH
from generator.evolution.fitness import FitnessConfig, evaluate_fitness
from generator.evolution.models import EvolutionIndividual
from generator.evolution.operators import OPERATORS, crossover, guided_cells, mutate
from generator.evolution.repair import ConflictStore, repair_uniqueness
from generator.evolution.selection import (dominates, mask_distance, mean_diversity,
    pareto_archive, select_survivors, tournament_select)
from generator.rating.models import Bottleneck, DifficultyResult
from generator.solution_generator import generate_solution
from generator.solver.exact_solver import collect_solutions, count_solutions


SOLUTION = tuple(generate_solution(31))


def chromosome(clues=24, offset=0, solution=SOLUTION):
    return Individual(sum(1 << ((i + offset) % 81) for i in range(clues)), solution)


def rated(clues=24, required=12., offset=0, bottlenecks=0, mode="deep", **changes):
    rating = DifficultyResult(solved=True, mode=mode, hardest_rating=required,
        hardest_required_rating=required if mode == "deep" else None,
        minimum_tier="ADVANCED" if required >= 22 else "INTERMEDIATE",
        required_level_verified=mode == "deep", true_bottleneck_count=bottlenecks,
        advanced_steps=3, total_score=100., **changes)
    item = EvolutionIndividual(chromosome(clues, offset), unique=True,
        deep_rating=rating if mode == "deep" else None,
        quick_rating=rating if mode == "quick" else None)
    return evaluate_fitness(item)


class EvolutionConfigTests(unittest.TestCase):
    def test_round_trip_profiles_and_policy(self):
        for mode in ("balanced", "extreme", "monster", "min_clues"):
            config = EvolutionConfig.for_mode(mode, seed=17)
            self.assertEqual(EvolutionConfig.from_dict(config.to_dict()), config)
        self.assertEqual(EvolutionConfig.for_mode("extreme").target, EXTREME_SEARCH)
        self.assertEqual(EvolutionConfig.for_mode("monster").target, MONSTER_SEARCH)

    def test_direct_modes_have_real_search_policies_and_honor_explicit_overrides(self):
        policies = []
        for mode in ("balanced", "extreme", "monster", "min_clues"):
            direct = EvolutionConfig(mode=mode)
            self.assertEqual(direct, EvolutionConfig.for_mode(mode))
            policies.append(direct.fitness_config)
        self.assertEqual(len(set(policies)), 4)
        self.assertTrue(EvolutionConfig(mode="monster").target.require_minimal)
        custom = FitnessConfig(clue_bonus=.5)
        self.assertEqual(EvolutionConfig(mode="monster", fitness_config=custom).fitness_config, custom)
        hard, sparse = rated(24, 30.), rated(17, 12.)
        self.assertGreater(evaluate_fitness(hard, policies[1]).fitness,
                           evaluate_fitness(sparse, policies[1]).fitness)
        self.assertGreater(evaluate_fitness(sparse, policies[3]).fitness,
                           evaluate_fitness(hard, policies[3]).fitness)

    def test_invalid_budgets_and_weights(self):
        for updates in ({"population_size": True}, {"repair_limit": -1},
                        {"min_clues": 16}, {"search_max_clues": 20},
                        {"crossover_rate": float("nan")}, {"max_seconds": float("inf")},
                        {"elite_size": 32}, {"mutation_weights": (("swap", 0),)},
                        {"multi_swap_sizes": (True,)}, {"deep_fraction": 1.1}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                EvolutionConfig(**updates)
        with self.assertRaises(ValueError):
            FitnessConfig(clue_bonus=-1)

    def test_individual_preserves_immutable_chromosome_and_owned_rating(self):
        source = DifficultyResult(solved=True, mode="quick", hardest_rating=4.)
        individual = EvolutionIndividual(chromosome(), quick_rating=source)
        source.hardest_rating = 999
        self.assertEqual(individual.quick_rating.hardest_rating, 4.)
        self.assertEqual(individual.key, (SOLUTION, chromosome().clue_mask))
        with self.assertRaises(FrozenInstanceError):
            individual.candidate = chromosome(30)


class MutationTests(unittest.TestCase):
    def test_all_operators_preserve_solution_valid_mask_and_fixed_rng(self):
        original = chromosome(40)
        for operator in OPERATORS:
            with self.subTest(operator=operator):
                a = mutate(original, random.Random(82), operator)
                b = mutate(original, random.Random(82), operator)
                self.assertEqual(a, b)
                self.assertEqual(a.solution, original.solution)
                self.assertGreaterEqual(a.clue_mask, 0)
                self.assertLessEqual(a.clue_mask, FULL_MASK)
                expected = 39 if operator == "remove" else 41 if operator == "add" else 40
                self.assertEqual(a.clue_count, expected)
        self.assertEqual(original, chromosome(40))

    def test_swap_changes_distinct_positions_and_multi_swap_budget(self):
        original = chromosome(40)
        for count in (1, 2, 3):
            child = mutate(original, random.Random(6), "multi_swap", multi_swap_sizes=(count,))
            self.assertEqual(mask_distance(original, child), 2 * count)
            self.assertEqual(child.clue_count, 40)

    def test_boundary_masks_and_operator_errors(self):
        for mask in (0, FULL_MASK):
            for operator in OPERATORS:
                child = mutate(Individual(mask, SOLUTION), random.Random(1), operator)
                self.assertTrue(0 <= child.clue_mask <= FULL_MASK)
        with self.assertRaises(ValueError):
            mutate(chromosome(), random.Random(), "unsupported")

    def test_region_mutation_is_local_to_one_unit(self):
        from generator.sudoku.grid import ALL_UNITS
        source = Individual(sum(1 << i for i in range(0, 81, 2)), SOLUTION)
        for seed in range(10):
            target = mutate(source, random.Random(seed), "region")
            changed = {i for i in range(81) if (source.clue_mask ^ target.clue_mask) & (1 << i)}
            self.assertTrue(any(changed.issubset(unit) for unit in ALL_UNITS))

    def test_guided_mutation_uses_bottleneck_candidate_structure(self):
        grid = list(SOLUTION)
        masks = [0] * 81
        grid[40] = 0
        masks[40] = 3
        rating = DifficultyResult(solved=True, mode="deep", bottlenecks=[
            Bottleneck(5, (tuple(grid), tuple(masks)), 30., "AIC", 1)])
        region = guided_cells(rating)
        self.assertIn(40, region)
        self.assertLess(len(region), 81)
        source = Individual(sum(1 << i for i in range(0, 81, 2)), SOLUTION)
        child = mutate(source, random.Random(9), "guided", rating=rating)
        changed = {i for i in range(81) if (source.clue_mask ^ child.clue_mask) & (1 << i)}
        self.assertTrue(changed.issubset(region))
        self.assertEqual(len(changed), 2)

    def test_crossover_keeps_common_and_only_parent_optional_clues(self):
        a, b = chromosome(24), chromosome(24, 12)
        child = crossover(a, b, random.Random(2))
        self.assertEqual(child, crossover(a, b, random.Random(2)))
        self.assertEqual(child.clue_mask & (a.clue_mask & b.clue_mask), a.clue_mask & b.clue_mask)
        self.assertEqual(child.clue_mask & ~(a.clue_mask | b.clue_mask), 0)
        with self.assertRaises(ValueError):
            crossover(a, chromosome(solution=tuple(generate_solution(32))), random.Random())


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.multiple = Individual(sum(1 << i for i, value in enumerate(SOLUTION)
                                      if value not in (1, 2)), SOLUTION)

    def test_collector_exact_witnesses_and_early_limit(self):
        board = self.multiple.to_puzzle()
        answers = collect_solutions(board, 2)
        self.assertEqual(len(answers), 2)
        self.assertNotEqual(answers[0], answers[1])
        self.assertEqual(len(collect_solutions(board, 1)), 1)
        for answer in answers:
            self.assertEqual(Individual(FULL_MASK, tuple(answer)).clue_count, 81)
            self.assertTrue(all(not n or n == answer[i] for i, n in enumerate(board)))
        with self.assertRaises(ValueError):
            collect_solutions(board, True)
        invalid = list(SOLUTION)
        invalid[0] = invalid[1]
        self.assertEqual(collect_solutions(invalid), [])

    def test_all_repair_strategies_are_unique_and_use_difference_sets(self):
        for strategy in ("random", "coverage", "guided"):
            with self.subTest(strategy=strategy):
                result = repair_uniqueness(self.multiple, rng=random.Random(12), limit=18, strategy=strategy)
                self.assertTrue(result.unique)
                self.assertEqual(count_solutions(result.candidate.to_puzzle(), 2), 1)
                self.assertEqual(result.candidate.solution, SOLUTION)
                self.assertEqual(result.candidate.clue_count, self.multiple.clue_count + len(result.added_cells))
                for cell, witness in zip(result.added_cells, result.addition_conflicts):
                    self.assertTrue(witness & (1 << cell))
                    self.assertFalse(self.multiple.clue_mask & (1 << cell))
                self.assertEqual(result, repair_uniqueness(self.multiple, rng=random.Random(12), limit=18, strategy=strategy))

    def test_zero_budget_reports_failure_without_mutation(self):
        result = repair_uniqueness(self.multiple, rng=random.Random(1), limit=0)
        self.assertFalse(result.unique)
        self.assertEqual(result.candidate, self.multiple)
        self.assertEqual(result.added_cells, ())
        self.assertTrue(result.conflict_sets)
        unique = repair_uniqueness(Individual(FULL_MASK, SOLUTION), rng=random.Random(1), limit=0)
        self.assertTrue(unique.unique)

    def test_conflicts_reused_only_for_identical_target(self):
        store = ConflictStore()
        first = repair_uniqueness(self.multiple, rng=random.Random(1), limit=18, conflicts=store)
        self.assertTrue(store.unresolved(self.multiple))
        self.assertEqual(store.unresolved(first.candidate), ())
        other = tuple(generate_solution(11))
        self.assertEqual(store.for_solution(other), ())
        second = repair_uniqueness(self.multiple, rng=random.Random(1), limit=18, conflicts=store)
        self.assertTrue(second.unique)
        self.assertLessEqual(second.checks, first.checks)


class FitnessSelectionTests(unittest.TestCase):
    def test_difficulty_and_genuine_bottlenecks_raise_fitness(self):
        self.assertGreater(rated(required=30).fitness, rated(required=12).fitness)
        self.assertGreater(rated(bottlenecks=3).fitness, rated(bottlenecks=1).fitness)
        self.assertEqual(rated(mode="quick", bottlenecks=3).fitness, rated(mode="quick", bottlenecks=0).fitness)
        self.assertGreater(rated(19, 30.).fitness, rated(17, 1.).fitness)

    def test_quick_and_deep_share_tier_scale_without_certifying_quick(self):
        provisional = rated(24, 30., mode="quick")
        deep = evaluate_fitness(replace(provisional, deep_rating=replace(
            provisional.quick_rating, mode="deep", minimum_tier="EXTREME",
            hardest_required_rating=30., required_level_verified=True)))
        self.assertEqual(provisional.fitness, deep.fitness)
        self.assertEqual(provisional.status, "QUICK_RATED")
        self.assertEqual(pareto_archive((provisional,)), ())
        self.assertGreater(provisional.fitness, rated(24, 17.).fitness)

    def test_advanced_complexity_positive_contributions(self):
        base = rated()
        for field in ("advanced_steps", "extreme_steps", "total_score", "chain_complexity",
                      "longest_chain", "als_steps", "forcing_steps"):
            with self.subTest(field=field):
                more = replace(base.deep_rating, **{field: getattr(base.deep_rating, field) + 1})
                self.assertGreater(evaluate_fitness(replace(base, deep_rating=more)).fitness, base.fitness)

    def test_archive_order_is_deterministic(self):
        records = [rated(17, 12.), rated(19, 30., offset=1), rated(20, 12., offset=2)]
        self.assertEqual(pareto_archive(records), pareto_archive(reversed(records)))

    def test_clues_and_minimality_are_small_bonuses_and_policy_recomputes(self):
        a = rated(19, 12.)
        self.assertGreater(rated(17, 12.).fitness, a.fitness)
        self.assertLess(rated(17, 12.).fitness - a.fitness, 1.)
        self.assertGreater(evaluate_fitness(replace(a, minimal=True)).fitness, a.fitness)
        custom = evaluate_fitness(a, FitnessConfig(required_rating_weight=2000.))
        self.assertGreater(custom.fitness, a.fitness)
        self.assertEqual(evaluate_fitness(a), a)

    def test_reject_constraints_and_human_unsolved_never_score_high(self):
        a = rated()
        for invalid in (replace(a, unique=False), replace(a, candidate=chromosome(16)),
                        replace(a, deep_rating=replace(a.deep_rating, invalid=True))):
            result = evaluate_fitness(invalid)
            self.assertEqual(result.status, "REJECTED")
            self.assertEqual(result.fitness, float("-inf"))
        unsolved = evaluate_fitness(replace(a, deep_rating=replace(a.deep_rating, solved=False, hardest_rating=65.)))
        self.assertEqual(unsolved.status, "HUMAN_UNSOLVED")
        self.assertLess(unsolved.fitness, rated(17, 1.).fitness)

    def test_tournament_reproducibility_and_bias(self):
        population = [rated(offset=i, required=2. + i) for i in range(12)]
        one, two = random.Random(1), random.Random(1)
        a = [tournament_select(population, one, 4, penalty=0).key for _ in range(100)]
        b = [tournament_select(population, two, 4, penalty=0).key for _ in range(100)]
        self.assertEqual(a, b)
        ranks = {p.key: i for i, p in enumerate(population)}
        self.assertGreater(sum(ranks[key] for key in a) / len(a), 7.)

    def test_survivors_exact_elite_preservation_duplicates_and_diversity(self):
        elite, near, far = rated(offset=0), rated(offset=1), rated(offset=35)
        result = select_survivors((elite, near, near, far), 2, elites=(elite,), near_distance=4, penalty=.2)
        self.assertIs(result[0], elite)
        self.assertEqual(result[1].key, far.key)
        self.assertEqual(len({p.key for p in result}), len(result))
        self.assertEqual(mask_distance(elite, near), 2)
        self.assertGreater(mean_diversity((elite, far)), mean_diversity((elite, near)))

    def test_pareto_keeps_tradeoffs_rejects_dominated_and_provisional(self):
        sparse, harder, dominated = rated(17, 12.), rated(19, 30., offset=1), rated(20, 12., offset=2)
        provisional = rated(17, 65., offset=3, mode="quick")
        archive = pareto_archive((sparse, harder, dominated, provisional))
        self.assertEqual({p.key for p in archive}, {sparse.key, harder.key})
        self.assertTrue(dominates(sparse, dominated))
        self.assertFalse(dominates(sparse, harder))


if __name__ == "__main__":
    unittest.main()
