"""Naked and hidden pairs/triples/quads in every row, column and box."""

from itertools import combinations

from .base import Technique, cell_name, unit_name, unique_steps
from .weights import TECHNIQUE_WEIGHTS
from ...sudoku.grid import ALL_UNITS
from ...sudoku.candidates import digit_mask, mask_digits


class _NakedSubset(Technique):
    size: int

    def find_steps(self, state):
        steps = []
        for index, unit in enumerate(ALL_UNITS):
            eligible = [c for c in unit if 2 <= state.candidates[c].bit_count() <= self.size]
            for cells in combinations(eligible, self.size):
                mask = 0
                for cell in cells:
                    mask |= state.candidates[cell]
                if mask.bit_count() != self.size:
                    continue
                eliminations = tuple((c, digit) for c in unit if c not in cells
                                     for digit in mask_digits(state.candidates[c] & mask))
                if eliminations:
                    digits = mask_digits(mask)
                    steps.append(self.step(
                        eliminations=eliminations,
                        premises=(tuple(unit), tuple((c, mask_digits(state.candidates[c])) for c in cells)),
                        explanation=f"{', '.join(map(cell_name, cells))} contain only {digits} in "
                                    f"{unit_name(index)}; remove those digits from the other cells.",
                    ))
        return unique_steps(steps)


class _HiddenSubset(Technique):
    size: int

    def find_steps(self, state):
        steps = []
        for index, unit in enumerate(ALL_UNITS):
            supports = {d: tuple(c for c in unit if state.candidates[c] & digit_mask(d))
                        for d in range(1, 10)}
            eligible = [d for d, cells in supports.items() if 1 <= len(cells) <= self.size]
            for digits in combinations(eligible, self.size):
                cells = tuple(sorted({c for d in digits for c in supports[d]}))
                if len(cells) != self.size:
                    continue
                mask = sum(digit_mask(d) for d in digits)
                eliminations = tuple((c, d) for c in cells
                                     for d in mask_digits(state.candidates[c] & ~mask))
                if eliminations:
                    steps.append(self.step(
                        eliminations=eliminations,
                        premises=(tuple(unit), tuple((d, supports[d]) for d in digits)),
                        explanation=f"{digits} occur only in {', '.join(map(cell_name, cells))} in "
                                    f"{unit_name(index)}; remove the other candidates from those cells.",
                    ))
        return unique_steps(steps)


class NakedPair(_NakedSubset):
    name, size = "Naked Pair", 2
    difficulty = TECHNIQUE_WEIGHTS[name]


class HiddenPair(_HiddenSubset):
    name, size = "Hidden Pair", 2
    difficulty = TECHNIQUE_WEIGHTS[name]


class NakedTriple(_NakedSubset):
    name, size = "Naked Triple", 3
    difficulty = TECHNIQUE_WEIGHTS[name]


class HiddenTriple(_HiddenSubset):
    name, size = "Hidden Triple", 3
    difficulty = TECHNIQUE_WEIGHTS[name]


class NakedQuad(_NakedSubset):
    name, size = "Naked Quad", 4
    difficulty = TECHNIQUE_WEIGHTS[name]


class HiddenQuad(_HiddenSubset):
    name, size = "Hidden Quad", 4
    difficulty = TECHNIQUE_WEIGHTS[name]
