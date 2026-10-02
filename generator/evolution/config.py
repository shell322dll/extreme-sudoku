"""All search budgets, coefficients and target profiles in one explicit policy."""
from dataclasses import asdict, dataclass, fields, replace
from math import isfinite

from .fitness import FitnessConfig
from ..rating.config import DifficultyConfig


@dataclass(frozen=True)
class TargetProfile:
    required_rating: float = 0.0
    bottlenecks: int = 0
    advanced_steps: int = 0
    longest_chain: int = 0
    reject_intermediate: bool = False
    prefer_minimal: bool = True
    require_minimal: bool = False

    def __post_init__(self):
        if type(self.required_rating) not in (float, int) or not isfinite(self.required_rating) or self.required_rating < 0:
            raise ValueError("required_rating must be finite and nonnegative")
        for name in ("bottlenecks", "advanced_steps", "longest_chain"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if any(type(v) is not bool for v in (self.reject_intermediate, self.prefer_minimal, self.require_minimal)):
            raise ValueError("target flags must be booleans")


BALANCED = TargetProfile()
EXTREME_SEARCH = TargetProfile(30., 2, 3, 0, True)
MONSTER_SEARCH = TargetProfile(36., 3, 5, 8, True, require_minimal=True)


def fitness_for_mode(mode):
    """Search preferences never alter the evidence or classification thresholds."""
    base = FitnessConfig()
    if mode == "extreme":
        return replace(base, bottleneck_weight=200., advanced_step_weight=30.)
    if mode == "monster":
        return replace(base, bottleneck_weight=300., advanced_step_weight=40.,
                       chain_weight=20., longest_chain_weight=5., als_weight=10., forcing_weight=15.)
    if mode == "min_clues":
        return replace(base, clue_bonus=200000.)
    return base


@dataclass(frozen=True)
class EvolutionConfig:
    seed: int | None = None
    population_size: int = 32
    elite_size: int = 3
    offspring_count: int = 32
    random_injection_count: int = 3
    injection_interval: int = 5
    max_generations: int = 30
    solution_count: int = 4
    min_clues: int = 17
    max_clues: int = 21
    search_max_clues: int = 32
    tournament_size: int = 5
    crossover_rate: float = .1
    multi_swap_sizes: tuple = (2, 3)
    mutation_weights: tuple = (("remove", .15), ("add", .1), ("swap", .35),
                               ("multi_swap", .2), ("region", .1), ("guided", .1))
    repair_limit: int = 5
    repair_strategy: str = "coverage"
    deep_fraction: float = .05
    deep_candidates_per_generation: int = 2
    local_search_candidates: int = 1
    local_search_budget: int = 3
    stagnation_generations: int = 8
    stagnation_strength: int = 2
    near_duplicate_distance: int = 4
    near_duplicate_penalty: float = .02
    cache_size: int = 4096
    archive_size: int = 100
    initialization_attempt_factor: int = 20
    offspring_attempt_factor: int = 10
    reduce_after_repair: bool = False
    max_seconds: float | None = None
    mode: str = "balanced"
    fitness_config: FitnessConfig | None = None
    difficulty_config: DifficultyConfig = DifficultyConfig()
    target: TargetProfile | None = None

    def __post_init__(self):
        positive = ("population_size", "offspring_count", "injection_interval", "solution_count",
                    "tournament_size", "stagnation_generations", "stagnation_strength", "archive_size",
                    "initialization_attempt_factor", "offspring_attempt_factor")
        nonnegative = ("elite_size", "random_injection_count", "max_generations", "repair_limit",
                       "deep_candidates_per_generation", "local_search_candidates", "local_search_budget",
                       "near_duplicate_distance", "cache_size")
        for name in positive + nonnegative:
            value = getattr(self, name)
            if type(value) is not int or value < (1 if name in positive else 0):
                raise ValueError(f"invalid integer budget: {name}")
        if self.seed is not None and type(self.seed) is not int:
            raise ValueError("seed must be an integer or None")
        if not self.elite_size < self.population_size:
            raise ValueError("elite_size must be smaller than population_size")
        if self.random_injection_count > self.population_size - self.elite_size:
            raise ValueError("random injections must leave room for elites")
        if any(type(v) is not int for v in (self.min_clues, self.max_clues, self.search_max_clues)):
            raise ValueError("clue limits must be integers")
        if not 17 <= self.min_clues <= self.max_clues <= self.search_max_clues <= 81:
            raise ValueError("require 17 <= min_clues <= max_clues <= search_max_clues <= 81")
        for name in ("crossover_rate", "deep_fraction", "near_duplicate_penalty"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must lie in [0,1]")
        if self.max_seconds is not None and (type(self.max_seconds) not in (int, float)
                or not isfinite(self.max_seconds) or self.max_seconds <= 0):
            raise ValueError("max_seconds must be finite and positive")
        if self.repair_strategy not in ("random", "coverage", "guided"):
            raise ValueError("unknown repair strategy")
        if self.mode not in ("balanced", "extreme", "monster", "min_clues"):
            raise ValueError("unknown search mode")
        if self.fitness_config is None:
            object.__setattr__(self, "fitness_config", fitness_for_mode(self.mode))
        if self.target is None:
            object.__setattr__(self, "target", {"balanced": BALANCED, "extreme": EXTREME_SEARCH,
                "monster": MONSTER_SEARCH, "min_clues": BALANCED}[self.mode])
        if type(self.reduce_after_repair) is not bool:
            raise ValueError("reduce_after_repair must be boolean")
        if not isinstance(self.fitness_config, FitnessConfig) or not isinstance(self.difficulty_config, DifficultyConfig) or not isinstance(self.target, TargetProfile):
            raise ValueError("invalid policy configuration")
        sizes = tuple(self.multi_swap_sizes)
        if not sizes or any(type(n) is not int or not 1 <= n <= 40 for n in sizes):
            raise ValueError("multi_swap_sizes must contain counts from 1 to 40")
        weights = tuple(tuple(pair) for pair in self.mutation_weights)
        if (not weights or any(len(pair) != 2 for pair in weights)
                or any(name not in ("remove", "add", "swap", "multi_swap", "region", "guided") for name, _ in weights)
                or len({name for name, _ in weights}) != len(weights)):
            raise ValueError("invalid mutation operators")
        if any(type(w) not in (int, float) or not isfinite(w) or w < 0 for _, w in weights) or not sum(w for _, w in weights):
            raise ValueError("mutation weights must be finite nonnegative with positive sum")
        object.__setattr__(self, "multi_swap_sizes", sizes)
        object.__setattr__(self, "mutation_weights", weights)

    @classmethod
    def for_mode(cls, mode="balanced", **kwargs):
        profiles = {"balanced": BALANCED, "extreme": EXTREME_SEARCH,
                    "monster": MONSTER_SEARCH, "min_clues": BALANCED}
        if mode not in profiles:
            raise ValueError("unknown search mode")
        kwargs.setdefault("target", profiles[mode])
        return cls(mode=mode, **kwargs)

    def to_dict(self):
        result = asdict(self)
        result["difficulty_config"] = self.difficulty_config.to_dict()
        return result

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        for name, factory in (("fitness_config", FitnessConfig), ("target", TargetProfile)):
            if name in data:
                data[name] = factory(**data[name])
        if "difficulty_config" in data:
            data["difficulty_config"] = DifficultyConfig.from_dict(data["difficulty_config"])
        return cls(**data)
