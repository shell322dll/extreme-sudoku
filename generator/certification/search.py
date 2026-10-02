"""Search logical transitions only. There is no exact/solution-grid dependency.

The search runs over an abstract transition provider (``transitions.py``); the
production provider is ``SudokuTransitions``. Phase 7.1 changes are performance
only; every operational limit still yields INCONCLUSIVE_BUDGET and
PROVEN_UNSOLVABLE_WITHIN_MODEL requires either exhausting the whole reachable
graph with no limit reason, or (``use_stuck_state_lemma``) an independently
checked Stuck-State Superset Lemma certificate at the root (``stuck_state.py``).
"""
from dataclasses import dataclass, field, replace
from heapq import heappop, heappush
from itertools import count
from time import perf_counter

from .enumeration import StepEnumerator, effect_key, representative  # noqa: F401 (public re-export)
from .models import SearchStatus, ThresholdResult
from .transitions import SudokuTransitions, apply_step  # noqa: F401 (patchable hook)
from .stuck_state import EXHAUSTIVE_PROOF_KIND, PROOF_KIND, confluence_violation
from ..solver.techniques.base import step_key


def _transition_order(item):
    step = item[0]
    # Placements first, then larger elimination sets, then cheaper ratings and a
    # deterministic canonical key. Ordering affects only scheduling.
    return (-len(step.placements), -len(step.eliminations), step.rating, step_key(step))


def select_transitions(provider, state, steps, telemetry=None):
    """Distinct successor states, each with its cheapest canonical proof.

    Steps reaching an identical successor (equal effects, or e.g. a Hidden and a
    Naked Single for one placement) are interchangeable for every objective
    except their own rating, so only the minimum (rating, step_key, JSON proof)
    representative is kept; the choice is independent of input order.
    A step that cannot be applied is validated so the error names the proof.
    """
    groups, children = {}, {}
    for step in steps:
        child = provider.child(state, step)
        if child is None:
            proof = provider.validate(state, step)
            if not proof.valid:
                raise ValueError("Invalid logic proof: " + "; ".join(proof.errors))
            child = provider.apply_checked(state, step)  # raises the apply error
        key = provider.signature(child)
        if key in groups:
            groups[key].append(step)
        else:
            groups[key], children[key] = [step], child
    chosen = []
    for key, group in groups.items():
        step = representative(group)
        chosen.append((step, children[key], key))
        if telemetry is not None and len(group) > 1:
            removed = telemetry.setdefault("duplicates_removed_by_family", {})
            for other in group:
                if other is not step:
                    removed[other.technique] = removed.get(other.technique, 0) + 1
    chosen.sort(key=_transition_order)
    if telemetry is not None:
        telemetry["raw_steps"] = telemetry.get("raw_steps", 0) + len(steps)
        telemetry["unique_effects"] = telemetry.get("unique_effects", 0) + len({effect_key(s) for s in steps})
        telemetry["unique_children"] = telemetry.get("unique_children", 0) + len(chosen)
        telemetry["duplicate_children_removed"] = (telemetry.get("duplicate_children_removed", 0)
                                                   + len(steps) - len(chosen))
        telemetry["max_branching"] = max(telemetry.get("max_branching", 0), len(chosen))
    return chosen


def _path(node):
    steps = []
    while node is not None:
        step, node = node
        steps.append(step)
    return steps[::-1]


def threshold_search(state_or_grid, threshold, config, *, deadline=None, enumerator=None,
                     provider=None, max_records=None):
    """Find a witness or exhaust ALL reachable transitions at or below a rating ceiling.

    More advanced states are visited first, but all alternative states remain in
    the frontier. Only equal signatures merge.

    Within one fixed ceiling the verdict (SOLVED vs PROVEN) depends only on
    reachability, not on the max rating so far (the descent lowers the ceiling
    itself), so a signature is expanded at most once (plain visited semantics).
    The only exception: when the depth limit can bind, a strictly shallower
    arrival re-opens a state (it leaves more remaining depth budget). When every
    path from the root is provably shorter than ``max_path_depth`` (Sudoku: each
    step removes >=1 live candidate), depth can never cut a branch and visited
    semantics is exact. Secondary costs (extreme-step count, score) only order
    the frontier deterministically; they are not certified.

    Transposition lookup happens before proof validation; every step that
    creates or improves a frontier entry, hence every witness edge, is validated.
    Any limit reason clears ``negative_proof_possible``: the search then can only
    return SOLVED or INCONCLUSIVE_BUDGET.
    """
    started = perf_counter()
    deadline = min(deadline if deadline is not None else float("inf"), started + config.time_budget)
    provider = provider or SudokuTransitions(config, enumerator)
    result = ThresholdResult(threshold, SearchStatus.INCONCLUSIVE_BUDGET)
    telemetry = {"transposition_lookups": 0, "transposition_hits": 0, "stale_pops": 0,
                 "repushes": 0, "depth_reopens": 0, "expansions": 0,
                 "peak_frontier": 1, "limit_reason_first_expansion": {}, "enumeration_seconds": 0.0,
                 "validation_calls": 0, "negative_certificates": 0}
    result.telemetry = telemetry
    enumerator_ref = getattr(provider, "enumerator", None)
    family_before = dict(getattr(enumerator_ref, "family_seconds", {}) or {})
    root = provider.initial(state_or_grid)
    root_key = provider.signature(root)
    bound = provider.depth_bound(root)
    depth_matters = bound is None or bound >= config.max_path_depth
    telemetry["depth_rule"] = "shallower-reopen" if depth_matters else "visited"
    # signature -> [best depth, serial of the entry holding it]
    records = {root_key: [0, 0]}
    expanded = {}                              # signature -> smallest depth already expanded
    frontier, serial = [], count()
    heappush(frontier, (provider.progress(root), 0, 0, next(serial), (root, root_key, None, 0, 0.0, 0, 0.0)))
    # An entry is live while it holds the best depth of its signature; a superseded
    # entry, or one not shallower than an earlier expansion, is a stale transposition.
    reasons = set()
    result.states_generated = 1
    hook = getattr(provider, "negative_certificate", None)
    if not getattr(config, "use_stuck_state_lemma", False):
        hook = None

    def finish(status):
        result.status = status
        result.limit_reasons = sorted(reasons)
        result.negative_proof_possible = not reasons
        result.elapsed_seconds = perf_counter() - started
        lookups = telemetry["transposition_lookups"]
        telemetry["transposition_hit_rate"] = telemetry["transposition_hits"] / lookups if lookups else 0.0
        telemetry["unique_states"] = len(records)
        expansions = telemetry["expansions"]
        telemetry["mean_branching"] = telemetry.get("unique_children", 0) / expansions if expansions else 0.0
        after = getattr(enumerator_ref, "family_seconds", {}) or {}
        telemetry["family_enumeration_seconds"] = {
            k: v - family_before.get(k, 0.0) for k, v in sorted(after.items()) if v - family_before.get(k, 0.0) > 0}
        stats = getattr(provider, "cache_stats", None)
        if stats:
            telemetry["caches"] = stats()
        return result

    def note(new_reasons):
        for reason in sorted(new_reasons):
            if reason not in reasons:
                telemetry["limit_reason_first_expansion"][reason] = result.states_explored
                reasons.add(reason)

    if hook is not None:
        # Stuck-State Superset Lemma at the root (doc PHASE7_1_STUCK_STATE_PROOFS).
        # Accepted certificate => proven; solved closure => validated witness;
        # anything else (guard failure, timeout) => unchanged exhaustive search.
        certificate = hook(root, threshold, deadline)
        if certificate is not None:
            accepted = (certificate.outcome == "STUCK"
                        and provider.check_negative_certificate(root, threshold, certificate, deadline))
            telemetry["stuck_state_lemma"] = certificate.telemetry()
            if certificate.outcome == "ERROR":
                result.error = certificate.error or "Stuck-state certificate error"
                return finish(SearchStatus.ERROR)
            if certificate.outcome == "SOLVED":
                # Same semantics as a search witness (review P2-5): the closure is a
                # chain of len(path) expansions, so it must fit max_path_depth and the
                # node budget, and those expansions are counted as states explored.
                checker = getattr(provider, "validate_witness", None)
                length = len(certificate.path)
                if (length <= config.max_path_depth and length <= config.node_budget
                        and perf_counter() < deadline and (checker is None or checker(root, certificate.path))):
                    result.path = list(certificate.path)
                    result.states_explored = length
                    result.states_generated = length + 1
                    telemetry["expansions"] = length
                    telemetry["stuck_state_lemma"]["outcome"] = "SOLVED"
                    return finish(SearchStatus.SOLVED)
                telemetry["stuck_state_lemma"]["outcome"] = "FALLBACK"
            elif accepted and perf_counter() < deadline:
                telemetry["negative_certificates"] += 1
                result.negative_proof_kind = PROOF_KIND
                result.negative_certificate = certificate.evidence()
                return finish(SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)
            elif accepted:
                telemetry["stuck_state_lemma"]["outcome"] = "TIMEOUT"

    while frontier:
        if perf_counter() >= deadline:
            note({"TIME_LIMIT"})
            return finish(SearchStatus.INCONCLUSIVE_BUDGET)
        _, _, _, entry, (current, key, node, extreme_count, score, depth, max_rating) = heappop(frontier)
        effective = depth if depth_matters else 0
        done = expanded.get(key)
        if entry != records[key][1] or (done is not None and done <= effective):
            result.cache_hits += 1
            telemetry["stale_pops"] += 1
            continue
        if provider.is_solved(current):
            if perf_counter() >= deadline:
                note({"TIME_LIMIT"})
                return finish(SearchStatus.INCONCLUSIVE_BUDGET)
            result.path = _path(node)
            return finish(SearchStatus.SOLVED)
        if result.states_explored >= config.node_budget:
            note({"NODE_LIMIT"})
            return finish(SearchStatus.INCONCLUSIVE_BUDGET)
        result.states_explored += 1
        telemetry["expansions"] += 1
        expanded[key] = effective if done is None else min(done, effective)
        if depth >= config.max_path_depth:
            note({"PATH_DEPTH_LIMIT"})
            continue
        try:
            enumeration_started = perf_counter()
            available = provider.enumerate(current, threshold, deadline)
            telemetry["enumeration_seconds"] += perf_counter() - enumeration_started
            new_reasons = set(available.limit_reasons)
            if not available.complete and not available.limit_reasons:
                new_reasons.add("INCOMPLETE_ENUMERATION")
            note(new_reasons)
            for step in available.steps:
                if step.rating > threshold:
                    raise ValueError("Enumerator returned a step above its threshold")
            transitions = select_transitions(provider, current, available.steps, telemetry)
            for step, child, child_key in transitions:
                if perf_counter() >= deadline:
                    note({"TIME_LIMIT"})
                    return finish(SearchStatus.INCONCLUSIVE_BUDGET)
                child_depth = depth + 1
                child_effective = child_depth if depth_matters else 0
                child_max = max(max_rating, step.rating)
                telemetry["transposition_lookups"] += 1
                known = records.get(child_key)
                if known is not None:
                    if not child_effective < known[0]:
                        result.cache_hits += 1
                        telemetry["transposition_hits"] += 1
                        continue
                elif len(records) >= config.state_budget:
                    note({"STATE_LIMIT"})
                    continue
                elif max_records is not None and len(records) >= max_records:
                    note({"MEMORY_LIMIT"})
                    continue
                proof_started = perf_counter()
                telemetry["validation_calls"] += 1
                proof = provider.validate(current, step, key)
                result.proof_seconds += perf_counter() - proof_started
                if not proof.valid:
                    raise ValueError("Invalid logic proof: " + "; ".join(proof.errors))
                child_serial = next(serial)
                if known is None:
                    records[child_key] = [child_effective, child_serial]
                    result.states_generated += 1
                else:
                    known[0], known[1] = child_effective, child_serial
                    telemetry["repushes"] += 1
                    telemetry["depth_reopens"] += 1
                new_score = score + step.rating ** 2
                new_extreme = extreme_count + int(step.rating >= config.extreme_step_threshold)
                heappush(frontier, (provider.progress(child), new_extreme, new_score, child_serial,
                                    (child, child_key, (step, node), new_extreme, new_score,
                                     child_depth, child_max)))
            telemetry["peak_frontier"] = max(telemetry["peak_frontier"], len(frontier))
        except (ValueError, TypeError, AttributeError) as exc:
            result.error = str(exc)
            return finish(SearchStatus.ERROR)
    if perf_counter() >= deadline:
        note({"TIME_LIMIT"})
    if reasons:
        return finish(SearchStatus.INCONCLUSIVE_BUDGET)
    result.negative_proof_kind = EXHAUSTIVE_PROOF_KIND
    return finish(SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)


@dataclass
class DescentResult:
    """Outcome of the minimax threshold descent.

    ``conclusive`` is True only when the search immediately below ``upper`` was
    PROVEN_UNSOLVABLE_WITHIN_MODEL (or no lower rating exists). ``stop_reason``:
    EXHAUSTED_BELOW, NO_WITNESS (proven unsolvable at the top and no witness),
    NODE_BUDGET, INCONCLUSIVE, ERROR or INVALID_WITNESS.
    """
    witness: list | None
    upper: float | None
    conclusive: bool = False
    stop_reason: str = ""
    threshold_results: list = field(default_factory=list)
    last: ThresholdResult | None = None
    cache_stats: dict = field(default_factory=dict, compare=False)


def _max_rating(path):
    return max((s.rating for s in path), default=0.0)


def minimax_descent(root, ratings, config, *, provider=None, initial_witness=None, deadline=None,
                    enumerator=None):
    """Lower the rating ceiling below the current witness until a search fails.

    Thresholds are taken from ``ratings`` strictly below the current upper bound
    (never at or above a known witness). A SOLVED search yields a cheaper,
    validated witness; PROVEN_UNSOLVABLE below the witness certifies the minimum
    (transition sets are nested by threshold); anything else stops inconclusive.
    The node budget is shared by all threshold searches.
    """
    provider = provider or SudokuTransitions(config, enumerator)
    ratings = sorted(set(ratings))
    witness = list(initial_witness) if initial_witness is not None else None
    outcome = DescentResult(witness, _max_rating(witness) if witness is not None else None)
    root_state = provider.initial(root)
    while True:
        upper = outcome.upper if outcome.upper is not None else float("inf")
        lower = [r for r in ratings if r < upper]
        if not lower:
            outcome.conclusive, outcome.stop_reason = witness is not None, "EXHAUSTED_BELOW"
            break
        remaining = config.node_budget - sum(t.states_explored for t in outcome.threshold_results)
        if remaining <= 0:
            outcome.stop_reason = "NODE_BUDGET"
            break
        search = threshold_search(root_state, lower[-1], replace(config, node_budget=remaining),
                                  deadline=deadline, provider=provider)
        outcome.threshold_results.append(search)
        outcome.last = search
        if search.status == SearchStatus.SOLVED:
            checker = getattr(provider, "validate_witness", None)
            if checker is not None and not checker(root_state, search.path):
                search.status = SearchStatus.ERROR
                search.error = "Search witness failed independent path validation"
                outcome.stop_reason = "INVALID_WITNESS"
                break
            witness = list(search.path)
            outcome.witness, outcome.upper = witness, _max_rating(witness)
            continue
        if search.status == SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL:
            if witness is None:
                outcome.stop_reason = "NO_WITNESS"
            else:
                outcome.conclusive, outcome.stop_reason = True, "EXHAUSTED_BELOW"
            break
        outcome.stop_reason = "ERROR" if search.error else "INCONCLUSIVE"
        break
    # Review R5: an SSL certificate contradicted by a witness or reachable state
    # within this invocation refutes the theorem or the code: fail closed.
    alarm = confluence_violation(root_state, outcome.threshold_results, outcome.witness)
    if alarm is not None:
        flagged = outcome.threshold_results[-1]
        flagged.status, flagged.error = SearchStatus.ERROR, alarm
        outcome.last, outcome.conclusive, outcome.stop_reason = flagged, False, "ERROR"
    stats = getattr(provider, "cache_stats", None)
    if stats:
        outcome.cache_stats = stats()
    return outcome
