"""Immutable rating policy and detector budgets, JSON round-trip supported."""
from dataclasses import asdict, dataclass, fields
from .registry import DEFAULT_REGISTRY, TechniqueRating, TechniqueRegistry, Tier, nonnegative
from ..solver.advanced_config import AdvancedConfig

@dataclass(frozen=True)
class DifficultyConfig:
    registry: TechniqueRegistry = DEFAULT_REGISTRY
    search: AdvancedConfig = AdvancedConfig()
    score_exponent: float = 2.0
    chain_length_factor: float = 1.5
    grouped_node_factor: float = 2.0
    branching_factor: float = 1.0
    als_bonus: float = 4.0
    forcing_bonus: float = 8.0
    search_complexity_factor: float = .01
    advanced_threshold: float = 12.0
    extreme_step_threshold: float = 22.0
    bottleneck_threshold: float = 12.0
    extreme_threshold: float = 30.0
    ultra_threshold: float = 36.0
    minimum_advanced_steps: int = 3
    minimum_bottlenecks: int = 2
    ultra_minimum_advanced_steps: int = 5
    ultra_minimum_bottlenecks: int = 3
    ultra_minimum_chain: int = 8
    ultra_minimum_distributed_bins: int = 2
    late_fraction: float = .65
    distribution_bins: int = 4
    total_rating_factor: float = .1
    bottleneck_rating_factor: float = .05
    distribution_rating_factor: float = .1
    classification_thresholds: tuple = (("Easy", 0.), ("Medium", 2.), ("Hard", 7.), ("Expert", 12.))
    cache_size: int = 512

    def __post_init__(self):
        if not isinstance(self.registry, TechniqueRegistry) or not isinstance(self.search, AdvancedConfig):
            raise ValueError("Invalid registry/search configuration")
        for item in fields(self):
            if item.name not in ("registry", "search", "classification_thresholds"):
                nonnegative(getattr(self, item.name), item.name)
        for name in ("minimum_advanced_steps", "minimum_bottlenecks", "ultra_minimum_advanced_steps",
                     "ultra_minimum_bottlenecks", "ultra_minimum_chain", "distribution_bins",
                     "ultra_minimum_distributed_bins", "cache_size"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")
        if self.distribution_bins < 1 or not 0 <= self.late_fraction <= 1 or self.score_exponent <= 0:
            raise ValueError("Invalid score/profile parameters")
        if self.ultra_threshold < self.extreme_threshold:
            raise ValueError("Ultra threshold must not be lower than Extreme")
        for _,value in self.classification_thresholds:
            nonnegative(value,"classification threshold")
        limits = tuple((name, float(value)) for name,value in self.classification_thresholds)
        if tuple(n for n,_ in limits) != ("Easy", "Medium", "Hard", "Expert"):
            raise ValueError("Classification thresholds must name Easy, Medium, Hard, Expert")
        for _, value in limits:
            nonnegative(value, "classification threshold")
        if limits[0][1] != 0 or any(a[1] >= b[1] for a,b in zip(limits, limits[1:])):
            raise ValueError("Classification thresholds must increase from zero")
        object.__setattr__(self, "classification_thresholds", limits)

    def to_dict(self):
        data = asdict(self)
        data["registry"] = [dict(name=e.name, tier=e.tier.name, base_rating=e.base_rating, weight=e.weight)
                            for e in self.registry.entries]
        return data

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        if "registry" in data:
            data["registry"] = TechniqueRegistry(tuple(TechniqueRating(e["name"], Tier[e["tier"]],
                e["base_rating"], e["weight"]) for e in data["registry"]))
        if "search" in data:
            data["search"] = AdvancedConfig(**data["search"])
        return cls(**data)
