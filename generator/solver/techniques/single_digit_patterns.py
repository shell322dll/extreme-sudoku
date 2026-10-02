"""Bounded single-digit patterns; no general chain traversal or assumptions."""

from itertools import combinations, product

from .base import Technique, cell_name, unit_name, unique_steps
from .weights import TECHNIQUE_WEIGHTS
from ...sudoku.candidates import digit_mask
from ...sudoku.grid import ALL_UNITS, BOXES, ROWS, COLS, PEERS, box_of


def _links(state, bit):
    """Conjugate pairs, retaining their proving house."""
    result = []
    for index, unit in enumerate(ALL_UNITS):
        cells = tuple(c for c in unit if state.candidates[c] & bit)
        if len(cells) == 2:
            result.append((index, cells))
    return result


class _TwoLinks(Technique):
    def accepts(self, first_unit, second_unit, inner_a, inner_b, outer_a, outer_b):
        return True

    def find_steps(self, state):
        steps = []
        for digit in range(1, 10):
            bit = digit_mask(digit)
            for (first_unit, first), (second_unit, second) in combinations(_links(state, bit), 2):
                if len(set(first + second)) != 4:
                    continue
                for i, j in product(range(2), repeat=2):
                    inner_a, outer_a = first[i], first[1 - i]
                    inner_b, outer_b = second[j], second[1 - j]
                    if inner_b not in PEERS[inner_a]:
                        continue
                    if not self.accepts(first_unit, second_unit, inner_a, inner_b, outer_a, outer_b):
                        continue
                    excluded = set(first + second)
                    eliminations = [(c, digit) for c in PEERS[outer_a]
                                    if c in PEERS[outer_b] and c not in excluded and state.candidates[c] & bit]
                    if eliminations:
                        steps.append(self.step(
                            eliminations=eliminations,
                            premises=(digit, (first_unit, first), (second_unit, second),
                                      (inner_a, inner_b), (outer_a, outer_b)),
                            explanation=f"{self.name}: {digit} has exactly two positions in "
                                        f"{unit_name(first_unit)} and {unit_name(second_unit)}. "
                                        f"{cell_name(inner_a)} and {cell_name(inner_b)} see each other, "
                                        f"so {cell_name(outer_a)} or {cell_name(outer_b)} must contain {digit}. "
                                        "Remove it from cells seeing both outer endpoints.",
                        ))
        return unique_steps(steps)


class Skyscraper(_TwoLinks):
    name = "Skyscraper"
    difficulty = TECHNIQUE_WEIGHTS[name]

    def accepts(self, first_unit, second_unit, inner_a, inner_b, outer_a, outer_b):
        if first_unit < 9 and second_unit < 9:
            return inner_a % 9 == inner_b % 9 and outer_a % 9 != outer_b % 9
        if 9 <= first_unit < 18 and 9 <= second_unit < 18:
            return inner_a // 9 == inner_b // 9 and outer_a // 9 != outer_b // 9
        return False


class TwoStringKite(_TwoLinks):
    name = "2-String Kite"
    difficulty = TECHNIQUE_WEIGHTS[name]

    def accepts(self, first_unit, second_unit, inner_a, inner_b, outer_a, outer_b):
        return (first_unit < 9 and 9 <= second_unit < 18
                and box_of(inner_a) == box_of(inner_b))


class TurbotFish(_TwoLinks):
    """Exactly two disjoint conjugate pairs joined by one peer relation.

    Includes the named Skyscraper/Kite special cases and box conjugates. The
    fixed four-candidate proof does not explore variable-length chains.
    """

    name = "Turbot Fish"
    difficulty = TECHNIQUE_WEIGHTS[name]


class EmptyRectangle(Technique):
    """A box confined to two intersecting lines plus an external line pair.

    Both arms must be nonempty outside the intersection. The intersection may
    itself contain the digit. Two-candidate boxes are allowed (also Turbot).
    """

    name = "Empty Rectangle"
    difficulty = TECHNIQUE_WEIGHTS[name]

    def find_steps(self, state):
        steps = []
        for digit in range(1, 10):
            bit = digit_mask(digit)
            for box_index, box in enumerate(BOXES):
                positions = tuple(c for c in box if state.candidates[c] & bit)
                if len(positions) < 2:
                    continue
                for row in sorted({c // 9 for c in box}):
                    for col in sorted({c % 9 for c in box}):
                        if not all(c // 9 == row or c % 9 == col for c in positions):
                            continue
                        if not (any(c // 9 != row for c in positions)
                                and any(c % 9 != col for c in positions)):
                            continue
                        for orientation, line, perpendicular, coordinate in (
                                ("row", ROWS[row], COLS, lambda c: c % 9),
                                ("column", COLS[col], ROWS, lambda c: c // 9)):
                            for near in line:
                                if near in box or not state.candidates[near] & bit:
                                    continue
                                pair = tuple(c for c in perpendicular[coordinate(near)]
                                             if state.candidates[c] & bit)
                                if len(pair) != 2:
                                    continue
                                far = next(c for c in pair if c != near)
                                target = far // 9 * 9 + col if orientation == "row" else row * 9 + far % 9
                                if target in box or target in pair or not state.candidates[target] & bit:
                                    continue
                                steps.append(self.step(
                                    eliminations=((target, digit),),
                                    premises=(digit, box_index, positions, row, col, orientation, pair),
                                    explanation=f"Empty Rectangle: {digit} in box {box_index + 1} lies only "
                                                f"in row {row + 1} or column {col + 1}. If "
                                                f"{cell_name(target)} contained {digit}, it would exclude "
                                                f"one box arm and {cell_name(far)}, forcing {cell_name(near)} "
                                                "by its conjugate pair and excluding the other box arm. "
                                                "The box would have no position; remove that candidate.",
                                ))
        return unique_steps(steps)
