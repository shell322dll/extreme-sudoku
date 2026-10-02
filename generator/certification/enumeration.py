"""Complete transition enumeration, or explicit evidence of omitted work.

The existing Phase 3 detectors keep representative paths. Certification instead
enumerates every simple path. Operational limits are NOT part of the definition
of a technique: reaching them makes a negative result inconclusive.

Phase 7.1 (performance only): representatives are chosen with cheap structured
keys first and the full proof is serialized only for genuine ties, which selects
exactly the same representative as sorting every step by the full JSON proof.
Per-technique enumeration results may be memoized in an invocation-local,
bounded cache keyed by the complete state signature (values81 + masks81).
"""
from collections import OrderedDict
from time import perf_counter
from dataclasses import asdict
import json
from ..solver.techniques import default_techniques, ADVANCED_TECHNIQUE_NAMES
from ..solver.techniques.base import step_key
from .models import EnumerationResult


def proof_json(step):
    """Complete immutable proof serialization: the final, total tie-break."""
    return json.dumps(asdict(step), sort_keys=True, separators=(",", ":"), allow_nan=False)


def effect_key(step):
    return tuple(sorted(set(step.placements))), tuple(sorted(set(step.eliminations)))


def representative(group):
    """Minimum of ``group`` by (rating, step_key, full JSON proof).

    Identical to ``sorted(group, key=(rating, step_key, json))[0]`` (stable sort:
    complete ties keep input order), but JSON is computed only for steps that tie
    on every cheap key. The choice therefore never depends on input order.
    """
    if len(group) == 1:
        return group[0]
    keys = [(s.rating, step_key(s)) for s in group]
    best = min(keys)
    tied = [s for s, k in zip(group, keys) if k == best]
    if len(tied) == 1:
        return tied[0]
    proofs = [proof_json(s) for s in tied]
    return tied[proofs.index(min(proofs))]


def _grouped(steps, key):
    groups = {}
    for step in steps:
        groups.setdefault(key(step), []).append(step)
    chosen = [representative(group) for group in groups.values()]
    # Distinct groups never tie on (rating, step_key): step_key contains the raw
    # effects, and equal (effect, rating) would be the same group.
    chosen.sort(key=lambda s: (s.rating, step_key(s)))
    return chosen


def canonical_steps(steps):
    """Equivalent effects AT THE SAME RATING keep one canonical proof.

    Semantics are unchanged from Phase 7: the key includes the rating, so equal
    effects of different techniques survive here (bottleneck evidence and
    enumeration limits depend on it). The search merges further, by successor
    state signature across ratings (``search.select_transitions``), keeping the
    cheapest proof per distinct successor. ``canonical_effects`` is an
    effect-level helper (same rating-independent idea), not used by the search.
    """
    return _grouped(steps, lambda s: effect_key(s) + (s.rating,))


def canonical_effects(steps):
    """One transition per distinct effect, keeping the lowest-rating proof.

    Two steps with the same placements and eliminations produce the same
    successor state, so the cheaper one dominates the other for every minimax
    objective (max rating, extreme-step count and score are all no larger).
    """
    return _grouped(steps, effect_key)


class EnumerationCache:
    """Invocation-local LRU of per-technique results.

    Key: (enumerator config identity, full state signature, technique name), so
    a cache shared between enumerators with different limits cannot mix their
    results (review P2-8). Results cut by a deadline are
    never stored; results cut by deterministic work limits are stored together
    with their limit reasons (the detectors are deterministic functions of the
    state and the fixed configuration of the owning enumerator).
    """

    # Phase 7.1 memory tuning: within one exhaustive search every expanded state
    # is new (0 hits measured); the cache pays off across stages (SSL closure ->
    # fallback search -> bottlenecks), which touch a few hundred states. A small
    # LRU keeps that benefit without retaining every expanded state.
    def __init__(self, max_entries=12000):
        self.max_entries = max_entries
        self.entries = OrderedDict()
        self.hits = self.misses = self.stores = self.evictions = self.skipped_time_limited = 0

    def get(self, key):
        found = self.entries.get(key)
        if found is None:
            self.misses += 1
            return None
        self.entries.move_to_end(key)
        self.hits += 1
        return found

    def put(self, key, result):
        if any("TIME_LIMIT" in r for r in result.limit_reasons):
            self.skipped_time_limited += 1
            return
        self.entries[key] = (tuple(result.steps), tuple(result.limit_reasons), result.complete, result.work)
        self.entries.move_to_end(key)
        self.stores += 1
        while len(self.entries) > self.max_entries:
            self.entries.popitem(last=False)
            self.evictions += 1

    def stats(self):
        lookups = self.hits + self.misses
        return {"lookups": lookups, "hits": self.hits, "misses": self.misses,
                "hit_rate": self.hits / lookups if lookups else 0.0, "stores": self.stores,
                "evictions": self.evictions, "entries": len(self.entries),
                "skipped_time_limited": self.skipped_time_limited}


class StepEnumerator:
    def __init__(self, config, *, cache=True):
        self.config = config
        self.techniques = default_techniques(config=config.advanced_config)
        self.cache = EnumerationCache() if cache is True else (cache or None)
        fingerprint = getattr(config, "fingerprint", None)
        self.config_key = fingerprint() if callable(fingerprint) else repr(config)
        self.family_seconds = {}
        self.family_raw_steps = {}

    def _run(self, technique, state, deadline, graphs=None):
        from .enum_chains import enumerate_chains
        from .enum_als import enumerate_als_steps
        from .enum_forcing import enumerate_forcing
        name = technique.name
        if name not in ADVANCED_TECHNIQUE_NAMES:
            return EnumerationResult(technique.find_steps(state))
        if name in {"X-Chain", "XY-Chain", "AIC", "Nice Loop", "Grouped AIC"}:
            graph = None
            if graphs is not None:
                # The inference graph is a pure function of (state, grouped, mode):
                # AIC and Nice Loop share one immutable graph per state.
                from ..solver.techniques.chains import InferenceGraph
                key = (technique.grouped, technique.mode)
                graph = graphs.get(key)
                if graph is None:
                    graph = graphs[key] = InferenceGraph(state, grouped=technique.grouped, mode=technique.mode)
            return enumerate_chains(state, technique, self.config, deadline, graph=graph)
        if name.startswith("ALS"):
            return enumerate_als_steps(state, technique, self.config, deadline)
        return enumerate_forcing(state, technique, self.config, deadline)

    def enumerate(self, state, threshold, *, deadline=float("inf")):
        result = EnumerationResult()
        signature = state.signature() if self.cache is not None else None
        graphs = {}
        for technique in self.techniques:
            if technique.difficulty > threshold:
                continue
            if perf_counter() >= deadline:
                result.limit_reasons.append("TIME_LIMIT")
                break
            name = technique.name
            cache_key = (self.config_key, signature, name)
            cached = self.cache.get(cache_key) if self.cache is not None else None
            if cached is not None:
                steps, reasons, complete, work = cached
                found = EnumerationResult(list(steps), complete, list(reasons), work)
            else:
                started = perf_counter()
                found = self._run(technique, state, deadline, graphs)
                self.family_seconds[name] = self.family_seconds.get(name, 0.0) + perf_counter() - started
                self.family_raw_steps[name] = self.family_raw_steps.get(name, 0) + len(found.steps)
                if self.cache is not None:
                    self.cache.put(cache_key, found)
            result.steps.extend(found.steps)
            result.limit_reasons.extend(f"{name}:{reason}" for reason in found.limit_reasons)
            result.work += found.work
        result.steps = canonical_steps(result.steps)
        if len(result.steps) > self.config.max_alternative_steps_per_state:
            result.steps = result.steps[:self.config.max_alternative_steps_per_state]
            result.limit_reasons.append("ALTERNATIVE_STEP_LIMIT")
        if perf_counter() >= deadline:
            result.limit_reasons.append("TIME_LIMIT")
        result.limit_reasons = sorted(set(result.limit_reasons))
        result.complete = not result.limit_reasons
        return result
