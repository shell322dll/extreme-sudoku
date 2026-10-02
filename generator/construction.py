"""Reusable immutable solution + clue-mask construction and uniqueness gates."""
from collections import OrderedDict
import random

from .chromosome import Individual
from .solver.exact_solver import count_solutions

FULL_MASK = (1 << 81) - 1


class UniquenessCache:
    """Bounded cache keyed by BOTH immutable solution and mask."""
    def __init__(self, size=512):
        if type(size) is not int or size < 0:
            raise ValueError("cache size must be a nonnegative integer")
        self.size = size
        self._cache = OrderedDict()

    def unique(self, candidate):
        key = (candidate.solution, candidate.clue_mask)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        result = validate_candidate(candidate)
        if self.size:
            self._cache[key] = result
            while len(self._cache) > self.size:
                self._cache.popitem(last=False)
        return result


def validate_candidate(candidate: Individual) -> bool:
    """Independent fresh exact check, never satisfied by a cache entry."""
    return count_solutions(candidate.to_puzzle(), limit=2) == 1


def remove_clues(candidate: Individual, target_clues: int, *, rng=None, cache=None, check=None):
    """Try each present clue once, stopping at the requested floor if reachable.

    A failed deletion never becomes removable after further deletions: its two
    solutions remain solutions of every weaker puzzle. One full pass suffices.
    """
    if type(target_clues) is not int or not 0 <= target_clues <= 81:
        raise ValueError("target_clues must be an integer from 0 to 81")
    rng = rng if rng is not None else random.Random()
    cache = cache if cache is not None else UniquenessCache()
    if not cache.unique(candidate):
        raise ValueError("clue removal requires a uniquely solvable candidate")
    positions = [cell for cell in range(81) if candidate.clue_mask & (1 << cell)]
    rng.shuffle(positions)
    for cell in positions:
        if check:
            check()
        if candidate.clue_count <= target_clues:
            break
        reduced = Individual(candidate.clue_mask & ~(1 << cell), candidate.solution)
        if cache.unique(reduced):
            candidate = reduced
    return candidate


def minimalize(candidate: Individual, *, rng=None, cache=None, check=None):
    """Remove all individually redundant clues; minimal is not minimum."""
    return remove_clues(candidate, 0, rng=rng, cache=cache, check=check)


def check_minimal(candidate: Individual, *, cache=None, check=None):
    cache = cache if cache is not None else UniquenessCache()
    if not cache.unique(candidate):
        return False
    for cell in range(81):
        if check:
            check()
        if candidate.clue_mask & (1 << cell):
            reduced = Individual(candidate.clue_mask & ~(1 << cell), candidate.solution)
            if cache.unique(reduced):
                return False
    return True
