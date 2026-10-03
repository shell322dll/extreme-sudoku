"""Cheap, conservative duplicate and diversity checks for Phase 9 content.

All generated solution grids are isomorphic by construction (Latin pattern plus
permutations), so "same solution" is judged on the raw solution string. The
symmetry fingerprint is an invariant, not a canonical form: equal fingerprints
mean "possibly isomorphic" and are treated as near-duplicates (conservative).
"""
from itertools import permutations
from math import sqrt

from .models import Phase9Reason

MASK_NEAR_DISTANCE = 8          # popcount(maskA ^ maskB) <= 8 on the same solution
TECHNIQUE_SIMILARITY = 0.98     # cosine; warning only (with equal clue count)


def clue_mask(puzzle):
    return sum(1 << index for index, value in enumerate(puzzle) if value != "0")


def mask_distance(first, second):
    return (clue_mask(first) ^ clue_mask(second)).bit_count()


def is_mask_near(first, second, *, threshold=MASK_NEAR_DISTANCE):
    """Near clone: same solution string and clue masks differing in <= threshold cells."""
    return (first["solution"] == second["solution"]
            and mask_distance(first["puzzle"], second["puzzle"]) <= threshold)


def _box_matrix(puzzle):
    matrix = [[0] * 3 for _ in range(3)]
    for index, value in enumerate(puzzle):
        if value != "0":
            matrix[index // 27][index % 9 // 3] += 1
    return matrix


def symmetry_fingerprint(puzzle):
    """Invariant under band/stack/row/column permutations, transpose and relabelling."""
    counts = {}
    for value in puzzle:
        if value != "0":
            counts[value] = counts.get(value, 0) + 1
    digits = tuple(sorted(counts.values(), reverse=True))
    matrix = _box_matrix(puzzle)
    variants = []
    for grid in (matrix, [list(column) for column in zip(*matrix)]):
        for bands in permutations(range(3)):
            for stacks in permutations(range(3)):
                variants.append(tuple(grid[b][s] for b in bands for s in stacks))
    boxes = min(variants)
    rows = [sum(puzzle[r * 9 + c] != "0" for c in range(9)) for r in range(9)]
    cols = [sum(puzzle[r * 9 + c] != "0" for r in range(9)) for c in range(9)]
    row_shape = tuple(sorted(tuple(sorted(rows[b * 3:b * 3 + 3])) for b in range(3)))
    col_shape = tuple(sorted(tuple(sorted(cols[s * 3:s * 3 + 3])) for s in range(3)))
    lines = tuple(sorted((row_shape, col_shape)))
    text = "d" + ".".join(map(str, digits)) + "|b" + "".join(map(str, boxes)) + "|l" + ";".join(
        "/".join("".join(map(str, triple)) for triple in shape) for shape in lines)
    return text


def technique_similarity(first, second):
    """Cosine similarity of technique count vectors (0.0 when either is empty)."""
    names = set(first) | set(second)
    dot = sum(first.get(n, 0) * second.get(n, 0) for n in names)
    norm = sqrt(sum(v * v for v in first.values())) * sqrt(sum(v * v for v in second.values()))
    return dot / norm if norm else 0.0


class DiversityIndex:
    """Reference set (production records, archive selections, this run's picks)."""

    def __init__(self, *, mask_threshold=MASK_NEAR_DISTANCE, one_per_solution=True):
        self.mask_threshold = mask_threshold
        self.one_per_solution = one_per_solution
        self.by_puzzle, self.by_id, self.by_solution, self.by_fingerprint = {}, {}, {}, {}
        self.entries = []

    def add(self, entry, label=""):
        reference = {"id": entry["id"], "puzzle": entry["puzzle"], "solution": entry.get("solution"),
                     "label": label, "techniques": entry.get("techniques") or {},
                     "clues": entry.get("clues")}
        self.entries.append(reference)
        self.by_puzzle.setdefault(entry["puzzle"], reference)
        self.by_id.setdefault(entry["id"], reference)
        if reference["solution"]:
            self.by_solution.setdefault(reference["solution"], []).append(reference)
        self.by_fingerprint.setdefault(symmetry_fingerprint(entry["puzzle"]), []).append(reference)

    def exact_duplicate(self, entry):
        """(reason, detail) for an exact puzzle-string or ID collision, else None."""
        other = self.by_puzzle.get(entry["puzzle"])
        if other is not None:
            return Phase9Reason.DUPLICATE, f"exact puzzle string of {other['id']} ({other['label']})"
        other = self.by_id.get(entry["id"])
        if other is not None:
            # IDs are content hashes; a collision with a different string is an error.
            return Phase9Reason.DUPLICATE, f"ID collision with {other['label']} record (different puzzle)"
        return None

    def near_duplicate(self, entry):
        solution = entry.get("solution")
        for other in self.by_solution.get(solution, ()) if solution else ():
            distance = mask_distance(entry["puzzle"], other["puzzle"])
            if distance <= self.mask_threshold:
                return Phase9Reason.NEAR_DUPLICATE, (f"clue mask distance {distance} <= {self.mask_threshold} "
                                                     f"to {other['id']} ({other['label']}) on the same solution")
            if self.one_per_solution:
                return Phase9Reason.NEAR_DUPLICATE, (f"same solution as {other['id']} ({other['label']}); "
                                                     "policy: one puzzle per solution")
        fingerprint = symmetry_fingerprint(entry["puzzle"])
        for other in self.by_fingerprint.get(fingerprint, ()):
            return Phase9Reason.NEAR_DUPLICATE, (f"symmetry fingerprint equals {other['id']} ({other['label']}): "
                                                 "possible isomorph")
        return None

    def check(self, entry):
        return self.exact_duplicate(entry) or self.near_duplicate(entry)

    def technique_warnings(self, entry, *, threshold=TECHNIQUE_SIMILARITY):
        """Informational only: never a rejection."""
        warnings = []
        techniques = entry.get("techniques") or {}
        for other in self.entries:
            if other["id"] == entry["id"] or not other["techniques"] or other["clues"] != entry.get("clues"):
                continue
            similarity = technique_similarity(techniques, other["techniques"])
            if similarity >= threshold:
                warnings.append(f"technique profile cosine {similarity:.3f} with {other['id']} "
                                f"({other['label']}), same clue count")
        return warnings

    def nearest(self, entry):
        """(id, mask distance) of the closest same-solution reference, or (None, None)."""
        best = (None, None)
        for other in self.by_solution.get(entry.get("solution"), ()):
            distance = mask_distance(entry["puzzle"], other["puzzle"])
            if best[1] is None or distance < best[1]:
                best = (other["id"], distance)
        return best
