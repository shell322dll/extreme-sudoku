"""Finite inference-graph searches, never a search through Sudoku solutions.

Strong (A or B): not A implies B. Weak (not A or not B): A implies not B.
A link may have both properties; neither is inferred merely from the other.
Grouped nodes are ORs of candidates in box/line intersections. Their weak
links require *every* pair to conflict and their strong links partition all
remaining supports of one unit digit. Search retains a shortest simple path
per (start, node, next-link-kind); this is bounded representative enumeration,
not enumeration of all possible proofs. A cutoff can miss moves, never add one.
"""

from collections import deque
from itertools import combinations

from .base import Technique, unique_steps
from .weights import TECHNIQUE_WEIGHTS
from ..advanced_config import AdvancedConfig
from ..models import CandidateNode, ChainLink, Chain
from ...sudoku.candidates import mask_digits
from ...sudoku.grid import ALL_UNITS, PEERS, BOXES, ROWS, COLS


def conflicts(a, b):
    if a == b:
        return False
    return all((x == y and a.digit != b.digit) or
               (x != y and a.digit == b.digit and y in PEERS[x])
               for x in a.cells for y in b.cells)


class InferenceGraph:
    def __init__(self, state, *, grouped=False, mode="aic"):
        self.state = state
        singles = {CandidateNode((c,), d) for c in range(81)
                   for d in mask_digits(state.candidates[c])}
        nodes = set(singles)
        supports = []
        for unit in ALL_UNITS:
            for d in range(1, 10):
                cells = tuple(c for c in unit if state.candidates[c] & (1 << (d - 1)))
                if len(cells) >= 2:
                    supports.append((unit, d, cells))
        if grouped:
            for box in BOXES:
                for line in ROWS + COLS:
                    intersection = set(box) & set(line)
                    if not intersection:
                        continue
                    for d in range(1, 10):
                        cells = tuple(sorted(c for c in intersection
                                             if state.candidates[c] & (1 << (d - 1))))
                        if len(cells) >= 2:
                            nodes.add(CandidateNode(cells, d))
        if mode == "xy":
            nodes = {n for n in nodes if state.candidates[n.cells[0]].bit_count() == 2}
        self.nodes = tuple(sorted(nodes))
        self.index = {n: i for i, n in enumerate(self.nodes)}
        self.strong = [dict() for _ in self.nodes]
        self.weak = [dict() for _ in self.nodes]

        def link(a, b, kind, reason):
            if a not in self.index or b not in self.index or a == b:
                return
            i, j = self.index[a], self.index[b]
            adjacency = self.strong if kind == "strong" else self.weak
            adjacency[i].setdefault(j, reason)
            adjacency[j].setdefault(i, reason)

        by_digit = {d: [n for n in self.nodes if n.digit == d] for d in range(1, 10)}
        for digit_nodes in by_digit.values():
            for a, b in combinations(digit_nodes, 2):
                if conflicts(a, b):
                    link(a, b, "weak", ("visibility",))
        if mode != "x":
            for cell in range(81):
                digits = mask_digits(state.candidates[cell])
                for d, e in combinations(digits, 2):
                    a, b = CandidateNode((cell,), d), CandidateNode((cell,), e)
                    if mode != "xy":
                        link(a, b, "weak", ("cell", cell))
                    if len(digits) == 2:
                        link(a, b, "strong", ("cell", cell))
        if mode != "xy":
            for unit, d, cells in supports:
                if len(cells) == 2:
                    link(CandidateNode((cells[0],), d), CandidateNode((cells[1],), d),
                         "strong", ("unit", ALL_UNITS.index(unit)))
                if grouped:
                    support = set(cells)
                    for a in by_digit[d]:
                        if set(a.cells) < support:
                            b = CandidateNode(tuple(sorted(support - set(a.cells))), d)
                            link(a, b, "strong", ("partition", ALL_UNITS.index(unit), cells))
        self.strong = tuple(tuple(sorted(adj.items())) for adj in self.strong)
        self.weak = tuple(tuple(sorted(adj.items())) for adj in self.weak)
        self.weak_sets = tuple(frozenset(j for j, _ in adj) for adj in self.weak)

    def has_link(self, a, b, kind):
        if a not in self.index or b not in self.index or kind not in ("strong", "weak"):
            return False
        adjacency = self.strong if kind == "strong" else self.weak
        return any(j == self.index[b] for j, _ in adjacency[self.index[a]])

    def valid_chain(self, chain):
        if len(chain.nodes) != len(chain.links) + 1 or not chain.links:
            return False
        nodes = chain.nodes[:-1] if chain.closed else chain.nodes
        if len(set(nodes)) != len(nodes):
            return False
        if chain.closed and chain.nodes[0] != chain.nodes[-1]:
            return False
        for i, link in enumerate(chain.links):
            if link.source != chain.nodes[i] or link.target != chain.nodes[i + 1]:
                return False
            if not self.has_link(link.source, link.target, link.kind):
                return False
            if i and chain.links[i - 1].kind == link.kind:
                return False
        return True


class _GraphTechnique(Technique):
    mode = "aic"
    grouped = False
    loops_only = False
    limit_name = "max_aic_length"

    def __init__(self, difficulty=None, *, config=None):
        super().__init__(difficulty)
        self.config = config or AdvancedConfig()

    def find_steps(self, state):
        graph = InferenceGraph(state, grouped=self.grouped, mode=self.mode)
        limit = getattr(self.config, self.limit_name)
        budget = self.config.max_chain_search_nodes
        examined = 0
        steps = []

        def emit(path, links, *, eliminations=(), placements=(), closed=False):
            if not eliminations and not placements:
                return
            nodes = tuple(graph.nodes[i] for i in path)
            groups = tuple(n for n in nodes if len(n.cells) > 1)
            if self.grouped and not groups:
                return
            steps.append(self.step(
                placements=placements, eliminations=eliminations,
                premises=(nodes[0], nodes[-1]), chain=Chain(nodes, links, closed),
                grouped_nodes=groups, search_complexity=examined,
                explanation=("A continuous alternating loop makes every weak link conjugate; "
                             "removed candidates conflict with both ends of such a link."
                             if closed and self.loops_only else
                             "An alternating loop has two strong links at its start, proving "
                             "that candidate true." if closed and placements else
                             "An alternating loop has two weak links at its start, proving "
                             "that candidate false." if closed else
                             "Alternating strong/weak implications prove at least "
                             "one endpoint true; each removed candidate conflicts with both."),
            ))

        for start in range(len(graph.nodes)):
            # X/XY chains use only strong-start, strong-end endpoint proofs.
            kinds = ("strong", "weak") if self.mode == "aic" and not self.loops_only else ("strong",)
            for first_kind in kinds:
                if first_kind == "strong" and not graph.strong[start]:
                    continue
                queue = deque([((start,), (), first_kind)])
                seen = {(start, first_kind)}
                while queue:
                    path, links, kind = queue.popleft()
                    adjacency = graph.strong if kind == "strong" else graph.weak
                    for nxt, reason in adjacency[path[-1]]:
                        examined += 1
                        if examined > budget:
                            return unique_steps(steps)
                        link = ChainLink(graph.nodes[path[-1]], graph.nodes[nxt], kind, reason)
                        new_links = links + (link,)
                        length = len(new_links)
                        if nxt == start:
                            # Only an odd alternating cycle has a discontinuity.
                            if (self.mode == "aic" and not self.loops_only and length >= 3
                                    and kind == first_kind and len(graph.nodes[start].cells) == 1):
                                target = (graph.nodes[start].cells[0], graph.nodes[start].digit)
                                emit(path + (nxt,), new_links, closed=True,
                                     placements=(target,) if kind == "strong" else (),
                                     eliminations=(target,) if kind == "weak" else ())
                            continue
                        if nxt in path:
                            continue
                        extended = path + (nxt,)
                        if first_kind == "strong" and kind == "strong" and length >= 3:
                            same_endpoint = graph.nodes[start].digit == graph.nodes[nxt].digit
                            if self.mode != "xy" or same_endpoint:
                                if not self.loops_only:
                                    targets = graph.weak_sets[start] & graph.weak_sets[nxt]
                                    targets = targets - set(extended)
                                    eliminations = tuple((graph.nodes[i].cells[0], graph.nodes[i].digit)
                                                         for i in sorted(targets)
                                                         if len(graph.nodes[i].cells) == 1)
                                    if self.mode == "xy":
                                        a, b = graph.nodes[start], graph.nodes[nxt]
                                        used_cells = {c for i in extended for c in graph.nodes[i].cells}
                                        eliminations = tuple((c, a.digit) for c in sorted(
                                            set(PEERS[a.cells[0]]) & set(PEERS[b.cells[0]]) - used_cells)
                                            if state.candidates[c] & (1 << (a.digit - 1)))
                                    emit(extended, new_links, eliminations=eliminations)
                                elif start in graph.weak_sets[nxt] and length + 1 <= limit:
                                    # A continuous alternating loop makes every weak edge
                                    # conjugate: its endpoints cannot both be false either.
                                    closing = ChainLink(graph.nodes[nxt], graph.nodes[start], "weak", ("closure",))
                                    cycle_links = new_links + (closing,)
                                    eliminations = set()
                                    for edge in cycle_links:
                                        if edge.kind == "weak":
                                            a, b = graph.index[edge.source], graph.index[edge.target]
                                            for target in graph.weak_sets[a] & graph.weak_sets[b] - set(extended):
                                                n = graph.nodes[target]
                                                if len(n.cells) == 1:
                                                    eliminations.add((n.cells[0], n.digit))
                                    emit(extended + (start,), cycle_links,
                                         eliminations=tuple(sorted(eliminations)), closed=True)
                        next_kind = "weak" if kind == "strong" else "strong"
                        key = (nxt, next_kind)
                        if length < limit and key not in seen:
                            seen.add(key)
                            queue.append((extended, new_links, next_kind))
        return unique_steps(steps)


class XChain(_GraphTechnique):
    name = "X-Chain"
    difficulty = TECHNIQUE_WEIGHTS[name]
    mode, limit_name = "x", "max_x_chain_length"


class XYChain(_GraphTechnique):
    name = "XY-Chain"
    difficulty = TECHNIQUE_WEIGHTS[name]
    mode, limit_name = "xy", "max_xy_chain_length"


class AIC(_GraphTechnique):
    name = "AIC"
    difficulty = TECHNIQUE_WEIGHTS[name]


class NiceLoop(_GraphTechnique):
    name = "Nice Loop"
    difficulty = TECHNIQUE_WEIGHTS[name]
    loops_only = True


class GroupedAIC(_GraphTechnique):
    name = "Grouped AIC"
    difficulty = TECHNIQUE_WEIGHTS[name]
    grouped, limit_name = True, "max_grouped_aic_length"
