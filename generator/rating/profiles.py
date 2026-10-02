"""Centralized repertoire policies; Phase numbers are not difficulty tiers."""
from dataclasses import dataclass
from .config import DifficultyConfig
from .registry import Tier, nonnegative
from ..solver.human_solver import HumanSolver
from ..solver.techniques import default_techniques

@dataclass(frozen=True)
class SolverProfile:
    name: str
    max_tier: Tier = Tier.EXTREME
    max_rating: float | None = None
    disabled: frozenset[str] = frozenset()

    def __post_init__(self):
        if not isinstance(self.max_tier,Tier):
            raise ValueError("max_tier must be a Tier")
        if self.max_rating is not None:
            nonnegative(self.max_rating,"max_rating")
        object.__setattr__(self,"disabled",frozenset(self.disabled))

BASIC_PROFILE = SolverProfile("Basic",Tier.BASIC)
INTERMEDIATE_PROFILE = SolverProfile("Intermediate",Tier.INTERMEDIATE)
ADVANCED_PROFILE = SolverProfile("Advanced",Tier.ADVANCED)
EXTREME_PROFILE = SolverProfile("Extreme",Tier.EXTREME)
PROFILES = (BASIC_PROFILE,INTERMEDIATE_PROFILE,ADVANCED_PROFILE,EXTREME_PROFILE)

def solver_for_profile(profile=EXTREME_PROFILE, config=None):
    config=config or DifficultyConfig()
    registry=config.registry
    for name in profile.disabled:
        registry.get(name)
    weights={e.name:e.base_rating for e in registry.entries}
    techniques=default_techniques(weights,config=config.search)
    # Missing registry entries are errors rather than quietly unrated detectors.
    selected=[t for t in techniques if registry.tier_of(t.name)<=profile.max_tier
              and (profile.max_rating is None or registry.rating_of(t.name)<=profile.max_rating)
              and t.name not in profile.disabled]
    return HumanSolver(selected)

def solve_with_profile(puzzle, profile, *, config=None):
    return solver_for_profile(profile,config).solve(puzzle)

def solve_with_max_rating(puzzle,max_rating,*,config=None):
    return solve_with_profile(puzzle,SolverProfile("Threshold",max_rating=max_rating),config=config)

def solve_with_max_tier(puzzle,max_tier,*,config=None):
    if isinstance(max_tier,bool):
        raise ValueError("max_tier must not be Boolean")
    tier=Tier[max_tier.upper()] if isinstance(max_tier,str) else Tier(max_tier)
    return solve_with_profile(puzzle,SolverProfile(tier.name,max_tier=tier),config=config)

def solve_with_disabled_techniques(puzzle,disabled,*,config=None):
    return solve_with_profile(puzzle,SolverProfile("Disabled",disabled=frozenset(disabled)),config=config)

def status(result):
    return "INVALID" if result.invalid else "SOLVED" if result.solved else "STUCK"
