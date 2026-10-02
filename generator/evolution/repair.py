"""Target-relative alternative solutions produce reusable conflict sets."""
from collections import OrderedDict
from dataclasses import dataclass

from ..chromosome import Individual
from ..solver.exact_solver import collect_solutions
from .operators import guided_cells


class ConflictStore:
    """Bounded solution-scoped witness sets; no cross-solution reuse."""
    def __init__(self, max_solutions=128, max_sets_per_solution=1024):
        if any(type(n) is not int or n < 1 for n in (max_solutions, max_sets_per_solution)):
            raise ValueError("conflict cache limits must be positive integers")
        self.max_solutions = max_solutions
        self.max_sets_per_solution = max_sets_per_solution
        self._sets = OrderedDict()

    def add(self, target, alternative):
        """Store only a witnessed difference against this complete target."""
        target = tuple(target)
        alternative = tuple(alternative)
        # Validation prevents callers poisoning reusable unavoidable sets.
        Individual(0, target)
        Individual(0, alternative)
        difference = sum(1 << i for i in range(81) if target[i] != alternative[i])
        if not difference:
            return 0
        sets = self._sets.setdefault(target, OrderedDict())
        sets[difference] = None
        sets.move_to_end(difference)
        self._sets.move_to_end(target)
        while len(sets) > self.max_sets_per_solution:
            sets.popitem(last=False)
        while len(self._sets) > self.max_solutions:
            self._sets.popitem(last=False)
        return difference

    def for_solution(self, solution):
        return tuple(self._sets.get(tuple(solution), ()))

    def unresolved(self, candidate):
        return tuple(mask for mask in self.for_solution(candidate.solution)
                     if not mask & candidate.clue_mask)


@dataclass(frozen=True)
class RepairResult:
    candidate: Individual
    unique: bool
    added_cells: tuple[int, ...]
    conflict_sets: tuple[int, ...]
    checks: int
    # One witness set per added cell makes the repair decision auditable.
    addition_conflicts: tuple[int, ...] = ()


def repair_uniqueness(candidate, *, rng, limit=5, strategy="coverage", conflicts=None,
                      rating=None, check=None):
    """Add at most ``limit`` target clues, each hitting an actual conflict.

    Cached unhit sets are still exact witnesses: all surviving clues coincide
    with their alternative solution. A final exact call confirms uniqueness;
    hitting every discovered set alone is never considered sufficient.
    """
    if type(limit) is not int or limit < 0:
        raise ValueError("repair limit must be a nonnegative integer")
    if strategy not in ("random", "coverage", "guided"):
        raise ValueError("unknown repair strategy")
    conflicts = conflicts if conflicts is not None else ConflictStore()
    added, evidence, discovered = [], [], []
    checks = 0
    influence = set(guided_cells(rating)) if strategy == "guided" else set()
    while True:
        if check:
            check()
        unresolved = conflicts.unresolved(candidate)
        if not unresolved or len(added) >= limit:
            alternatives = collect_solutions(candidate.to_puzzle(), limit=2)
            checks += 1
            if len(alternatives) == 1:
                return RepairResult(candidate, True, tuple(added), tuple(dict.fromkeys(discovered)),
                                    checks, tuple(evidence))
            if not alternatives:
                return RepairResult(candidate, False, tuple(added), tuple(dict.fromkeys(discovered)),
                                    checks, tuple(evidence))
            for alternative in alternatives:
                difference = conflicts.add(candidate.solution, alternative)
                if difference:
                    discovered.append(difference)
            unresolved = conflicts.unresolved(candidate)
        if len(added) >= limit or not unresolved:
            return RepairResult(candidate, False, tuple(added), tuple(dict.fromkeys(discovered)),
                                checks, tuple(evidence))
        discovered.extend(unresolved)
        union = 0
        for mask in unresolved:
            union |= mask
        cells = [cell for cell in range(81) if union & (1 << cell)]
        if strategy == "random":
            cell = rng.choice(cells)
        else:
            # Coverage greedily approximates minimum added clues. Guided ties
            # avoid bottleneck influence when possible, preserving difficulty.
            def priority(cell):
                return (sum(bool(mask & (1 << cell)) for mask in unresolved),
                        int(cell not in influence) if strategy == "guided" else 0)
            best = max(map(priority, cells))
            cell = rng.choice([cell for cell in cells if priority(cell) == best])
        witness = next(mask for mask in unresolved if mask & (1 << cell))
        evidence.append(witness)
        added.append(cell)
        candidate = Individual(candidate.clue_mask | (1 << cell), candidate.solution)
