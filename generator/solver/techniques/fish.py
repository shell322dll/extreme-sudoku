"""Ordinary row/column fish, with disjoint base and cover houses."""

from itertools import combinations

from .base import Technique, unique_steps
from .weights import TECHNIQUE_WEIGHTS
from ...sudoku.candidates import digit_mask
from ...sudoku.grid import ROWS, COLS


class _Fish(Technique):
    size: int

    def find_steps(self, state):
        steps = []
        for digit in range(1, 10):
            bit = digit_mask(digit)
            for orientation, bases, covers in (("rows", ROWS, COLS), ("columns", COLS, ROWS)):
                positions = [tuple(i for i, c in enumerate(unit) if state.candidates[c] & bit)
                             for unit in bases]
                eligible = [i for i, cells in enumerate(positions) if 2 <= len(cells) <= self.size]
                for selected in combinations(eligible, self.size):
                    cover_ids = tuple(sorted(set().union(*(positions[i] for i in selected))))
                    if len(cover_ids) != self.size:
                        continue
                    base_cells = set().union(*(bases[i] for i in selected))
                    eliminations = [(c, digit) for i in cover_ids for c in covers[i]
                                    if c not in base_cells and state.candidates[c] & bit]
                    if eliminations:
                        pattern = tuple(c for i in selected for c in bases[i] if state.candidates[c] & bit)
                        steps.append(self.step(
                            eliminations=eliminations,
                            premises=(orientation, digit, selected, cover_ids, pattern),
                            explanation=f"{self.name}: digit {digit} in {orientation} "
                                        f"{tuple(i + 1 for i in selected)} is confined to "
                                        f"{self.size} perpendicular lines {tuple(i + 1 for i in cover_ids)}. "
                                        "Each base needs one occurrence, occupying every cover line; "
                                        "remove the digit from those lines outside the bases.",
                        ))
        return unique_steps(steps)


class XWing(_Fish):
    name = "X-Wing"
    difficulty = TECHNIQUE_WEIGHTS[name]
    size = 2


class Swordfish(_Fish):
    name = "Swordfish"
    difficulty = TECHNIQUE_WEIGHTS[name]
    size = 3


class Jellyfish(_Fish):
    name = "Jellyfish"
    difficulty = TECHNIQUE_WEIGHTS[name]
    size = 4
