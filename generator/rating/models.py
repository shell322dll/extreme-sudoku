"""Explainable rating records; timing/cache counters intentionally excluded."""
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Bottleneck:
    step_index: int
    state_signature: tuple
    required_rating: float
    required_technique: str
    minimum_step_count: int
    easier_steps_available: int = 0
    genuine: bool = True
    group_id: int = 0
    # All claims are relative to the bounded implemented repertoire.
    scope: str = "bounded implemented techniques"

@dataclass
class DifficultyResult:
    solved: bool
    mode: str
    difficulty_class: str = "Unrated"
    rating: float = 0.0
    hardest_technique: str | None = None
    hardest_rating: float = 0.0
    hardest_required_technique: str | None = None
    hardest_required_rating: float | None = None
    minimum_tier: str | None = None
    total_score: float = 0.0
    step_count: int = 0
    advanced_steps: int = 0
    extreme_steps: int = 0
    chain_steps: int = 0
    longest_chain: int = 0
    chain_complexity: float = 0.0
    als_steps: int = 0
    forcing_steps: int = 0
    bottlenecks: list[Bottleneck] = field(default_factory=list)
    true_bottleneck_count: int = 0
    max_bottleneck_rating: float = 0.0
    bottleneck_severity: float = 0.0
    difficulty_profile: list[float] = field(default_factory=list)
    peak_rating: float = 0.0
    high_peak_count: int = 0
    peak_positions: list[int] = field(default_factory=list)
    late_peak_count: int = 0
    distributed_advanced_steps: int = 0
    advanced_distribution: list[int] = field(default_factory=list)
    late_bottleneck_count: int = 0
    state_signatures: list[tuple] = field(default_factory=list)
    profile_statuses: dict[str, str] = field(default_factory=dict)
    threshold_results: list = field(default_factory=list)
    required_level_verified: bool = False
    clue_count: int = 0
    unique: bool | None = None
    minimal: bool | None = None
    invalid: bool = False
    used_backtracking: bool = False
    guesses: int = 0
    is_extreme_candidate: bool = False
    is_ultra_extreme_candidate: bool = False
    preliminary: bool = True
    scope: str = "deterministic bounded human solver; no exhaustive alternative-path proof"
