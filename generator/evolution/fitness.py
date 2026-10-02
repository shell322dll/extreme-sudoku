"""Explainable configurable objectives; observed Quick scores are provisional."""
from dataclasses import dataclass, fields, replace
from math import log1p

from ..rating.registry import DEFAULT_REGISTRY, nonnegative


@dataclass(frozen=True)
class FitnessConfig:
    required_level_weight: float = 10000.0
    required_rating_weight: float = 1000.0
    bottleneck_weight: float = 100.0
    advanced_step_weight: float = 20.0
    extreme_step_weight: float = 10.0
    total_score_weight: float = 1.0
    chain_weight: float = 5.0
    longest_chain_weight: float = 1.0
    als_weight: float = 2.0
    forcing_weight: float = 3.0
    clue_bonus: float = 0.1
    minimality_bonus: float = 0.1

    def __post_init__(self):
        for item in fields(self):
            nonnegative(getattr(self, item.name), item.name)


def evaluate_fitness(individual, config=None, *, registry=DEFAULT_REGISTRY):
    """Return a fresh record; no scalar cache can survive a policy change.

    Logarithmic secondary features bound their influence in practical search.
    Quick uses an explicitly provisional tier on the same scale as Deep, so
    purchasing a Deep evaluation does not itself earn a tier bonus. Only Deep
    contributes genuine bottlenecks or qualifies for the verified archive.
    """
    config = config or FitnessConfig()
    result = individual.deep_rating or individual.quick_rating
    status = "UNRATED"
    if individual.clue_count < 17 or individual.unique is False:
        status = "REJECTED"
    elif result is not None and (result.invalid or result.used_backtracking or result.guesses):
        status = "REJECTED"
    elif result is not None and not result.solved:
        status = "HUMAN_UNSOLVED"
    elif individual.unique is True and result is not None:
        status = "DEEP_RATED" if result.mode == "deep" and result.required_level_verified else "QUICK_RATED"
        if result.mode == "deep" and not result.required_level_verified:
            status = "UNRATED"
    if status not in ("QUICK_RATED", "DEEP_RATED"):
        return replace(individual, fitness=float("-inf"), fitness_vector=(), status=status)

    verified = status == "DEEP_RATED"
    required = result.hardest_required_rating if verified else result.hardest_rating
    if required is None:
        return replace(individual, fitness=float("-inf"), fitness_vector=(), status="UNRATED")
    tier = ({"TRIVIAL": 0, "BASIC": 1, "INTERMEDIATE": 2, "ADVANCED": 3, "EXTREME": 4}.get(result.minimum_tier, 0)
            if verified else max((int(e.tier) for e in registry.entries if e.base_rating <= required), default=0))
    bottlenecks = result.true_bottleneck_count if verified else 0
    advanced = result.advanced_steps + result.extreme_steps
    vector = (float(required), bottlenecks, advanced, result.chain_complexity,
              result.total_score, -individual.clue_count)
    score = (config.required_level_weight * tier
             + config.required_rating_weight * required
             + config.bottleneck_weight * log1p(bottlenecks)
             + config.advanced_step_weight * log1p(result.advanced_steps)
             + config.extreme_step_weight * log1p(result.extreme_steps)
             + config.total_score_weight * log1p(result.total_score)
             + config.chain_weight * log1p(result.chain_complexity)
             + config.longest_chain_weight * log1p(result.longest_chain)
             + config.als_weight * log1p(result.als_steps)
             + config.forcing_weight * log1p(result.forcing_steps)
             + config.clue_bonus * max(0, 82 - individual.clue_count)
             + config.minimality_bonus * (individual.minimal is True))
    return replace(individual, fitness=score, fitness_vector=vector, status=status)
