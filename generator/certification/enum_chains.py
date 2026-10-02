"""Exhaustive simple inference paths; no representative-node pruning.

Phase 7.1 (performance only): the traversal visits exactly the same edges in the
same order with the same work counter and limit reasons as before. Chain link
objects are built only for emitted steps (the stack carries node indices and
link reasons; link kinds alternate from the first kind), and an inference graph
may be shared between techniques with the same (grouped, mode) on one state.
"""
from time import perf_counter
from ..solver.models import Chain, ChainLink
from ..solver.techniques.chains import InferenceGraph
from ..sudoku.grid import PEERS
from .models import EnumerationResult
from .enumeration import canonical_steps

_OTHER = {"strong": "weak", "weak": "strong"}


def enumerate_chains(state, technique, config, deadline=float("inf"), *, graph=None):
    if graph is None:
        graph = InferenceGraph(state, grouped=technique.grouped, mode=technique.mode)
    result = EnumerationResult()
    reasons = set()
    nodes, weak_sets = graph.nodes, graph.weak_sets
    grouped, mode, loops_only = technique.grouped, technique.mode, technique.loops_only
    max_length, max_work = config.max_chain_length, config.max_chain_search_nodes
    work = 0

    def finish():
        result.work = work
        result.steps = canonical_steps(result.steps)
        result.limit_reasons = sorted(reasons)
        result.complete = not reasons
        return result

    def emit(indices, link_reasons, first_kind, *, closed=False, placements=(), eliminations=()):
        if not placements and not eliminations:
            return
        chain_nodes = tuple(nodes[i] for i in indices)
        groups = tuple(n for n in chain_nodes if len(n.cells) > 1)
        if grouped and not groups:
            return
        links, kind = [], first_kind
        for i, reason in enumerate(link_reasons):
            links.append(ChainLink(chain_nodes[i], chain_nodes[i + 1], kind, reason))
            kind = _OTHER[kind]
        result.steps.append(technique.step(placements=placements, eliminations=eliminations,
            premises=(chain_nodes[0], chain_nodes[-1]), chain=Chain(chain_nodes, tuple(links), closed),
            grouped_nodes=groups, explanation="Exhaustively enumerated alternating implication proof."))

    open_aic = mode == "aic" and not loops_only
    for start in range(len(nodes)):
        kinds = ("strong", "weak") if open_aic else ("strong",)
        start_single = len(nodes[start].cells) == 1
        for first_kind in kinds:
            stack = [((start,), (), first_kind)]
            while stack:
                if perf_counter() >= deadline:
                    reasons.add("TIME_LIMIT")
                    return finish()
                path, link_reasons, kind = stack.pop()
                adjacent = graph.strong if kind == "strong" else graph.weak
                last = path[-1]
                length = len(link_reasons) + 1
                next_kind = _OTHER[kind]
                for nxt, reason in adjacent[last]:
                    work += 1
                    if work > max_work:
                        reasons.add("CHAIN_NODE_LIMIT")
                        return finish()
                    if nxt in path and nxt != start:
                        continue
                    if length > max_length:
                        reasons.add("CHAIN_LENGTH_LIMIT")
                        continue
                    new_reasons = link_reasons + (reason,)
                    if nxt == start:
                        if open_aic and length >= 3 and first_kind == kind and start_single:
                            target = (nodes[start].cells[0], nodes[start].digit)
                            emit(path + (start,), new_reasons, first_kind, closed=True,
                                 placements=(target,) if kind == "strong" else (),
                                 eliminations=(target,) if kind == "weak" else ())
                        continue
                    extended = path + (nxt,)
                    if first_kind == kind == "strong" and length >= 3:
                        a, b = nodes[start], nodes[nxt]
                        if mode != "xy" or a.digit == b.digit:
                            if not loops_only:
                                targets = (weak_sets[start] & weak_sets[nxt]) - set(extended)
                                elimination = tuple((nodes[i].cells[0], nodes[i].digit)
                                    for i in sorted(targets) if len(nodes[i].cells) == 1)
                                if mode == "xy":
                                    used = {c for i in extended for c in nodes[i].cells}
                                    elimination = tuple((c, a.digit) for c in sorted(
                                        set(PEERS[a.cells[0]]) & set(PEERS[b.cells[0]]) - used)
                                        if state.candidates[c] & (1 << (a.digit - 1)))
                                emit(extended, new_reasons, first_kind, eliminations=elimination)
                            elif start in weak_sets[nxt]:
                                if length + 1 > max_length:
                                    reasons.add("CHAIN_LENGTH_LIMIT")
                                else:
                                    # Cycle links: path links alternate from strong,
                                    # then the weak closure nxt -> start.
                                    cycle = extended + (start,)
                                    members = set(extended)
                                    effects = set()
                                    edge_kind = first_kind
                                    for i in range(len(cycle) - 1):
                                        if edge_kind == "weak":
                                            x, y = cycle[i], cycle[i + 1]
                                            for j in (weak_sets[x] & weak_sets[y]) - members:
                                                n = nodes[j]
                                                if len(n.cells) == 1:
                                                    effects.add((n.cells[0], n.digit))
                                        edge_kind = _OTHER[edge_kind]
                                    emit(cycle, new_reasons + (("closure",),), first_kind, closed=True,
                                         eliminations=tuple(sorted(effects)))
                    stack.append((extended, new_reasons, next_kind))
    return finish()
