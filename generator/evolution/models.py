"""Immutable evolutionary records referencing the existing clue chromosome."""
from copy import deepcopy
from dataclasses import dataclass

from ..chromosome import Individual
from ..rating.models import DifficultyResult


@dataclass(frozen=True)
class EvolutionIndividual:
    candidate: Individual
    unique: bool | None = None
    minimal: bool | None = None
    quick_rating: DifficultyResult | None = None
    deep_rating: DifficultyResult | None = None
    fitness: float = float("-inf")
    fitness_vector: tuple = ()
    status: str = "UNRATED"
    generation: int = 0
    operator: str = "seed"
    parent_keys: tuple = ()

    def __post_init__(self):
        if not isinstance(self.candidate, Individual):
            raise ValueError("candidate must be an immutable Individual")
        # Ratings are mutable legacy records: never retain a cache/parent alias.
        object.__setattr__(self, "quick_rating", deepcopy(self.quick_rating))
        object.__setattr__(self, "deep_rating", deepcopy(self.deep_rating))
        object.__setattr__(self, "fitness_vector", tuple(self.fitness_vector))
        object.__setattr__(self, "parent_keys", tuple(self.parent_keys))

    @property
    def solution(self):
        return self.candidate.solution

    @property
    def clue_mask(self):
        return self.candidate.clue_mask

    @property
    def clue_count(self):
        return self.candidate.clue_count

    @property
    def key(self):
        """Future symmetry normalization can replace this identity boundary."""
        return self.solution, self.clue_mask

    def to_puzzle(self):
        return self.candidate.to_puzzle()
