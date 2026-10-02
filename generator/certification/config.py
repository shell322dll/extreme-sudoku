"""One explicit policy for fresh, conservative production certification."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import isfinite

from ..solver.advanced_config import AdvancedConfig
from ..rating.config import DifficultyConfig

CERTIFICATION_VERSION = "1"


@dataclass(frozen=True)
class CertificationConfig:
    time_budget: float = 60.0
    node_budget: int = 10000
    state_budget: int = 10000
    max_path_depth: int = 256
    max_alternative_steps_per_state: int = 512
    max_chain_length: int = 19
    max_als_size: int = 4
    max_chain_search_nodes: int = 100000
    max_als_search_nodes: int = 30000
    max_als_chain_length: int = 5
    max_forcing_depth: int = 12
    max_forcing_nodes: int = 2000
    max_forcing_starts: int = 160
    extreme_threshold: float = DifficultyConfig().extreme_threshold
    ultra_threshold: float = DifficultyConfig().ultra_threshold
    required_bottlenecks_extreme: int = DifficultyConfig().minimum_bottlenecks
    required_bottlenecks_ultra: int = DifficultyConfig().ultra_minimum_bottlenecks
    minimum_advanced_steps: int = DifficultyConfig().minimum_advanced_steps
    ultra_minimum_advanced_steps: int = DifficultyConfig().ultra_minimum_advanced_steps
    ultra_minimum_chain: int = DifficultyConfig().ultra_minimum_chain
    ultra_minimum_distributed_bins: int = DifficultyConfig().ultra_minimum_distributed_bins
    advanced_threshold: float = DifficultyConfig().advanced_threshold
    bottleneck_threshold: float = DifficultyConfig().bottleneck_threshold
    extreme_step_threshold: float = DifficultyConfig().extreme_step_threshold
    distribution_bins: int = DifficultyConfig().distribution_bins
    late_fraction: float = DifficultyConfig().late_fraction
    require_minimal: bool = False
    # Phase 7.1: try the Stuck-State Superset Lemma (SSL-v1) before the exhaustive
    # threshold search. False reproduces the pure exhaustive behaviour.
    use_stuck_state_lemma: bool = True

    def __post_init__(self):
        for name, value in asdict(self).items():
            if name in {"require_minimal", "use_stuck_state_lemma"}:
                if type(value) is not bool:
                    raise ValueError(f"{name} must be Boolean")
            elif name in {"time_budget", "extreme_threshold", "ultra_threshold", "advanced_threshold",
                          "bottleneck_threshold", "extreme_step_threshold", "late_fraction"}:
                if type(value) not in (int, float) or not isfinite(value) or value < 0:
                    raise ValueError(f"{name} must be finite and nonnegative")
            elif type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not 1 <= self.max_als_size <= 8 or not 0 <= self.late_fraction <= 1:
            raise ValueError("Invalid ALS size or late fraction")
        if self.ultra_threshold < self.extreme_threshold:
            raise ValueError("Ultra threshold must not be lower than Extreme")
        default = DifficultyConfig()
        floors = {"extreme_threshold": default.extreme_threshold, "ultra_threshold": default.ultra_threshold,
            "required_bottlenecks_extreme": default.minimum_bottlenecks,
            "required_bottlenecks_ultra": default.ultra_minimum_bottlenecks,
            "minimum_advanced_steps": default.minimum_advanced_steps,
            "ultra_minimum_advanced_steps": default.ultra_minimum_advanced_steps,
            "ultra_minimum_chain": default.ultra_minimum_chain,
            "ultra_minimum_distributed_bins": default.ultra_minimum_distributed_bins}
        if any(getattr(self, name) < floor for name, floor in floors.items()):
            raise ValueError("Certification policy cannot weaken the existing product criteria")
        if (self.advanced_threshold != default.advanced_threshold
                or self.bottleneck_threshold != default.bottleneck_threshold
                or self.extreme_step_threshold != default.extreme_step_threshold
                or self.distribution_bins != default.distribution_bins):
            raise ValueError("Metric definitions must retain the existing product scale")

    @property
    def advanced_config(self):
        return AdvancedConfig(max_x_chain_length=self.max_chain_length,
            max_xy_chain_length=self.max_chain_length, max_aic_length=self.max_chain_length,
            max_grouped_aic_length=self.max_chain_length,
            max_chain_search_nodes=self.max_chain_search_nodes, max_als_size=self.max_als_size,
            max_als_chain_length=self.max_als_chain_length,
            max_als_search_nodes=self.max_als_search_nodes, max_forcing_depth=self.max_forcing_depth,
            max_forcing_nodes=self.max_forcing_nodes, max_forcing_starts=self.max_forcing_starts)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def fingerprint(self):
        return sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()
