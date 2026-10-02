"""Ordinary seeded generation, reusable rating, filtering, and bounded batches."""
from collections import OrderedDict
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import random
from secrets import randbits
from time import perf_counter

from .chromosome import Individual
from .config import GeneratorConfig
from .construction import (FULL_MASK, UniquenessCache, check_minimal, minimalize,
                           remove_clues, validate_candidate)
from .models import (BatchResult, GeneratedPuzzle, GenerationError, GenerationStats,
                     RejectionReason)
from .rating.difficulty import DifficultyAnalyzer
from .rating.profiles import solve_with_max_rating
from .solution_generator import generate_solution
from .solver.human_solver import HumanSolver


class _DeadlineReached(Exception):
    pass


class PuzzleGenerator:
    """One immutable configuration; each generate_many call restarts its seed.

    Timeout is cooperative: it is checked between stages and clue attempts.
    A running solver call completes before the deadline can be observed.
    Timings and deadlines are intentionally outside reproducibility guarantees.
    """
    def __init__(self, config=None):
        self.config = config if config is not None else GeneratorConfig()
        if not isinstance(self.config, GeneratorConfig):
            raise ValueError("config must be a GeneratorConfig")
        self.analyzer = DifficultyAnalyzer(self.config.difficulty_config)
        self._rating_cache = OrderedDict()
        self._cache_config = self.config.difficulty_config
        self.stats = GenerationStats()
        self._deadline = None

    def _check_deadline(self):
        if self._deadline is not None and perf_counter() >= self._deadline:
            raise _DeadlineReached

    @contextmanager
    def _stage(self, name):
        started = perf_counter()
        try:
            yield
        finally:
            self.stats.stage_seconds[name] = self.stats.stage_seconds.get(name, 0.) + perf_counter() - started
            self.stats.stage_calls[name] = self.stats.stage_calls.get(name, 0) + 1

    def _rating(self, candidate, mode):
        # Public config replacement and a changed rating policy cannot reuse old
        # results. Returned mutable records never alias the cache or each other.
        policy = self.config.difficulty_config
        if policy != self._cache_config:
            self.analyzer = DifficultyAnalyzer(policy)
            self._rating_cache.clear()
            self._cache_config = policy
        key = (candidate.solution, candidate.clue_mask, mode, policy)
        if key in self._rating_cache:
            self._rating_cache.move_to_end(key)
            return deepcopy(self._rating_cache[key])
        self._check_deadline()
        with self._stage(mode + "_rating"):
            board = candidate.to_puzzle()
            result = (self.analyzer.quick(board) if mode == "quick"
                      else self.analyzer.deep(board, check_unique=True))
        result.unique = True  # Caller has independently validated this candidate.
        if policy.cache_size:
            self._rating_cache[key] = deepcopy(result)
            while len(self._rating_cache) > policy.cache_size:
                self._rating_cache.popitem(last=False)
        self._check_deadline()
        return result

    def _rate_validated(self, candidate):
        mode = self.config.rating_mode
        if mode == "deep":
            return self._rating(candidate, "deep")
        quick = self._rating(candidate, "quick")
        if mode == "quick":
            # Even explicit Quick mode must preserve a accidentally discovered
            # promising Extreme candidate with a real Deep assessment.
            if quick.hardest_rating >= self.config.difficulty_config.extreme_threshold:
                return self._rating(candidate, "deep")
            return quick
        threshold = dict(self.config.difficulty_config.classification_thresholds)["Expert"]
        target = self.config.target_difficulty
        thresholds = dict(self.config.difficulty_config.classification_thresholds)
        target_floor = thresholds.get(target)
        # Deep can lower a greedy rating or solve a Quick-stuck puzzle through
        # another bounded profile. Never pre-reject these promising candidates.
        needs_deep = (not quick.solved or quick.hardest_rating >= threshold
                      or (target_floor is not None and quick.hardest_rating > target_floor
                          and quick.difficulty_class != target))
        return self._rating(candidate, "deep") if needs_deep else quick

    def rate_candidate(self, candidate: Individual):
        """Reusable fresh uniqueness -> configured human rating; no known solution
        is supplied to Human Solver. Useful for future mask-based callers.
        """
        if not validate_candidate(candidate):
            raise ValueError("rating requires a unique candidate")
        return self._rate_validated(candidate)

    def _construct(self, seed):
        rng = random.Random(seed)
        with self._stage("solution_generation"):
            candidate = Individual(FULL_MASK, generate_solution(seed))
        self.stats.generated_complete_grids += 1
        self._check_deadline()
        cache = UniquenessCache(self.config.difficulty_config.cache_size)
        target = rng.randint(self.config.min_clues, self.config.max_clues)
        with self._stage("clue_removal"):
            candidate = remove_clues(candidate, target, rng=rng, cache=cache,
                                     check=self._check_deadline)
        if self.config.require_minimal:
            with self._stage("minimalization"):
                candidate = minimalize(candidate, rng=rng, cache=cache,
                                       check=self._check_deadline)
        return candidate, cache

    def _record(self, candidate, result, minimal, run_seed, attempt_seed):
        self._check_deadline()
        with self._stage("human_path"):
            policy = self.config.difficulty_config
            if result.mode == "deep" and result.hardest_required_rating is not None:
                human = solve_with_max_rating(candidate.to_puzzle(), result.hardest_required_rating,
                                              config=policy)
            else:
                weights = {entry.name: entry.base_rating for entry in policy.registry.entries}
                human = HumanSolver(weights=weights, config=policy.search).solve(candidate.to_puzzle())
        if not human.solved or tuple(human.grid) != candidate.solution or human.used_backtracking or human.guesses:
            raise ValueError("accepted human path does not reproduce the unique solution")
        self._check_deadline()
        puzzle = "".join(map(str, candidate.to_puzzle()))
        result = deepcopy(result)
        result.minimal = minimal
        return GeneratedPuzzle(
            id="puzzle-" + sha256(puzzle.encode("ascii")).hexdigest()[:20],
            puzzle=puzzle, solution="".join(map(str, candidate.solution)),
            clues=candidate.clue_count, unique=True, minimal=minimal,
            difficulty=result.difficulty_class, rating=result.rating,
            difficulty_result=result, human_result=human, seed=run_seed,
            attempt_seed=attempt_seed, attempts=self.stats.attempts, clue_mask=candidate.clue_mask)

    def _attempt(self, run_seed, attempt_seed, seen):
        candidate, cache = self._construct(attempt_seed)
        if not self.config.min_clues <= candidate.clue_count <= self.config.max_clues:
            return None, RejectionReason.OUTSIDE_CLUE_RANGE
        with self._stage("uniqueness_validation"):
            unique = validate_candidate(candidate)
        self._check_deadline()
        if not unique:
            return None, RejectionReason.NOT_UNIQUE
        puzzle = "".join(map(str, candidate.to_puzzle()))
        if puzzle in seen:
            return None, RejectionReason.DUPLICATE
        result = self._rate_validated(candidate)
        if not result.solved or result.invalid or result.difficulty_class == "Unrated" or result.used_backtracking or result.guesses:
            return None, RejectionReason.HUMAN_UNSOLVED
        wrong = (self.config.target_difficulty is not None
                 and result.difficulty_class != self.config.target_difficulty)
        if wrong and result.difficulty_class not in ("Extreme", "Ultra Extreme"):
            return None, RejectionReason.WRONG_DIFFICULTY
        with self._stage("minimality_check"):
            minimal = check_minimal(candidate, cache=cache, check=self._check_deadline)
        if self.config.require_minimal and not minimal:
            raise ValueError("minimalization failed its independent clue-deletion verification")
        record = self._record(candidate, result, minimal, run_seed, attempt_seed)
        return record, RejectionReason.WRONG_DIFFICULTY if wrong else None

    def generate_many(self, count, *, progress=None):
        """Return partial results honestly after a GLOBAL batch attempt budget."""
        if type(count) is not int or count < 1:
            raise ValueError("count must be a positive integer")
        started = perf_counter()
        run_seed = self.config.seed if self.config.seed is not None else randbits(64)
        rng = random.Random(run_seed)
        self.stats = GenerationStats()
        # Each run has identical cache behavior; timings alone can still vary.
        self._rating_cache.clear()
        self.analyzer.state_analyzer.clear_cache()
        self._deadline = (None if self.config.timeout_seconds is None
                          else started + self.config.timeout_seconds)
        accepted, preliminary, seen = [], [], set()
        try:
            for _ in range(self.config.max_attempts):
                self._check_deadline()
                self.stats.attempts += 1
                attempt_seed = rng.getrandbits(64)
                with self._stage("attempt"):
                    record, reason = self._attempt(run_seed, attempt_seed, seen)
                if reason is not None:
                    self.stats.reject(reason)
                    if record is not None:
                        preliminary.append(record)
                        seen.add(record.puzzle)
                else:
                    accepted.append(record)
                    seen.add(record.puzzle)
                    self.stats.accepted += 1
                self.stats.elapsed_seconds = perf_counter() - started
                if progress:
                    progress(deepcopy(self.stats), record)
                if len(accepted) == count:
                    break
        except _DeadlineReached:
            self.stats.timed_out = True
        finally:
            self.stats.elapsed_seconds = perf_counter() - started
            self._deadline = None
        return BatchResult(tuple(accepted), count, run_seed, deepcopy(self.stats), tuple(preliminary))


def generate_many(count, config=None, *, progress=None):
    return PuzzleGenerator(config).generate_many(count, progress=progress)


def generate_puzzle(config=None):
    result = generate_many(1, config)
    if not result.complete:
        raise GenerationError(result)
    return result.puzzles[0]
