"""Seeded end-to-end properties, cache isolation, budgets and schema reuse."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from generator.evolution import (EvolutionConfig, EvolutionEngine, evolve, export_evolution,
                                 save_snapshot, target_match)
from generator.evolution.fitness import FitnessConfig
from generator.evolution.fitness import evaluate_fitness
from generator.evolution.models import EvolutionIndividual
from generator.chromosome import Individual
from generator.rating.models import DifficultyResult
from generator.solution_generator import generate_solution
from generator.export import validate_database
from generator.solver.exact_solver import count_solutions
from generator.solver.human_solver import HumanSolver
from generator.tests.test_evolution_core import rated


class RecordingEngine(EvolutionEngine):
    def _record_stats(self, *args, **kwargs):
        if not hasattr(self, "history"):
            self.history = []
        self.history.append(tuple(self.population))
        return super()._record_stats(*args, **kwargs)


class EvolutionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = EvolutionConfig(seed=42, population_size=4, elite_size=1,
            offspring_count=4, random_injection_count=1, solution_count=2,
            injection_interval=1, max_generations=2, local_search_budget=1,
            stagnation_generations=1)
        cls.engine = RecordingEngine(cls.config)
        cls.result = cls.engine.run()

    def test_short_pipeline_valid_human_rated_and_unique(self):
        result = self.result
        self.assertEqual(result.generations, 2)
        self.assertEqual(len(result.population), 4)
        self.assertEqual(len({p.key for p in result.population}), 4)
        self.assertGreater(len({p.solution for p in self.engine.history[0]}), 1)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.initial_best)
        self.assertTrue(result.best.deep_rating.required_level_verified)
        self.assertEqual(result.best.status, "DEEP_RATED")
        for individual in result.population:
            self.assertEqual(count_solutions(individual.to_puzzle(), limit=2), 1)
        solved = HumanSolver().solve(result.best.to_puzzle())
        self.assertTrue(solved.solved)
        self.assertFalse(solved.used_backtracking)
        self.assertEqual(solved.guesses, 0)
        self.assertEqual(tuple(solved.grid), result.best.solution)

    def test_reproducibility_excludes_timings(self):
        repeated = evolve(self.config)
        self.assertEqual([p.key for p in repeated.population], [p.key for p in self.result.population])
        self.assertEqual(repeated.best.key, self.result.best.key)
        self.assertEqual(repeated.best.fitness, self.result.best.fitness)
        self.assertEqual(repeated.counters, self.result.counters)
        for a, b in zip(repeated.stats, self.result.stats):
            data_a, data_b = a.to_dict(), b.to_dict()
            for name in ("elapsed_seconds", "generation_seconds"):
                del data_a[name], data_b[name]
            self.assertEqual(data_a, data_b)

    def test_elites_preserved_and_injections_reserved(self):
        for previous, current in zip(self.engine.history, self.engine.history[1:]):
            elite = sorted(previous, key=lambda p: (-p.fitness, p.key))[0]
            self.assertIn(elite.key, {p.key for p in current})
            successor = next(p for p in current if p.key == elite.key)
            self.assertEqual(successor.candidate, elite.candidate)
            if elite.deep_rating is not None:
                self.assertEqual(successor.fitness, elite.fitness)
            previous_solutions = {p.solution for p in previous}
            self.assertTrue(any(p.solution not in previous_solutions for p in current))
        self.assertTrue(all(s.injections == 1 for s in self.result.stats[1:]))

    def test_stats_and_archive_have_verified_evidence(self):
        self.assertEqual([s.generation for s in self.result.stats], [0, 1, 2])
        self.assertIn("quick_rating", self.result.stage_seconds)
        self.assertIn("deep_rating", self.result.stage_seconds)
        self.assertIn("uniqueness", self.result.stage_seconds)
        self.assertTrue(all(p.deep_rating.required_level_verified for p in self.result.archive))
        self.assertTrue(all(s.best_fitness is not None for s in self.result.stats))
        self.assertTrue(all(s.unique_population_size == 4 for s in self.result.stats))
        self.assertTrue(all(0 < s.unique_masks <= 4 for s in self.result.stats))
        self.assertEqual(self.result.stats[-1].best_advanced_steps, self.result.best.deep_rating.advanced_steps)
        self.assertIn("local_search", self.result.stage_seconds)
        for cache in ("uniqueness", "quick", "deep", "fitness"):
            self.assertGreater(self.result.counters[cache + "_cache_lookups"], 0)
            self.assertLessEqual(self.result.counters.get(cache + "_cache_hits", 0),
                                 self.result.counters[cache + "_cache_lookups"])
        for stat in self.result.stats:
            self.assertTrue(all(0 <= rate <= 1 for rate in stat.mutation_success_rates.values()))
            self.assertTrue(stat.repair_success_rate is None or 0 <= stat.repair_success_rate <= 1)

    def test_existing_export_and_snapshot_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.json"
            database = export_evolution(self.result, path, generated_at="2026-09-29T00:00:00Z")
            validate_database(database)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), database)
            record = database["puzzles"][0]
            self.assertEqual(record["generatorSeed"], 42)
            self.assertTrue(record["ratingMetadata"]["preliminary"])
            self.assertIn("hardestRating", record["difficultyData"])
            snapshot = save_snapshot(self.result, Path(directory) / "snapshot.json")
            self.assertFalse(snapshot["resumable"])
            self.assertEqual(snapshot["generation"], 2)
            self.assertEqual(EvolutionConfig.from_dict(snapshot["config"]), self.config)
            self.assertEqual(snapshot["archive"][0]["solution"], "".join(map(str, self.result.archive[0].solution)))

    def test_target_profile_is_separate_from_exploratory_best(self):
        monster = EvolutionConfig.for_mode("monster")
        self.assertFalse(target_match(self.result.best, monster))
        broad = replace(self.config, max_clues=32)
        self.assertTrue(target_match(self.result.best, broad))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unchanged.json"
            path.write_text("old", encoding="utf-8")
            with self.assertRaises(ValueError):
                export_evolution(replace(self.result, config=monster), path, targets_only=True)
            self.assertEqual(path.read_text(encoding="utf-8"), "old")

    def test_policy_scoped_cache_and_detached_rating(self):
        candidate = self.result.best.candidate
        cached = self.engine._rating(candidate, "quick")
        cached.total_score = -123
        self.assertNotEqual(self.engine._rating(candidate, "quick").total_score, -123)
        previous = self.engine.config
        try:
            self.engine.config = replace(previous, fitness_config=replace(FitnessConfig(), clue_bonus=4.))
            rescored = self.engine._fitness(self.result.best)
            self.assertGreater(rescored.fitness, self.result.best.fitness)
            self.engine.config = replace(previous, difficulty_config=replace(previous.difficulty_config, total_rating_factor=.2))
            changed = self.engine._rating(candidate, "quick")
            self.assertEqual(self.engine.analyzer.config, self.engine.config.difficulty_config)
            self.assertGreater(changed.rating, self.result.best.quick_rating.rating)
        finally:
            self.engine.config = previous


class EvolutionBudgetTests(unittest.TestCase):
    def test_historical_scalar_champion_survives_pareto_dominance_and_export(self):
        from generator.evolution.selection import dominates
        from generator.evolution.io import export_evolution
        from types import SimpleNamespace
        champion = rated(24, 30., offset=0, als_steps=1)
        frontier = rated(23, 30., offset=30)
        self.assertTrue(dominates(frontier, champion))
        self.assertGreater(champion.fitness, frontier.fitness)
        engine = EvolutionEngine()
        engine.best_seen, engine.archive = None, ()
        engine._remember(champion)
        engine._remember(frontier)
        self.assertEqual(engine._best().key, champion.key)
        self.assertEqual([p.key for p in engine.archive], [frontier.key])
        result = SimpleNamespace(best=engine._best(), archive=engine.archive, seed=42, config=engine.config)
        with patch("generator.evolution.io.to_generated_puzzle", side_effect=lambda p, **kw: p), \
             patch("generator.evolution.io.export_puzzles", side_effect=lambda records, *a, **kw: records):
            self.assertEqual([p.key for p in export_evolution(result, "unused")],
                             [champion.key, frontier.key])

    def test_champion_keeps_new_minimality_evidence_at_equal_fitness(self):
        engine = EvolutionEngine(EvolutionConfig(fitness_config=FitnessConfig(minimality_bonus=0.)))
        original = evaluate_fitness(rated(), engine.config.fitness_config)
        engine.best_seen, engine.archive = None, ()
        engine._remember(original)
        checked = evaluate_fitness(replace(original, minimal=True), engine.config.fitness_config)
        self.assertEqual(checked.fitness, original.fitness)
        engine._remember(checked)
        self.assertTrue(engine._best().minimal)

    def test_deep_selection_covers_old_and_injected_candidates_with_one_budget(self):
        old = replace(rated(24, 30., offset=0, mode="quick"), generation=0)
        injected = replace(rated(24, 35., offset=20, mode="quick"), generation=4, operator="seed")
        child = replace(rated(24, 12., offset=40, mode="quick"), generation=4, operator="swap")
        engine = EvolutionEngine(EvolutionConfig(deep_fraction=1., deep_candidates_per_generation=2))
        with patch.object(engine, "_deep", side_effect=lambda p: p) as deepen:
            result = engine._deepen_top((old, injected, child, old))
        self.assertEqual([call.args[0].key for call in deepen.call_args_list], [injected.key, old.key])
        self.assertEqual(len(result), 4)

    def test_monster_target_requires_minimality(self):
        from generator.evolution.io import target_match
        individual = rated(19, 36., bottlenecks=3, longest_chain=8)
        rating = replace(individual.deep_rating, advanced_steps=5, profile_statuses={"Intermediate": "STUCK"})
        individual = evaluate_fitness(replace(individual, deep_rating=rating, minimal=False))
        self.assertFalse(target_match(individual, EvolutionConfig(mode="monster")))
        self.assertTrue(target_match(replace(individual, minimal=True), EvolutionConfig(mode="monster")))

    def test_local_search_compares_cached_deep_neighbor_with_deep_baseline(self):
        solution = tuple(generate_solution(42))
        candidate = Individual((1 << 30) - 1, solution)
        changed = Individual(candidate.clue_mask ^ 1 ^ (1 << 40), solution)
        quick = DifficultyResult(solved=True, mode="quick", hardest_rating=22., total_score=10.)
        hard = DifficultyResult(solved=True, mode="deep", hardest_required_rating=22.,
            minimum_tier="EXTREME", required_level_verified=True, total_score=10.)
        easier = replace(hard, hardest_required_rating=7., minimum_tier="INTERMEDIATE")
        current = evaluate_fitness(EvolutionIndividual(candidate, unique=True, quick_rating=quick))
        neighbor = evaluate_fitness(EvolutionIndividual(changed, unique=True, quick_rating=quick, deep_rating=easier))
        engine = EvolutionEngine(EvolutionConfig(local_search_budget=1))
        engine.deadline, engine.rng, engine.counters = None, random.Random(42), {}

        def deepen(individual):
            return evaluate_fitness(replace(individual, deep_rating=hard)) if individual.key == current.key else individual

        with patch("generator.evolution.engine.mutate", return_value=changed), \
             patch.object(engine, "_evaluate", return_value=neighbor), \
             patch.object(engine, "_deep", side_effect=deepen) as deep:
            improved = engine._local_improve(current)
        self.assertEqual(improved.key, current.key)
        self.assertEqual(improved.deep_rating.hardest_required_rating, 22.)
        self.assertEqual(deep.call_count, 2)
        self.assertLess(engine.counters["critical_clue_deltas"][0]["delta"], 0.)
        self.assertEqual(engine.counters["critical_clue_deltas"][0]["mode"], "deep")

    def test_empty_timeout_is_honest_and_serializable(self):
        result = evolve(EvolutionConfig(max_seconds=1e-9))
        self.assertTrue(result.timed_out)
        self.assertEqual(result.stop_reason, "time_budget")
        self.assertIsNone(result.best)
        self.assertFalse(result.archive)
        with tempfile.TemporaryDirectory() as directory:
            save_snapshot(result, Path(directory) / "partial.json")

    def test_quick_only_run_never_claims_a_verified_best(self):
        result = evolve(EvolutionConfig(seed=1, population_size=2, elite_size=1,
            random_injection_count=1, max_generations=0, deep_candidates_per_generation=0))
        self.assertEqual(len(result.population), 2)
        self.assertIsNone(result.best)
        self.assertFalse(result.archive)

    def test_cli_timeout_saves_snapshot_without_overwriting_database(self):
        from generator.__main__ import main
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.json"
            path.write_text("existing", encoding="utf-8")
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                status = main(["evolve", "--seed", "42", "--population", "2", "--max-seconds", "0.000000001",
                               "--output", str(path)])
            self.assertEqual(status, 1)
            self.assertEqual(path.read_text(encoding="utf-8"), "existing")
            self.assertTrue(path.with_name("candidates_snapshot.json").exists())

    def test_cli_exports_matching_champion_outside_pareto_archive(self):
        from generator.__main__ import main
        from types import SimpleNamespace
        champion = rated(19, 36., bottlenecks=3, longest_chain=8)
        result = SimpleNamespace(best=champion, archive=(), seed=42,
            generations=1, stop_reason="max_generations", stage_seconds={})
        with tempfile.TemporaryDirectory() as directory, \
             patch("generator.evolution.evolve", return_value=result), \
             patch("generator.evolution.save_snapshot"), \
             patch("generator.evolution.target_match", return_value=True), \
             patch("generator.evolution.export_evolution", return_value={"puzzles": [1]}) as export, \
             redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            status = main(["evolve", "--targets-only", "--output", str(Path(directory) / "out.json")])
        self.assertEqual(status, 0)
        export.assert_called_once()
