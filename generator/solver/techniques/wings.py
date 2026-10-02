"""Candidate-only XY-, XYZ- and W-Wing deductions."""

from itertools import combinations

from .base import Technique, cell_name, unit_name, unique_steps
from .weights import TECHNIQUE_WEIGHTS
from ...sudoku.candidates import digit_mask, mask_digits
from ...sudoku.grid import ALL_UNITS, PEERS


class XYWing(Technique):
    name = "XY-Wing"
    difficulty = TECHNIQUE_WEIGHTS[name]

    def find_steps(self, state):
        steps = []
        masks = state.candidates
        for pivot, pivot_mask in enumerate(masks):
            if pivot_mask.bit_count() != 2:
                continue
            wings = [c for c in PEERS[pivot] if masks[c].bit_count() == 2
                     and (masks[c] & pivot_mask).bit_count() == 1]
            for first, second in combinations(wings, 2):
                common = masks[first] & masks[second]
                if common.bit_count() != 1 or common & pivot_mask:
                    continue
                # Different pivot candidates must force the two wings.
                if (masks[first] | masks[second]) != (pivot_mask | common):
                    continue
                digit = mask_digits(common)[0]
                targets = set(PEERS[first]) & set(PEERS[second]) - {pivot}
                eliminations = [(c, digit) for c in sorted(targets) if masks[c] & common]
                if eliminations:
                    steps.append(self.step(
                        eliminations=eliminations,
                        premises=tuple((c, mask_digits(masks[c])) for c in (pivot, first, second)),
                        explanation=f"Pivot {cell_name(pivot)} has {mask_digits(pivot_mask)} and sees "
                                    f"{cell_name(first)} {mask_digits(masks[first])} and "
                                    f"{cell_name(second)} {mask_digits(masks[second])}. Either pivot "
                                    f"value forces one wing to {digit}; remove {digit} from cells "
                                    "seeing both wings.",
                    ))
        return unique_steps(steps)


class XYZWing(Technique):
    name = "XYZ-Wing"
    difficulty = TECHNIQUE_WEIGHTS[name]

    def find_steps(self, state):
        steps = []
        masks = state.candidates
        for pivot, pivot_mask in enumerate(masks):
            if pivot_mask.bit_count() != 3:
                continue
            wings = [c for c in PEERS[pivot] if masks[c].bit_count() == 2
                     and masks[c] & pivot_mask == masks[c]]
            for first, second in combinations(wings, 2):
                if masks[first] | masks[second] != pivot_mask:
                    continue
                common = masks[first] & masks[second]
                digit = mask_digits(common)[0]
                targets = set(PEERS[pivot]) & set(PEERS[first]) & set(PEERS[second])
                eliminations = [(c, digit) for c in sorted(targets) if masks[c] & common]
                if eliminations:
                    steps.append(self.step(
                        eliminations=eliminations,
                        premises=tuple((c, mask_digits(masks[c])) for c in (pivot, first, second)),
                        explanation=f"Pivot {cell_name(pivot)} has {mask_digits(pivot_mask)} and sees "
                                    f"{cell_name(first)} {mask_digits(masks[first])} and "
                                    f"{cell_name(second)} {mask_digits(masks[second])}. The pivot is "
                                    f"{digit}, or its other value forces a wing to {digit}; remove "
                                    f"{digit} only from cells seeing the pivot and both wings.",
                    ))
        return unique_steps(steps)


class WWing(Technique):
    name = "W-Wing"
    difficulty = TECHNIQUE_WEIGHTS[name]

    def find_steps(self, state):
        steps = []
        masks = state.candidates
        pairs = {}
        for cell, mask in enumerate(masks):
            if mask.bit_count() == 2:
                pairs.setdefault(mask, []).append(cell)
        # A bridge is a conjugate pair: exactly two supports in one unit.
        bridges = {digit: [] for digit in range(1, 10)}
        for index, unit in enumerate(ALL_UNITS):
            for digit in bridges:
                supports = tuple(c for c in unit if masks[c] & digit_mask(digit))
                if len(supports) == 2:
                    bridges[digit].append((index, supports))
        for mask, cells in sorted(pairs.items()):
            for first, second in combinations(cells, 2):
                if second in PEERS[first]:
                    continue
                targets = set(PEERS[first]) & set(PEERS[second])
                for linked_digit in mask_digits(mask):
                    other = mask & ~digit_mask(linked_digit)
                    digit = mask_digits(other)[0]
                    eliminations = [(c, digit) for c in sorted(targets) if masks[c] & other]
                    if not eliminations:
                        continue
                    for index, supports in bridges[linked_digit]:
                        if first in supports or second in supports:
                            continue
                        a, b = supports
                        if a in PEERS[first] and b in PEERS[second]:
                            pass
                        elif b in PEERS[first] and a in PEERS[second]:
                            a, b = b, a
                        else:
                            continue
                        steps.append(self.step(
                            eliminations=eliminations,
                            premises=((first, mask_digits(mask)), (second, mask_digits(mask)),
                                      (tuple(ALL_UNITS[index]), linked_digit, supports),
                                      ((first, a), (second, b))),
                            explanation=f"{cell_name(first)} and {cell_name(second)} both have "
                                        f"{mask_digits(mask)}. In {unit_name(index)}, {linked_digit} "
                                        f"occurs only at {cell_name(a)} and {cell_name(b)}, seen by "
                                        "the respective wings. Both wings cannot be "
                                        f"{linked_digit}, because that would remove both bridge "
                                        f"supports. At least one wing is {digit}; remove {digit} "
                                        "from cells seeing both wings.",
                        ))
        return unique_steps(steps)
