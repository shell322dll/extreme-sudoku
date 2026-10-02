"""Bounded, candidate-only Almost Locked Set deductions.

An ALS has N mutually seeing cells and N+1 candidate digits. At most one
digit can be absent from it. A restricted common candidate (RCC) cannot be
present in both linked ALSs. Thus absence of an endpoint digit propagates
along a chain with distinct incoming/outgoing RCCs, forcing that digit at
the other end. Only disjoint ALSs are supported; overlap and double-linked
ALS-specific extra eliminations are intentionally outside this theorem.
"""

from dataclasses import dataclass
from itertools import combinations

from .base import Technique, cell_name, unique_steps
from .weights import TECHNIQUE_WEIGHTS
from ..advanced_config import AdvancedConfig
from ..models import Chain
from ...sudoku.candidates import digit_mask, mask_digits
from ...sudoku.grid import ALL_UNITS, PEERS, validate_cell


@dataclass(frozen=True, order=True)
class AlmostLockedSet:
    """Canonical cells with their original masks, sufficient for proof replay."""

    cells: tuple[int, ...]
    masks: tuple[int, ...]

    def __post_init__(self):
        cells, masks = tuple(self.cells), tuple(self.masks)
        if not cells or len(cells) != len(masks) or len(set(cells)) != len(cells):
            raise ValueError("ALS requires distinct cells with corresponding masks")
        for cell in cells:
            validate_cell(cell)
        for mask in masks:
            mask_digits(mask)
            if not mask:
                raise ValueError("ALS cells must have candidates")
        ordered = sorted(zip(cells, masks))
        object.__setattr__(self, "cells", tuple(c for c, _ in ordered))
        object.__setattr__(self, "masks", tuple(m for _, m in ordered))
        if not any(set(cells).issubset(unit) for unit in ALL_UNITS):
            raise ValueError("ALS cells must share a Sudoku unit")
        if self.candidate_mask.bit_count() != len(cells) + 1:
            raise ValueError("ALS requires exactly N+1 candidate digits for N cells")

    @property
    def candidate_mask(self):
        union = 0
        for mask in self.masks:
            union |= mask
        return union

    @property
    def digits(self):
        return mask_digits(self.candidate_mask)

    def occurrences(self, digit):
        bit = digit_mask(digit)
        return tuple(c for c, mask in zip(self.cells, self.masks) if mask & bit)


def enumerate_als(state, max_size=4):
    """All canonical ALSs up to the bound, independent of unit traversal order."""
    if type(max_size) is not int or not 1 <= max_size <= 8:
        raise ValueError("max_size must be an integer in 1..8")
    found = {}
    for unit in ALL_UNITS:
        cells = tuple(c for c in unit if not state.grid[c])
        for size in range(1, min(max_size, len(cells)) + 1):
            for subset in combinations(cells, size):
                masks = tuple(state.candidates[c] for c in subset)
                union = 0
                for mask in masks:
                    union |= mask
                if union.bit_count() == size + 1:
                    als = AlmostLockedSet(subset, masks)
                    found[als.cells] = als
    return tuple(sorted(found.values()))


def restricted_common_candidates(first, second):
    """Every occurrence on either side must see every occurrence on the other."""
    if set(first.cells) & set(second.cells):
        return ()
    return tuple(digit for digit in mask_digits(first.candidate_mask & second.candidate_mask)
                 if all(b in PEERS[a] for a in first.occurrences(digit)
                        for b in second.occurrences(digit)))


@dataclass(frozen=True, order=True)
class RestrictedCommonCandidate:
    first: AlmostLockedSet
    second: AlmostLockedSet
    digit: int


@dataclass(frozen=True)
class ALSGraph:
    nodes: tuple[AlmostLockedSet, ...]
    # Each adjacency entry is (neighbour index, RCC digit).
    adjacency: tuple[tuple[tuple[int, int], ...], ...]
    pair_checks: int
    truncated: bool

    @classmethod
    def build(cls, state, config=None):
        config = config or AdvancedConfig()
        nodes = enumerate_als(state, config.max_als_size)
        adjacency = [[] for _ in nodes]
        checks = 0
        truncated = False
        # Pair work is separately capped, so dense candidate states cannot
        # turn the graph construction itself into an unbounded quadratic scan.
        for first, second in combinations(range(len(nodes)), 2):
            if checks >= config.max_als_search_nodes:
                truncated = True
                break
            checks += 1
            for digit in restricted_common_candidates(nodes[first], nodes[second]):
                adjacency[first].append((second, digit))
                adjacency[second].append((first, digit))
        return cls(nodes, tuple(tuple(sorted(edges)) for edges in adjacency), checks, truncated)


def endpoint_eliminations(state, path, rccs):
    """Validate the entire chain before deriving its endpoint conclusion.

    This check also makes the public proof helper safe on hand-built paths.
    The terminal digit must differ from the first and last RCC; intermediate
    RCC reuse is allowed only when it is not consecutive.
    """
    if len(path) < 2 or len(rccs) != len(path) - 1:
        return ()
    used = set()
    for als in path:
        if used.intersection(als.cells):
            return ()
        if any(state.grid[c] or state.candidates[c] != mask
               for c, mask in zip(als.cells, als.masks)):
            return ()
        used.update(als.cells)
    if any(first == second for first, second in zip(rccs, rccs[1:])):
        return ()
    if any(digit not in restricted_common_candidates(first, second)
           for first, second, digit in zip(path, path[1:], rccs)):
        return ()
    common = path[0].candidate_mask & path[-1].candidate_mask
    common &= ~digit_mask(rccs[0]) & ~digit_mask(rccs[-1])
    eliminations = []
    for digit in mask_digits(common):
        supports = path[0].occurrences(digit) + path[-1].occurrences(digit)
        targets = set(PEERS[supports[0]])
        for cell in supports[1:]:
            targets.intersection_update(PEERS[cell])
        eliminations.extend((cell, digit) for cell in sorted(targets - used)
                            if state.candidates[cell] & digit_mask(digit))
    return tuple(sorted(eliminations))


class _ALSTechnique(Technique):
    minimum_sets = 2
    maximum_sets = 2

    def __init__(self, difficulty=None, *, config=None):
        super().__init__(difficulty)
        self.config = config or AdvancedConfig()

    def find_steps(self, state):
        maximum = min(self.maximum_sets or self.config.max_als_chain_length,
                      self.config.max_als_chain_length)
        if maximum < self.minimum_sets:
            return []
        graph = ALSGraph.build(state, self.config)
        steps = []
        searches = 0
        # Breadth first, canonical start/edge order: short explanations win.
        frontier = [((index,), ()) for index in range(len(graph.nodes))]
        for size in range(2, maximum + 1):
            next_frontier = []
            for indices, rccs in frontier:
                used = {c for index in indices for c in graph.nodes[index].cells}
                for neighbour, digit in graph.adjacency[indices[-1]]:
                    if searches >= self.config.max_als_search_nodes:
                        return unique_steps(steps)
                    searches += 1
                    if neighbour in indices or used.intersection(graph.nodes[neighbour].cells):
                        continue
                    if rccs and digit == rccs[-1]:
                        continue
                    extended = indices + (neighbour,)
                    linked = rccs + (digit,)
                    if size < maximum:
                        next_frontier.append((extended, linked))
                    # Reverse paths prove the same endpoints; retain one.
                    if size < self.minimum_sets or extended > extended[::-1]:
                        continue
                    path = tuple(graph.nodes[index] for index in extended)
                    eliminations = endpoint_eliminations(state, path, linked)
                    if not eliminations:
                        continue
                    links = tuple(RestrictedCommonCandidate(a, b, d)
                                  for a, b, d in zip(path, path[1:], linked))
                    description = " -> ".join(
                        "{" + ",".join(cell_name(c) for c in als.cells) + "}"
                        for als in path)
                    steps.append(self.step(
                        eliminations=eliminations,
                        premises=(tuple((als.cells, als.digits) for als in path), linked),
                        explanation=f"Disjoint ALS chain {description}, RCCs {linked}. "
                                    "If the first ALS lacks an endpoint digit, each RCC "
                                    "forces the next ALS to lack that RCC and contain all "
                                    "its other digits. Therefore at least one endpoint "
                                    "contains the eliminated digit; targets see every "
                                    "occurrence of that digit in both endpoints.",
                        chain=Chain(path, links), als=path,
                        search_complexity=graph.pair_checks + searches,
                    ))
            frontier = next_frontier
            if not frontier:
                break
        return unique_steps(steps)


class ALSXZ(_ALSTechnique):
    name = "ALS-XZ"
    difficulty = TECHNIQUE_WEIGHTS[name]


class ALSXYWing(_ALSTechnique):
    name = "ALS-XY-Wing"
    difficulty = TECHNIQUE_WEIGHTS[name]
    minimum_sets = 3
    maximum_sets = 3


class ALSChain(_ALSTechnique):
    name = "ALS Chain"
    difficulty = TECHNIQUE_WEIGHTS[name]
    minimum_sets = 4
    maximum_sets = None
