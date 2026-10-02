"""Single-process, budgeted evolutionary search over immutable clue masks.

Quick estimates guide reproduction. Only verified Deep results enter the
archive or become the reported best. Deadlines are cooperative between solver
calls; wall-clock stopping and timings are outside seeded reproducibility.
"""
from collections import OrderedDict
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from math import ceil, isfinite
import random
from secrets import randbits
from statistics import median
from time import perf_counter

from ..chromosome import Individual
from ..construction import FULL_MASK, UniquenessCache, check_minimal, remove_clues
from ..rating.difficulty import DifficultyAnalyzer
from ..solution_generator import generate_solution
from .config import EvolutionConfig
from .fitness import evaluate_fitness
from .models import EvolutionIndividual
from .operators import crossover, mutate
from .repair import ConflictStore, repair_uniqueness
from .selection import mean_diversity, pareto_archive, select_survivors, tournament_select


class _DeadlineReached(Exception):
    pass


@dataclass(frozen=True)
class EvolutionStats:
    generation: int
    best_fitness: float | None
    median_fitness: float | None
    best_required_rating: float | None
    best_bottlenecks: int
    best_advanced_steps: int
    best_clue_count: int | None
    unique_population_size: int
    unique_masks: int
    deep_rated_count: int
    diversity: float
    attempted: int
    accepted: int
    injections: int
    stagnated: bool
    mutation_success_rates: dict
    repair_success_rate: float | None
    archive_size: int
    elapsed_seconds: float
    generation_seconds: float

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class EvolutionResult:
    best: EvolutionIndividual | None
    archive: tuple
    population: tuple
    stats: tuple[EvolutionStats, ...]
    seed: int
    generations: int
    initial_best: EvolutionIndividual | None
    elapsed_seconds: float
    timed_out: bool
    stop_reason: str
    stage_seconds: dict
    stage_calls: dict
    counters: dict
    config: EvolutionConfig


class _TimedUniquenessCache(UniquenessCache):
    def __init__(self, owner):
        super().__init__(owner.config.cache_size)
        self.owner = owner

    def unique(self, candidate):
        self.owner._check()
        self.owner._count("uniqueness_cache_lookups")
        if (candidate.solution, candidate.clue_mask) in self._cache:
            self.owner._count("uniqueness_cache_hits")
        with self.owner._stage("uniqueness"):
            return super().unique(candidate)


class EvolutionEngine:
    """A run owns all caches and a private RNG. Reusing the engine restarts it."""
    def __init__(self, config=None):
        self.config = config if config is not None else EvolutionConfig()
        if not isinstance(self.config, EvolutionConfig):
            raise ValueError("config must be EvolutionConfig")

    def _check(self):
        if self.deadline is not None and perf_counter() >= self.deadline:
            raise _DeadlineReached

    @contextmanager
    def _stage(self, name):
        started = perf_counter()
        try:
            yield
        finally:
            self.stage_seconds[name] = self.stage_seconds.get(name, 0.) + perf_counter() - started
            self.stage_calls[name] = self.stage_calls.get(name, 0) + 1

    def _count(self, name, amount=1):
        self.counters[name] = self.counters.get(name, 0) + amount

    def _put(self, cache, key, value):
        if self.config.cache_size:
            cache[key] = deepcopy(value)
            cache.move_to_end(key)
            while len(cache) > self.config.cache_size:
                cache.popitem(last=False)

    def _rating(self, candidate, mode):
        self._count(mode + "_cache_lookups")
        if self.analyzer.config != self.config.difficulty_config:
            self.analyzer = DifficultyAnalyzer(self.config.difficulty_config)
        key = (candidate.solution, candidate.clue_mask, mode, self.config.difficulty_config)
        if key in self.rating_cache:
            self._count(mode + "_cache_hits")
            self.rating_cache.move_to_end(key)
            return deepcopy(self.rating_cache[key])
        self._check()
        with self._stage(mode + "_rating"):
            result = (self.analyzer.quick(candidate.to_puzzle()) if mode == "quick"
                      else self.analyzer.deep(candidate.to_puzzle(), check_unique=True))
        result.unique = True
        self._put(self.rating_cache, key, result)
        return result

    def _fitness(self, individual):
        self._count("fitness_cache_lookups")
        key = (individual.key, self.config.fitness_config, self.config.difficulty_config,
               individual.minimal, individual.deep_rating is not None)
        cached = self.fitness_cache.get(key)
        if cached is not None:
            self._count("fitness_cache_hits")
            return replace(individual, fitness=cached[0], fitness_vector=cached[1], status=cached[2])
        result = evaluate_fitness(individual, self.config.fitness_config,
                                  registry=self.config.difficulty_config.registry)
        self._put(self.fitness_cache, key, (result.fitness, result.fitness_vector, result.status))
        return result

    def _evaluate(self, candidate, *, generation=0, operator="seed", parents=(), minimal=None):
        self._check()
        if not self.config.min_clues <= candidate.clue_count <= self.config.search_max_clues:
            self._count("clue_range_rejections")
            return None
        if not self.unique_cache.unique(candidate):
            self._count("uniqueness_rejections")
            return None
        quick = self._rating(candidate, "quick")
        individual = EvolutionIndividual(candidate=candidate, unique=True, minimal=minimal,
            quick_rating=quick, generation=generation, operator=operator, parent_keys=parents)
        deep_key = (candidate.solution, candidate.clue_mask, "deep", self.config.difficulty_config)
        if deep_key in self.rating_cache:
            individual = replace(individual, deep_rating=deepcopy(self.rating_cache[deep_key]))
        result = self._fitness(individual)
        if result.status == "REJECTED":
            self._count("invalid_rejections")
            return None
        self._count("evaluated")
        return result

    def _deep(self, individual):
        if individual.deep_rating is None:
            rating = self._rating(individual.candidate, "deep")
            individual = self._fitness(replace(individual, deep_rating=rating))
        # A completed rating remains available even if minimality hits deadline.
        self._remember(individual)
        if individual.minimal is None:
            self._check()
            with self._stage("minimality"):
                minimal = check_minimal(individual.candidate, cache=self.unique_cache, check=self._check)
            individual = self._fitness(replace(individual, minimal=minimal))
        self._remember(individual)
        return individual

    def _remember(self, individual):
        """Scalar champion and non-dominated frontier have distinct contracts."""
        if pareto_archive((individual,), 1):
            if (self.best_seen is None or (individual.key == self.best_seen.key
                    and individual.fitness >= self.best_seen.fitness) or (individual.fitness, individual.fitness_vector, individual.key)
                    > (self.best_seen.fitness, self.best_seen.fitness_vector, self.best_seen.key)):
                self.best_seen = deepcopy(individual)
        self.archive = pareto_archive((*self.archive, individual), self.config.archive_size)

    def _deepen_top(self, population):
        if not population or not self.config.deep_fraction:
            return list(population)
        count = min(self.config.deep_candidates_per_generation,
                    max(1, ceil(len(population) * self.config.deep_fraction)))
        pending = {p.key: p for p in population if p.deep_rating is None}
        candidates = sorted(pending.values(),
                            key=lambda p: (-p.fitness, p.key))[:count]
        updates = {}
        for individual in candidates:
            updates[individual.key] = self._deep(individual)
        return [updates.get(p.key, p) for p in population]

    def _seed(self, solution=None, generation=0):
        self._check()
        with self._stage("seed_construction"):
            if solution is None:
                solution = tuple(generate_solution(self.rng.getrandbits(64)))
            candidate = remove_clues(Individual(FULL_MASK, solution), self.config.min_clues,
                rng=self.rng, cache=self.unique_cache, check=self._check)
        # Full removal pass establishes minimality, unless stopped at the floor.
        minimal = True if candidate.clue_count > self.config.min_clues else None
        return self._evaluate(candidate, generation=generation, operator="seed", minimal=minimal)

    def _initialize(self):
        solutions = [tuple(generate_solution(self.rng.getrandbits(64)))
                     for _ in range(min(self.config.solution_count, self.config.population_size))]
        seen = set()
        for attempt in range(self.config.population_size * self.config.initialization_attempt_factor):
            individual = self._seed(solutions[attempt % len(solutions)])
            if individual is not None and individual.key not in seen:
                self.population.append(individual)
                seen.add(individual.key)
            if len(self.population) == self.config.population_size:
                return

    def _repair(self, candidate, rating):
        if self.unique_cache.unique(candidate):
            return candidate
        with self._stage("repair"):
            result = repair_uniqueness(candidate, rng=self.rng, limit=self.config.repair_limit,
                strategy=self.config.repair_strategy, conflicts=self.conflicts,
                rating=rating, check=self._check)
        self._count("repair_attempts")
        self._count("repair_successes", int(result.unique))
        self._count("repair_added_clues", len(result.added_cells))
        if not result.unique:
            return None
        candidate = result.candidate
        if self.config.reduce_after_repair:
            candidate = remove_clues(candidate, self.config.min_clues, rng=self.rng,
                                     cache=self.unique_cache, check=self._check)
        return candidate

    def _parent(self):
        return tournament_select(self.population, self.rng, size=self.config.tournament_size,
            near_distance=self.config.near_duplicate_distance, penalty=self.config.near_duplicate_penalty)

    def _child(self, generation, strength):
        parent = self._parent()
        candidate, parents = parent.candidate, (parent.key,)
        crossed = False
        with self._stage("mutation"):
            if self.rng.random() < self.config.crossover_rate:
                compatible = [p for p in self.population if p.solution == parent.solution and p.key != parent.key]
                if compatible:
                    other = tournament_select(compatible, self.rng, size=self.config.tournament_size)
                    candidate = crossover(candidate, other.candidate, self.rng)
                    parents += (other.key,)
                    crossed = True
            names, weights = zip(*self.config.mutation_weights)
            operator = self.rng.choices(names, weights=weights, k=1)[0]
            candidate = mutate(candidate, self.rng, operator=operator,
                multi_swap_sizes=self.config.multi_swap_sizes, rating=parent.deep_rating,
                strength=strength)
        self._count("operator_" + operator)
        self._count("crossover_attempts", int(crossed))
        if candidate.clue_count < self.config.min_clues:
            self._count("clue_range_rejections")
            return None
        candidate = self._repair(candidate, parent.deep_rating)
        if candidate is None:
            return None
        if crossed:
            with self._stage("crossover_reduction"):
                candidate = remove_clues(candidate, self.config.min_clues, rng=self.rng,
                    cache=self.unique_cache, check=self._check)
        evaluated = self._evaluate(candidate, generation=generation,
            operator=("crossover+" if crossed else "") + operator, parents=parents)
        self._count("operator_valid_" + operator, int(evaluated is not None))
        return evaluated

    def _local_improve(self, individual):
        """Bounded critical-clue swap deltas; compare equal Deep evidence levels."""
        current = individual
        for _ in range(self.config.local_search_budget):
            self._check()
            candidate = mutate(current.candidate, self.rng, operator="swap")
            # Local deltas must describe the proposed swap, not a repaired puzzle.
            neighbor = self._evaluate(candidate, generation=current.generation,
                operator="local_swap", parents=(current.key,))
            self._count("local_attempts")
            if neighbor is None:
                continue
            if current.deep_rating is not None or neighbor.deep_rating is not None:
                # Cached neighbors may already carry Deep evidence even when
                # the starting child is only Quick-rated. Compare like to like.
                current = self._deep(current)
                neighbor = self._deep(neighbor)
            delta = neighbor.fitness - current.fitness
            self._count("critical_clue_evaluations")
            if isfinite(delta):
                self.counters["critical_clue_best_delta"] = max(
                    self.counters.get("critical_clue_best_delta", delta), delta)
                observations = self.counters.setdefault("critical_clue_deltas", [])
                observations.append({
                    "generation": current.generation,
                    "removed": [i for i in range(81) if current.clue_mask & (1 << i) and not candidate.clue_mask & (1 << i)],
                    "added": [i for i in range(81) if candidate.clue_mask & (1 << i) and not current.clue_mask & (1 << i)],
                    "delta": delta, "mode": "deep" if current.deep_rating is not None else "quick",
                })
                # Keep telemetry bounded just like evaluation caches.
                if len(observations) > self.config.cache_size:
                    del observations[0]
            if delta > 0:
                self._count("local_improvements")
                current = neighbor
        return current

    def _best(self):
        return self.best_seen

    def _record_stats(self, generation, started, attempted=0, accepted=0, injections=0, stagnated=False):
        best = self._best()
        rating = best.deep_rating if best else None
        scores = [p.fitness for p in self.population if isfinite(p.fitness)]
        def delta(name):
            return self.counters.get(name, 0) - self.last_stats_counters.get(name, 0)
        mutation_rates = {name: delta("operator_valid_" + name) / delta("operator_" + name)
                          for name, _ in self.config.mutation_weights if delta("operator_" + name)}
        repair_attempts = delta("repair_attempts")
        stat = EvolutionStats(generation, best.fitness if best else None,
            median(scores) if scores else None,
            rating.hardest_required_rating if rating else None,
            rating.true_bottleneck_count if rating else 0, rating.advanced_steps if rating else 0,
            best.clue_count if best else None,
            len({p.key for p in self.population}), len({p.clue_mask for p in self.population}),
            sum(p.deep_rating is not None for p in self.population),
            mean_diversity(self.population), attempted, accepted, injections, stagnated,
            mutation_rates, delta("repair_successes") / repair_attempts if repair_attempts else None,
            len(self.archive),
            perf_counter() - self.started, perf_counter() - started)
        self.stats.append(stat)
        self.last_stats_counters = dict(self.counters)
        if self.progress:
            self.progress(stat, deepcopy(best))

    def run(self, *, progress=None):
        config = self.config
        self.seed = config.seed if config.seed is not None else randbits(64)
        self.rng = random.Random(self.seed)
        self.started = perf_counter()
        self.deadline = None if config.max_seconds is None else self.started + config.max_seconds
        self.stage_seconds, self.stage_calls, self.counters = {}, {}, {}
        self.last_stats_counters, self.best_seen = {}, None
        self.rating_cache, self.fitness_cache = OrderedDict(), OrderedDict()
        self.unique_cache, self.conflicts = _TimedUniquenessCache(self), ConflictStore()
        self.analyzer = DifficultyAnalyzer(config.difficulty_config)
        self.population, self.archive, self.stats = [], (), []
        self.progress = progress
        initial_best, generations, stagnation = None, 0, 0
        timed_out, stop_reason = False, "max_generations"
        try:
            self._initialize()
            self.population = self._deepen_top(self.population)
            initial_best = deepcopy(self._best())
            self._record_stats(0, self.started)
            if len(self.population) < config.population_size:
                stop_reason = "initialization_budget"
            else:
                for generation in range(1, config.max_generations + 1):
                    self._check()
                    started = perf_counter()
                    previous_best = self._best()
                    stagnated = stagnation >= config.stagnation_generations
                    elites = sorted(self.population, key=lambda p: (-p.fitness, p.key))[:config.elite_size]
                    children, seen, attempted = [], {p.key for p in self.population}, 0
                    while len(children) < config.offspring_count and attempted < config.offspring_count * config.offspring_attempt_factor:
                        self._check()
                        attempted += 1
                        child = self._child(generation, config.stagnation_strength if stagnated else 1)
                        if child is not None and child.key not in seen:
                            children.append(child)
                            seen.add(child.key)
                        elif child is not None:
                            self._count("duplicate_rejections")
                    for child in sorted(children, key=lambda p: (-p.fitness, p.key))[:config.local_search_candidates]:
                        with self._stage("local_search"):
                            improved = self._local_improve(child)
                        if improved.key != child.key:
                            children.append(improved)
                    injections = []
                    if stagnated or generation % config.injection_interval == 0:
                        for _ in range(config.random_injection_count * config.initialization_attempt_factor):
                            if len(injections) == config.random_injection_count:
                                break
                            injected = self._seed(generation=generation)
                            if injected is not None and injected.key not in seen:
                                injections.append(injected)
                                seen.add(injected.key)
                    # One staged budget sees old provisional candidates and fresh
                    # injections as well as offspring. No source is starved forever.
                    pool = self._deepen_top((*self.population, *children, *injections))
                    evaluated = {p.key: p for p in pool}
                    preserved = [evaluated[p.key] for p in (*elites, *injections)]
                    # Elites keep their chromosomes; newly obtained evidence may
                    # update their ratings. Invalid human states cannot survive.
                    pool = [p for p in pool if p.status != "REJECTED"]
                    preserved = [p for p in preserved if p.status != "REJECTED"]
                    self.population = list(select_survivors(pool,
                        config.population_size, elites=preserved,
                        near_distance=config.near_duplicate_distance, penalty=config.near_duplicate_penalty))
                    best = self._best()
                    stagnation = (0 if best is not None and (previous_best is None or best.fitness > previous_best.fitness)
                                  else stagnation + 1)
                    if stagnated:
                        self._count("stagnation_responses")
                        stagnation = 0
                    generations = generation
                    self._record_stats(generation, started, attempted, len(children), len(injections), stagnated)
        except _DeadlineReached:
            timed_out, stop_reason = True, "time_budget"
        finally:
            self.deadline = None
        return EvolutionResult(deepcopy(self._best()), deepcopy(self.archive), tuple(deepcopy(self.population)),
            tuple(self.stats), self.seed, generations, initial_best, perf_counter() - self.started,
            timed_out, stop_reason, dict(self.stage_seconds), dict(self.stage_calls), dict(self.counters), config)


def evolve(config=None, *, progress=None):
    return EvolutionEngine(config).run(progress=progress)
