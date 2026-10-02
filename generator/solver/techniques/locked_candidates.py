"""Box/line intersections: pointing and claiming."""

from .base import Technique, unit_name, unique_steps
from .weights import TECHNIQUE_WEIGHTS
from ...sudoku.grid import ALL_UNITS
from ...sudoku.candidates import digit_mask


class LockedCandidates(Technique):
    name = "Locked Candidates"
    difficulty = TECHNIQUE_WEIGHTS[name]

    def find_steps(self, state):
        steps = []
        for source_index, source in enumerate(ALL_UNITS):
            targets = range(18) if source_index >= 18 else range(18, 27)
            for digit in range(1, 10):
                bit = digit_mask(digit)
                cells = tuple(c for c in source if state.candidates[c] & bit)
                if len(cells) < 2:
                    continue
                for target_index in targets:
                    target = ALL_UNITS[target_index]
                    if not all(c in target for c in cells):
                        continue
                    eliminations = tuple((c, digit) for c in target
                                         if c not in source and state.candidates[c] & bit)
                    if eliminations:
                        mode = "Pointing" if source_index >= 18 else "Claiming"
                        steps.append(self.step(
                            eliminations=eliminations,
                            premises=(mode, tuple(source), tuple(target), digit, cells),
                            explanation=f"{mode}: {digit} in {unit_name(source_index)} is confined to "
                                        f"{unit_name(target_index)}; remove it elsewhere in that unit.",
                        ))
        return unique_steps(steps)
