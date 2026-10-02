"""Required levels within deterministic bounded runs, not minimax proofs."""
from dataclasses import dataclass
from .config import DifficultyConfig
from .profiles import solve_with_max_rating,solve_with_disabled_techniques,status
from ..sudoku.grid import validate_grid

@dataclass(frozen=True)
class ThresholdResult:
    max_rating: float
    status: str

@dataclass
class RequiredLevel:
    solved: bool
    rating: float | None
    technique: str | None
    tier: str | None
    verified: bool
    attempts: tuple[ThresholdResult,...]
    solution: object = None
    scope: str = "lowest successful tested threshold; bounded deterministic paths, not global necessity"

def required_level(puzzle,*,config=None):
    config=config or DifficultyConfig()
    puzzle=validate_grid(puzzle)
    attempts=[]
    # No binary search: bounded detectors may behave non-monotonically when
    # earlier deductions alter the search budget allocation on later states.
    thresholds=sorted({0.0} | {e.base_rating for e in config.registry.entries})
    for rating in thresholds:
        solved=solve_with_max_rating(puzzle,rating,config=config)
        attempts.append(ThresholdResult(rating,status(solved)))
        if solved.solved:
            hardest=min(solved.steps,key=lambda s:(-config.registry.rating_of(s.technique),s.technique),default=None)
            tier=max((config.registry.tier_of(s.technique) for s in solved.steps),default=None)
            return RequiredLevel(True,rating,hardest.technique if hardest else None,
                tier.name if tier is not None else "TRIVIAL",
                all(a.status=="STUCK" for a in attempts[:-1]),tuple(attempts),solved)
    return RequiredLevel(False,None,None,None,False,tuple(attempts))

@dataclass(frozen=True)
class TechniqueNecessity:
    technique: str
    baseline_status: str
    disabled_status: str
    necessary_within_solver: bool
    scope: str = "bounded deterministic implemented repertoire, not all logical paths"

def technique_necessity(puzzle,technique,*,config=None):
    config=config or DifficultyConfig()
    config.registry.get(technique)
    puzzle=validate_grid(puzzle)
    baseline=solve_with_disabled_techniques(puzzle,set(),config=config)
    disabled=solve_with_disabled_techniques(puzzle,{technique},config=config)
    return TechniqueNecessity(technique,status(baseline),status(disabled),baseline.solved and disabled.stuck)
