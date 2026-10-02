"""Full houses and naked/hidden singles."""

from .base import Technique, cell_name, unit_name, unique_steps
from .weights import TECHNIQUE_WEIGHTS
from ...sudoku.grid import ALL_UNITS
from ...sudoku.candidates import digit_mask, mask_digits


class FullHouse(Technique):
    name = "Full House"
    difficulty = TECHNIQUE_WEIGHTS[name]

    def find_steps(self, state):
        steps = []
        for index, unit in enumerate(ALL_UNITS):
            empty = [cell for cell in unit if not state.grid[cell]]
            if len(empty) == 1:
                cell = empty[0]
                digit = next(iter(set(range(1, 10)) - {state.grid[c] for c in unit}))
                if state.candidates[cell] & digit_mask(digit):
                    steps.append(self.step(
                        placements=((cell, digit),), premises=(tuple(unit),),
                        explanation=f"{unit_name(index)} has one empty cell: {cell_name(cell)} = {digit}.",
                    ))
        return unique_steps(steps)


class NakedSingle(Technique):
    name = "Naked Single"
    difficulty = TECHNIQUE_WEIGHTS[name]

    def find_steps(self, state):
        return [self.step(
            placements=((cell, mask.bit_length()),), premises=((cell, mask_digits(mask)),),
            explanation=f"{cell_name(cell)} has only candidate {mask.bit_length()}.",
        ) for cell, mask in enumerate(state.candidates) if mask.bit_count() == 1]


class HiddenSingle(Technique):
    name = "Hidden Single"
    difficulty = TECHNIQUE_WEIGHTS[name]

    def find_steps(self, state):
        steps = []
        for index, unit in enumerate(ALL_UNITS):
            for digit in range(1, 10):
                cells = [c for c in unit if state.candidates[c] & digit_mask(digit)]
                if len(cells) == 1:
                    cell = cells[0]
                    steps.append(self.step(
                        placements=((cell, digit),), premises=(tuple(unit), (digit, tuple(cells))),
                        explanation=f"Only {cell_name(cell)} can hold {digit} in {unit_name(index)}.",
                    ))
        return unique_steps(steps)
