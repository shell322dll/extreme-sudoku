"""Disjoint ALS paths with explicit size, graph, and traversal exhaustion."""
from itertools import combinations
from time import perf_counter
from ..solver.models import Chain
from ..solver.techniques.als import (enumerate_als, restricted_common_candidates,
    endpoint_eliminations, RestrictedCommonCandidate)
from .models import EnumerationResult
from .enumeration import canonical_steps


def enumerate_als_steps(state, technique, config, deadline=float("inf")):
    result = EnumerationResult()
    reasons = set()
    # A full unit has at most 9 cells; an ALS at most 8. Checking all sizes is
    # finite and lets us distinguish an actual size omission from a harmless cap.
    all_nodes = enumerate_als(state, 8)
    nodes = tuple(a for a in all_nodes if len(a.cells) <= config.max_als_size)
    if len(nodes) != len(all_nodes):
        reasons.add("ALS_SIZE_LIMIT")
    adjacency = [[] for _ in nodes]

    def finish():
        result.steps = canonical_steps(result.steps)
        result.limit_reasons = sorted(reasons)
        result.complete = not reasons
        return result

    for a, b in combinations(range(len(nodes)), 2):
        if perf_counter() >= deadline:
            reasons.add("TIME_LIMIT")
            return finish()
        result.work += 1
        if result.work > config.max_als_search_nodes:
            reasons.add("ALS_NODE_LIMIT")
            return finish()
        for d in restricted_common_candidates(nodes[a], nodes[b]):
            adjacency[a].append((b, d))
            adjacency[b].append((a, d))
    natural_maximum = technique.maximum_sets
    maximum = min(natural_maximum or 81, config.max_als_chain_length)
    for start in range(len(nodes)):
        stack = [((start,), ())]
        while stack:
            if perf_counter() >= deadline:
                reasons.add("TIME_LIMIT")
                return finish()
            path, rccs = stack.pop()
            used = {c for i in path for c in nodes[i].cells}
            for nxt, digit in adjacency[path[-1]]:
                result.work += 1
                if result.work > config.max_als_search_nodes:
                    reasons.add("ALS_NODE_LIMIT")
                    return finish()
                if used.intersection(nodes[nxt].cells) or (rccs and rccs[-1] == digit):
                    continue
                extended, linked = path + (nxt,), rccs + (digit,)
                if len(extended) > maximum:
                    if natural_maximum is None or len(extended) <= natural_maximum:
                        reasons.add("ALS_CHAIN_LENGTH_LIMIT")
                    continue
                if len(extended) >= technique.minimum_sets and extended <= extended[::-1]:
                    sets = tuple(nodes[i] for i in extended)
                    effects = endpoint_eliminations(state, sets, linked)
                    if effects:
                        links = tuple(RestrictedCommonCandidate(a, b, d)
                                      for a, b, d in zip(sets, sets[1:], linked))
                        result.steps.append(technique.step(eliminations=effects, als=sets,
                            chain=Chain(sets, links),
                            premises=(tuple((a.cells, a.digits) for a in sets), linked),
                            explanation="Disjoint ALS chain with independently checkable RCCs."))
                if natural_maximum is None or len(extended) < natural_maximum:
                    stack.append((extended, linked))
    return finish()
