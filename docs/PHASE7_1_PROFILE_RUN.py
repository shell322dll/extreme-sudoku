"""Phase 7.1 profiling harness (diagnostic only; does NOT modify product code).

Instruments the existing certification search by monkeypatching module/class
attributes in this process only. Every job runs in a fresh subprocess so
memory peaks and patches are isolated.

Usage:
  python docs/PHASE7_1_PROFILE_RUN.py --all            # full run, writes BASELINE json/md
  python docs/PHASE7_1_PROFILE_RUN.py --job profile --pid ID --threshold 32 --budget 60 [--big]
  python docs/PHASE7_1_PROFILE_RUN.py --job lattice --pid ID --threshold 32
  python docs/PHASE7_1_PROFILE_RUN.py --job probe --pid ID
"""
import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DOCS = ROOT / "docs"
INPUT = DOCS / "PHASE7_EXPERIMENT_INPUT.json"
OUT_DIR = Path(os.environ.get("PHASE7_1_OUT", str(DOCS / "PHASE7_1_PROFILE_RAW")))

import psutil  # noqa: E402

from generator.certification import enumeration, enum_chains, enum_als, enum_forcing, proofs, search  # noqa: E402
from generator.certification.config import CertificationConfig  # noqa: E402
from generator.certification.enumeration import StepEnumerator  # noqa: E402
from generator.certification.models import SearchStatus  # noqa: E402
from generator.rating.registry import DEFAULT_REGISTRY  # noqa: E402
from generator.solver.human_solver import apply_step, HumanSolver  # noqa: E402
from generator.solver.techniques import ADVANCED_TECHNIQUE_NAMES, TECHNIQUE_TYPES  # noqa: E402
from generator.sudoku.candidates import SudokuState  # noqa: E402

PROC = psutil.Process()
perf = time.perf_counter
CHAIN_NAMES = {"X-Chain", "XY-Chain", "AIC", "Nice Loop", "Grouped AIC"}


def family(name):
    if name in CHAIN_NAMES:
        return "chain:" + name
    if name.startswith("ALS"):
        return "als:" + name
    if name in {"Forcing Chain", "Nishio"}:
        return "forcing:" + name
    if name in {"Full House", "Naked Single", "Hidden Single"}:
        return "singles"
    return "basic"


def puzzles():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    return {p["id"]: p for p in data["puzzles"]}


def grid_of(pid):
    return [int(c) for c in puzzles()[pid]["puzzle"]]


def cand_count(state):
    return sum(m.bit_count() for m in state.candidates)


def raw_sig(state):
    return tuple(state.grid), tuple(state.candidates)


def effect_key(step):
    return tuple(sorted(set(step.placements))), tuple(sorted(set(step.eliminations)))


# ---------------------------------------------------------------- instrumentation
class Prof:
    def __init__(self):
        self.reset()

    def reset(self):
        self.t = defaultdict(float)          # seconds per label
        self.n = Counter()                   # calls per label
        self.tech_steps = Counter()          # steps returned per technique (after inner canonical)
        self.tech_raw = Counter()            # raw representations before inner canonical
        self.tech_limits = Counter()         # limit reason per technique
        self.limit_reasons = Counter()       # per enumerate() call, each distinct reason
        self.enum_calls_with_limits = 0
        self.raw_per_state = []              # (raw_before_outer_canonical, after_outer, distinct_effect_no_rating)
        self.effect_family_dups = Counter()  # number of distinct techniques sharing one effect -> count
        self.fam_pairs = Counter()           # technique-set signature for multi-represented effects
        self.enum_sigs = Counter()
        self.current_tech = None
        self.in_enumerate = False
        # search mirror
        self.mirror = {}
        self.expanded = set()
        self.pops = self.stale_pops = self.reexpansions = self.pushes = 0
        self.child_new = self.child_trans_hit = self.child_depth_improve = self.child_state_limit = 0
        self.pending = None
        self.series = []
        self.sample_every = 25
        self.started = perf()
        self.rss_peak = PROC.memory_info().rss
        self.frontier_peak = 0
        self.children_per_parent = []        # (steps, distinct child signatures)
        self.cur_parent = None
        self.cur_children = None
        self.cur_steps = 0
        self.sampled_states = []
        self.sample_states_every = 0
        self.overhead = 0.0


P = Prof()


def timed(label, fn):
    def wrapper(*a, **k):
        s = perf()
        try:
            return fn(*a, **k)
        finally:
            P.t[label] += perf() - s
            P.n[label] += 1
    return wrapper


def _flush_pending(pushed):
    if P.pending is None:
        return
    in_mirror = P.pending
    if in_mirror:
        if pushed:
            P.child_depth_improve += 1
        else:
            P.child_trans_hit += 1
    else:
        if pushed:
            P.child_new += 1
        else:
            P.child_state_limit += 1
    P.pending = None


def _close_parent():
    if P.cur_parent is not None:
        P.children_per_parent.append((P.cur_steps, len(P.cur_children)))
    P.cur_parent = None


def install():
    # basic detectors
    for cls in TECHNIQUE_TYPES:
        if cls.name in ADVANCED_TECHNIQUE_NAMES:
            continue
        orig = cls.find_steps

        def make(orig, name):
            def find_steps(self, state):
                s = perf()
                out = orig(self, state)
                P.t["tech:" + name] += perf() - s
                P.n["tech:" + name] += 1
                P.tech_steps[name] += len(out)
                P.tech_raw[name] += len(out)
                return out
            return find_steps
        cls.find_steps = make(orig, cls.name)

    # advanced enumerators (enumeration.enumerate imports them at call time)
    def wrap_adv(mod, attr):
        orig = getattr(mod, attr)

        def wrapper(state, technique, config, deadline=float("inf")):
            prev = P.current_tech
            P.current_tech = technique.name
            s = perf()
            try:
                out = orig(state, technique, config, deadline)
            finally:
                P.t["tech:" + technique.name] += perf() - s
                P.n["tech:" + technique.name] += 1
                P.current_tech = prev
            P.tech_steps[technique.name] += len(out.steps)
            for r in out.limit_reasons:
                P.tech_limits[technique.name + ":" + r] += 1
            return out
        setattr(mod, attr, wrapper)
    wrap_adv(enum_chains, "enumerate_chains")
    wrap_adv(enum_als, "enumerate_als_steps")
    wrap_adv(enum_forcing, "enumerate_forcing")

    # canonical_steps: inner (per technique), outer (enumerate), search
    orig_canon = enumeration.canonical_steps

    def inner_canon(steps):
        s = perf()
        out = orig_canon(steps)
        P.t["canonical_inner"] += perf() - s
        P.n["canonical_inner"] += 1
        if P.current_tech:
            P.tech_raw[P.current_tech] += len(steps)
        return out
    for mod in (enum_chains, enum_als, enum_forcing):
        mod.canonical_steps = inner_canon

    def outer_canon(steps):
        steps = list(steps)
        s = perf()
        out = orig_canon(steps)
        P.t["canonical_outer"] += perf() - s
        P.n["canonical_outer"] += 1
        s2 = perf()
        by_eff = defaultdict(set)
        for st in out:
            by_eff[effect_key(st)].add(st.technique)
        for techs in by_eff.values():
            P.effect_family_dups[len(techs)] += 1
            if len(techs) > 1:
                P.fam_pairs["+".join(sorted(techs))] += 1
        P.raw_per_state.append((len(steps), len(out), len(by_eff)))
        P.overhead += perf() - s2
        return out
    enumeration.canonical_steps = outer_canon
    search.canonical_steps = timed("canonical_search", orig_canon)

    orig_enum = StepEnumerator.enumerate

    def enumerate_(self, state, threshold, *, deadline=float("inf")):
        s = perf()
        P.enum_sigs[raw_sig(state)] += 1
        out = orig_enum(self, state, threshold, deadline=deadline)
        P.t["enumerate_total"] += perf() - s
        P.n["enumerate_total"] += 1
        if out.limit_reasons:
            P.enum_calls_with_limits += 1
        for r in out.limit_reasons:
            P.limit_reasons[r] += 1
        return out
    StepEnumerator.enumerate = enumerate_

    proofs.validate_step = timed("validate_step", proofs.validate_step)

    orig_apply = search.apply_step

    def apply_(state, step):
        _flush_pending(False)
        s = perf()
        out = orig_apply(state, step)
        P.t["apply_step"] += perf() - s
        P.n["apply_step"] += 1
        s2 = perf()
        psig = raw_sig(state)
        if P.cur_parent != psig:
            _close_parent()
            P.cur_parent, P.cur_children, P.cur_steps = psig, set(), 0
        csig = raw_sig(out)
        P.cur_children.add(csig)
        P.cur_steps += 1
        P.pending = csig in P.mirror
        P.overhead += perf() - s2
        return out
    search.apply_step = apply_

    SudokuState.signature = timed("signature", SudokuState.signature)
    orig_validate = SudokuState.validate
    SudokuState.validate = timed("SudokuState.validate", orig_validate)

    orig_push, orig_pop = search.heappush, search.heappop

    def push(heap, item):
        s = perf()
        orig_push(heap, item)
        P.t["heap"] += perf() - s
        P.n["heappush"] += 1
        s2 = perf()
        payload = item[4]
        sig = raw_sig(payload[0])
        if P.pushes:
            _flush_pending(True)
        P.pushes += 1
        P.mirror[sig] = len(payload[1])
        P.frontier_peak = max(P.frontier_peak, len(heap))
        P.overhead += perf() - s2

    def pop(heap):
        _flush_pending(False)
        _close_parent()
        s = perf()
        item = orig_pop(heap)
        P.t["heap"] += perf() - s
        P.n["heappop"] += 1
        s2 = perf()
        state, path = item[4][0], item[4][1]
        sig = raw_sig(state)
        P.pops += 1
        if len(path) > P.mirror.get(sig, 1 << 30):
            P.stale_pops += 1
        else:
            if sig in P.expanded:
                P.reexpansions += 1
            P.expanded.add(sig)
            if P.sample_states_every and len(P.expanded) % P.sample_states_every == 1 \
                    and len(P.sampled_states) < 40:
                P.sampled_states.append({"grid": list(state.grid), "candidates": list(state.candidates),
                                         "depth": len(path), "expanded_index": len(P.expanded)})
        if P.pops % P.sample_every == 0:
            rss = PROC.memory_info().rss
            P.rss_peak = max(P.rss_peak, rss)
            P.series.append({"t": round(perf() - P.started, 3), "pops": P.pops, "expanded": len(P.expanded),
                             "unique_states": len(P.mirror), "frontier": len(heap) + 1,
                             "rss_mb": round(rss / 2**20, 1), "min_frontier_cands": item[0]})
        P.overhead += perf() - s2
        return item
    search.heappush, search.heappop = push, pop


# ---------------------------------------------------------------- jobs
def job_profile(pid, threshold, budget, big):
    install()
    cfg = CertificationConfig(time_budget=float(budget))
    if big:
        cfg = replace(cfg, node_budget=1_000_000, state_budget=1_000_000)
    grid = grid_of(pid)
    root = SudokuState(grid)
    P.reset()
    P.sample_every = 25
    P.sample_states_every = 0 if big else 20
    P.started = perf()
    res = search.threshold_search(grid, threshold, cfg)
    _flush_pending(False)
    _close_parent()
    rss_end = PROC.memory_info()
    mi = rss_end
    peak = getattr(mi, "peak_wset", None) or max(P.rss_peak, mi.rss)
    rp = P.raw_per_state
    cpp = P.children_per_parent
    enum_counts = list(P.enum_sigs.values())
    tech_time = {k[5:]: round(v, 4) for k, v in P.t.items() if k.startswith("tech:")}
    fam_time = defaultdict(float)
    for k, v in tech_time.items():
        fam_time[family(k)] += v
    total = res.elapsed_seconds
    lookups = res.cache_hits + res.states_generated  # approx (see md)
    out = {
        "pid": pid, "threshold": threshold, "budget_s": budget, "big_budget": big,
        "config": {"node_budget": cfg.node_budget, "state_budget": cfg.state_budget},
        "root_candidates": cand_count(root),
        "status": res.status.value if hasattr(res.status, "value") else str(res.status),
        "limit_reasons_final": res.limit_reasons, "elapsed_s": round(total, 3),
        "states_explored": res.states_explored, "states_generated": res.states_generated,
        "cache_hits_product": res.cache_hits, "proof_seconds_product": round(res.proof_seconds, 3),
        "mirror": {
            "unique_states": len(P.mirror), "pops": P.pops, "stale_pops": P.stale_pops,
            "expanded_unique": len(P.expanded), "reexpansions": P.reexpansions, "pushes": P.pushes,
            "children_total": P.n["apply_step"], "child_new": P.child_new,
            "child_transposition_hit": P.child_trans_hit, "child_depth_improved_repush": P.child_depth_improve,
            "child_state_limit_drop": P.child_state_limit, "frontier_peak": P.frontier_peak,
            "frontier_end": P.series[-1]["frontier"] if P.series else None,
        },
        "transposition_hit_rate": {
            "child_level": round(P.child_trans_hit / max(1, P.n["apply_step"]), 4),
            "pop_level_stale": round(P.stale_pops / max(1, P.pops), 4),
            "overall_product_cache_hits_over_lookups": round(res.cache_hits / max(1, res.cache_hits + P.child_new + P.child_depth_improve + P.pops - P.stale_pops), 4),
        },
        "enumerate_calls": P.n["enumerate_total"],
        "enumerations_of_same_signature_max": max(enum_counts) if enum_counts else 0,
        "enumerations_repeated": sum(c - 1 for c in enum_counts),
        "branching": {
            "raw_before_outer_canonical_avg": round(sum(r[0] for r in rp) / max(1, len(rp)), 2),
            "raw_before_outer_canonical_max": max((r[0] for r in rp), default=0),
            "after_canonical_avg": round(sum(r[1] for r in rp) / max(1, len(rp)), 2),
            "after_canonical_max": max((r[1] for r in rp), default=0),
            "distinct_effect_ignoring_rating_avg": round(sum(r[2] for r in rp) / max(1, len(rp)), 2),
            "distinct_effect_ignoring_rating_max": max((r[2] for r in rp), default=0),
            "children_per_expanded_avg": round(sum(c[0] for c in cpp) / max(1, len(cpp)), 2),
            "distinct_child_states_per_expanded_avg": round(sum(c[1] for c in cpp) / max(1, len(cpp)), 2),
            "steps_with_child_state_equal_to_sibling_total": sum(c[0] - c[1] for c in cpp),
            "techniques_per_effect_hist": {str(k): v for k, v in sorted(P.effect_family_dups.items())},
            "top_multi_technique_effects": P.fam_pairs.most_common(12),
        },
        "time_s": {k: round(v, 4) for k, v in sorted(P.t.items()) if not k.startswith("tech:")},
        "calls": {k: v for k, v in sorted(P.n.items()) if not k.startswith("tech:")},
        "time_per_technique_s": dict(sorted(tech_time.items(), key=lambda kv: -kv[1])),
        "calls_per_technique": {k[5:]: v for k, v in P.n.items() if k.startswith("tech:")},
        "time_per_family_s": {k: round(v, 4) for k, v in sorted(fam_time.items(), key=lambda kv: -kv[1])},
        "steps_per_technique_after_inner_canonical": dict(P.tech_steps),
        "raw_representations_per_technique": dict(P.tech_raw),
        "technique_limit_reasons": dict(P.tech_limits.most_common()),
        "enumerate_limit_reasons": dict(P.limit_reasons.most_common()),
        "enumerate_calls_with_any_limit": P.enum_calls_with_limits,
        "harness_overhead_s": round(P.overhead, 3),
        "rss_peak_mb": round(peak / 2**20, 1), "rss_end_mb": round(mi.rss / 2**20, 1),
        "series": P.series,
        "sampled_states": P.sampled_states,
    }
    return out


def _subset_dominance(effects):
    sets = [frozenset(a) | frozenset(("e",) + x for x in b) for a, b in effects]
    dominated = 0
    for i, s in enumerate(sets):
        if any(j != i and s < t for j, t in enumerate(sets)):
            dominated += 1
    return dominated


def job_sample_analysis(pid, threshold, samples):
    """Offline per-state structural analysis on sampled expanded states."""
    install()
    cfg = CertificationConfig()
    en = StepEnumerator(cfg)
    rows = []
    for smp in samples:
        state = SudokuState(smp["grid"], smp["candidates"])
        P.reset()
        s = perf()
        r = en.enumerate(state, threshold)
        el = perf() - s
        steps = r.steps
        effects = {}
        reps = defaultdict(list)
        for st in steps:
            reps[effect_key(st)].append(st.technique)
        eff_list = list(reps.keys())
        dominated = _subset_dominance(eff_list) if len(eff_list) <= 600 else None
        children = set()
        for st in steps:
            try:
                children.add(raw_sig(apply_step(state, st)))
            except ValueError:
                pass
        singles_eff = sum(1 for k, v in reps.items() if any(family(t) == "singles" for t in v))
        rows.append({
            "depth": smp["depth"], "candidates": cand_count(state), "enumerate_s": round(el, 4),
            "raw_inner_total": sum(P.tech_raw.values()), "after_inner_total": sum(P.tech_steps.values()),
            "after_outer": len(steps), "distinct_effects_no_rating": len(eff_list),
            "distinct_child_states": len(children), "effects_strict_subset_of_other": dominated,
            "effects_with_single": singles_eff,
            "raw_per_tech": {k: v for k, v in P.tech_raw.items() if v},
            "inner_canonical_per_tech": {k: v for k, v in P.tech_steps.items() if v},
            "time_per_tech": {k[5:]: round(v, 4) for k, v in P.t.items() if k.startswith("tech:") and v > 0.001},
            "limit_reasons": r.limit_reasons,
        })
    return rows


def _enum_only(en, techniques):
    sub = StepEnumerator.__new__(StepEnumerator)
    sub.config, sub.techniques = en.config, techniques
    return sub


def greedy(grid, threshold, cfg, mode, cap):
    """Positive-evidence witness probe. Steps validated with the product validator."""
    en = StepEnumerator(cfg)
    techs = sorted([t for t in en.techniques if t.difficulty <= threshold], key=lambda t: (t.difficulty, t.name))
    subs = [(t, _enum_only(en, [t])) for t in techs]
    state = SudokuState(grid)
    started = perf()
    deadline = started + cap
    path, limits, rounds, distinct_eff = [], Counter(), 0, set()
    stuck_cands = None
    round_limits = set()
    while not state.is_solved:
        if perf() >= deadline:
            return {"solved": False, "reason": "PROBE_TIME_CAP", "steps": len(path), "elapsed_s": round(perf() - started, 2),
                    "candidates_left": cand_count(state), "limits": dict(limits)}
        rounds += 1
        round_limits = set()
        if mode == "cheapest":
            chosen = None
            for t, sub in subs:
                r = sub.enumerate(state, threshold, deadline=deadline)
                round_limits.update(r.limit_reasons)
                for x in r.limit_reasons:
                    limits[x] += 1
                if r.steps:
                    chosen = [r.steps[0]]
                    break
        else:
            r = en.enumerate(state, threshold, deadline=deadline)
            round_limits.update(r.limit_reasons)
            for x in r.limit_reasons:
                limits[x] += 1
            chosen = sorted(r.steps, key=lambda s: s.rating)
        if not chosen:
            stuck_cands = cand_count(state)
            break
        applied = 0
        for st in chosen:
            if any(state.grid[c] or not state.candidates[c] >> (d - 1) & 1 for c, d in st.placements + st.eliminations):
                continue
            pr = proofs.validate_step(state, st, config=cfg)
            if not pr.valid:
                continue
            state = apply_step(state, st)
            path.append(st)
            distinct_eff.add(effect_key(st))
            applied += 1
        if not applied:
            stuck_cands = cand_count(state)
            break
    solved = state.is_solved
    # Independent re-validation of the whole witness from the root.
    valid = None
    if solved:
        valid = proofs.validate_path(grid, path, config=cfg).valid
    rc = Counter(s.technique for s in path)
    return {"solved": solved, "path_valid": valid, "steps": len(path), "rounds": rounds,
            "max_rating": max((s.rating for s in path), default=0.0),
            "elapsed_s": round(perf() - started, 2), "candidates_left": stuck_cands,
            "singles_steps": sum(family(s.technique) == "singles" for s in path),
            "advanced_steps": sum(s.technique in ADVANCED_TECHNIQUE_NAMES for s in path),
            "technique_counts": dict(rc), "limits": dict(limits),
            "stuck_state_enumeration_complete": (None if solved else not round_limits),
            "stuck_state_limits": sorted(round_limits) if not solved else [],
            "final_state": None if solved else {"grid": list(state.grid), "candidates": list(state.candidates)},
            "distinct_effects": len(distinct_eff)}


def _touched(state, eff):
    placements, eliminations = eff
    out = set(eliminations)
    from generator.sudoku.grid import PEERS
    for c, d in placements:
        out.update((c, x) for x in range(1, 10) if state.candidates[c] >> (x - 1) & 1)
        out.update((p, d) for p in PEERS[c] if state.candidates[p] >> (d - 1) & 1)
    return frozenset(out)


def _live_effects(state, steps):
    return {effect_key(s) for s in steps}


def independence_lower_bound(state, threshold, en, trials=12, seed=7, cap_s=400):
    import random
    t0 = perf()
    r = en.enumerate(state, threshold)
    effs = sorted({effect_key(s) for s in r.steps})
    touched = {e: _touched(state, e) for e in effs}
    chosen, used = [], set()
    for e in sorted(effs, key=lambda e: (len(touched[e]), e)):
        if not touched[e] & used:
            chosen.append(e)
            used |= touched[e]
    # persistence: e must still be enumerated (same effect) after applying any other chosen f
    steps_by_eff = {}
    for s in r.steps:
        steps_by_eff.setdefault(effect_key(s), s)
    after = {}
    for f in chosen:
        if perf() - t0 > cap_s:
            break
        sf = apply_step(state, steps_by_eff[f])
        after[f] = _live_effects(sf, en.enumerate(sf, threshold).steps)
    persistent = [e for e in chosen if all(e in after.get(f, set()) for f in chosen if f != e)]
    rng = random.Random(seed)
    realizable = attempted = 0
    for _ in range(trials):
        if perf() - t0 > cap_s or len(persistent) < 2:
            break
        subset = [e for e in persistent if rng.random() < 0.5]
        rng.shuffle(subset)
        cur, ok = state, True
        for e in subset:
            avail = _live_effects(cur, en.enumerate(cur, threshold).steps)
            if e not in avail:
                ok = False
                break
            cur = apply_step(cur, steps_by_eff[e])
        attempted += 1
        realizable += ok
    return {"root_distinct_effects": len(effs), "pairwise_disjoint_effects": len(chosen),
            "mutually_persistent_disjoint_effects": len(persistent),
            "random_subset_trials": attempted, "random_subsets_realizable": realizable,
            "lower_bound_states_2_pow_m": 2 ** len(persistent), "elapsed_s": round(perf() - t0, 1),
            "root_limit_reasons": r.limit_reasons}


def job_lattice(pid, threshold):
    """Greedy fixpoint G at T + capped layered BFS counting with cheap enumeration."""
    cfg = CertificationConfig()
    grid = grid_of(pid)
    root = SudokuState(grid)
    out = {"pid": pid, "threshold": threshold, "root_candidates": cand_count(root)}
    fp = greedy(grid, threshold, cfg, "fixpoint", 600)
    out["fixpoint"] = fp
    # Final candidate count of G (root - eliminated):
    if fp.get("candidates_left") is not None:
        out["k_eliminated_root_to_G"] = cand_count(root) - fp["candidates_left"]
    elif fp["solved"]:
        out["k_eliminated_root_to_G"] = cand_count(root) - 0
    en = StepEnumerator(cfg)
    out["independence_root"] = independence_lower_bound(root, threshold, en)
    fs = fp.get("final_state")
    # Layered BFS with cheap transitions (no validation needed for counting).
    out["bfs"] = {}
    BFS_CAP = float(os.environ.get('PHASE7_1_BFS_CAP', '150'))
    for tcheap, cap_states, cap_s in ((1.2, 300000, BFS_CAP), (18.0, 300000, BFS_CAP), (float(threshold), 300000, BFS_CAP)):
        t0 = perf()
        layer = {raw_sig(root): root}
        seen = set(layer)
        layers = [1]
        edges = 0
        effects = set()
        truncated = None
        depth = 0
        terminals, solved_terminals, limited_states = set(), 0, 0
        while layer and not truncated:
            nxt = {}
            for sig, st in layer.items():
                if perf() - t0 > cap_s:
                    truncated = "TIME_CAP"
                    break
                r = en.enumerate(st, tcheap)
                if r.limit_reasons:
                    limited_states += 1
                if not r.steps:
                    terminals.add(sig)
                    if all(st.grid):
                        solved_terminals += 1
                for step in r.steps:
                    effects.add(effect_key(step))
                    edges += 1
                    try:
                        ch = apply_step(st, step)
                    except ValueError:
                        continue
                    cs = raw_sig(ch)
                    if cs not in seen:
                        seen.add(cs)
                        nxt[cs] = ch
                        if len(seen) >= cap_states:
                            truncated = "STATE_CAP"
                            break
                if truncated:
                    break
            depth += 1
            if nxt:
                layers.append(len(nxt))
            layer = nxt
        out["bfs"][str(tcheap)] = {"layers_unique_new_states": layers, "states_seen": len(seen), "edges": edges,
                                   "distinct_effects": len(effects), "truncated": truncated,
                                   "terminal_states_found": len(terminals), "solved_terminals": solved_terminals,
                                   "expanded_states_with_enumeration_limits": limited_states,
                                   "elapsed_s": round(perf() - t0, 1),
                                   "rss_mb": round(PROC.memory_info().rss / 2**20, 1)}
        del layer, seen
    if fp.get("final_state"):
        fp["final_state"] = "omitted"
    return out


def job_probe(pid, cap):
    cfg = CertificationConfig()
    grid = grid_of(pid)
    hs = HumanSolver(config=cfg.advanced_config).solve(grid)
    upper = hs.max_rating
    ratings = sorted({0.0} | {e.base_rating for e in DEFAULT_REGISTRY.entries})
    rows = []
    current_upper = upper
    while True:
        lower = [r for r in ratings if r < current_upper and r >= 25.0]
        if not lower:
            break
        T = lower[-1]
        row = {"threshold": T}
        best = None
        for mode in ("cheapest", "fixpoint"):
            r = greedy(grid, T, cfg, mode, cap)
            row[mode] = r
            if r["solved"] and r.get("path_valid"):
                best = r["max_rating"] if best is None else min(best, r["max_rating"])
        rows.append(row)
        if best is None:
            break
        current_upper = best
    return {"pid": pid, "human_upper": upper, "human_steps": len(hs.steps), "rows": rows,
            "best_witness_max_rating": current_upper}


def job_walkprobe(pid, cap, seed=11):
    """Randomized witness probe: uniformly random enumerated step at each state.

    Positive evidence only: a solved walk is re-validated from the root with the
    product validate_path. Distinct terminals also test confluence empirically.
    """
    import random
    cfg = CertificationConfig()
    grid = grid_of(pid)
    hs = HumanSolver(config=cfg.advanced_config).solve(grid)
    ratings = sorted({0.0} | {e.base_rating for e in DEFAULT_REGISTRY.entries})
    en = StepEnumerator(cfg)
    rng = random.Random(seed)
    started = perf()
    upper = hs.max_rating
    levels = []
    while perf() - started < cap:
        lower = [r for r in ratings if r < upper and r >= 22.0]
        if not lower:
            break
        T = lower[-1]
        lv = {"threshold": T, "walks": 0, "terminals": Counter(), "terminal_candidates": {},
              "limited_enumerations": 0, "enumerations": 0, "witness": None}
        while perf() - started < cap and lv["witness"] is None:
            st, path = SudokuState(grid), []
            while perf() - started < cap:
                r = en.enumerate(st, T)
                lv["enumerations"] += 1
                lv["limited_enumerations"] += bool(r.limit_reasons)
                if not r.steps:
                    break
                step = rng.choice(r.steps)
                st = apply_step(st, step)
                path.append(step)
            else:
                break
            lv["walks"] += 1
            sig = hash(raw_sig(st))
            lv["terminals"][sig] += 1
            lv["terminal_candidates"][sig] = cand_count(st)
            if all(st.grid):
                ok = proofs.validate_path(grid, path, config=cfg).valid
                lv["witness"] = {"path_valid": ok, "steps": len(path),
                                 "max_rating": max(x.rating for x in path),
                                 "technique_counts": dict(Counter(x.technique for x in path)),
                                 "found_after_s": round(perf() - started, 1)}
        lv["distinct_terminals"] = len(lv["terminals"])
        lv["terminal_candidates"] = sorted(lv["terminal_candidates"].values())
        lv["terminals"] = sorted(lv["terminals"].values(), reverse=True)
        levels.append(lv)
        if lv["witness"] and lv["witness"]["path_valid"]:
            upper = lv["witness"]["max_rating"]
        else:
            break
    return {"pid": pid, "human_upper": hs.max_rating, "best_validated_upper": upper, "levels": levels,
            "elapsed_s": round(perf() - started, 1), "cap_s": cap}


# ---------------------------------------------------------------- orchestration
def run_child(args, timeout):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(Path(__file__).resolve())] + args
    t0 = perf()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
    if p.returncode != 0:
        raise RuntimeError(f"child failed {args}: {p.stderr[-3000:]}")
    print(f"[{time.strftime('%H:%M:%S')}] done {' '.join(args)} in {perf() - t0:.1f}s", flush=True)
    return json.loads(p.stdout.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job")
    ap.add_argument("--pid")
    ap.add_argument("--threshold", type=float)
    ap.add_argument("--budget", type=float, default=60)
    ap.add_argument("--big", action="store_true")
    ap.add_argument("--cap", type=float, default=240)
    ap.add_argument("--samples")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--stage", default="profile,lattice,probe")
    a = ap.parse_args()
    if a.job == "profile":
        res = job_profile(a.pid, a.threshold, a.budget, a.big)
        path = OUT_DIR / f"profile_{a.pid[-6:]}_{int(a.threshold)}_{int(a.budget)}{'_big' if a.big else ''}.json"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        print(json.dumps({"file": str(path)}))
    elif a.job == "samples":
        samples = json.loads(Path(a.samples).read_text(encoding="utf-8"))
        res = job_sample_analysis(a.pid, a.threshold, samples)
        print(json.dumps(res, default=str))
    elif a.job == "lattice":
        print(json.dumps(job_lattice(a.pid, a.threshold), default=str))
    elif a.job == "walkprobe":
        print(json.dumps(job_walkprobe(a.pid, a.cap), default=str))
    elif a.job == "probe":
        print(json.dumps(job_probe(a.pid, a.cap), default=str))
    elif a.all:
        orchestrate(a.stage.split(","), a.cap)


def orchestrate(stages, cap):
    from concurrent.futures import ThreadPoolExecutor
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = [("puzzle-8e2b144cecb50551d96b", 32.0), ("puzzle-ca88d658a18eafb27c24", 50.0)]
    agg_path = OUT_DIR / "aggregate.json"
    agg = json.loads(agg_path.read_text(encoding="utf-8")) if agg_path.exists() else {}
    if "profile" in stages:
        agg["profiles"] = {}
        agg["sample_analysis"] = {}
        for pid, T in targets:
            for budget, big in ((60, False), (300, True)):
                f = run_child(["--job", "profile", "--pid", pid, "--threshold", str(T), "--budget", str(budget)]
                              + (["--big"] if big else []), timeout=budget + 600)["file"]
                prof = json.loads(Path(f).read_text(encoding="utf-8"))
                agg["profiles"][f"{pid}|{T}|{budget}"] = {k: v for k, v in prof.items() if k != "sampled_states"}
                if not big and prof["sampled_states"]:
                    sp = OUT_DIR / f"samples_{pid[-6:]}.json"
                    sp.write_text(json.dumps(prof["sampled_states"][:25]), encoding="utf-8")
                    agg["sample_analysis"][pid] = run_child(["--job", "samples", "--pid", pid, "--threshold", str(T),
                                                             "--samples", str(sp)], timeout=1800)
                agg_path.write_text(json.dumps(agg, indent=1, default=str), encoding="utf-8")
    if "lattice" in stages:
        agg["lattice"] = {}
        with ThreadPoolExecutor(2) as ex:
            futs = {pid: ex.submit(run_child, ["--job", "lattice", "--pid", pid, "--threshold", str(T)], 2400)
                    for pid, T in targets}
            for pid, fu in futs.items():
                agg["lattice"][pid] = fu.result()
        agg_path.write_text(json.dumps(agg, indent=1, default=str), encoding="utf-8")
    if "probe" in stages:
        agg["probe"] = {}
        ids = list(puzzles())
        with ThreadPoolExecutor(5) as ex:
            futs = {pid: ex.submit(run_child, ["--job", "probe", "--pid", pid, "--cap", str(cap)], 7200) for pid in ids}
            for pid, fu in futs.items():
                try:
                    agg["probe"][pid] = fu.result()
                except Exception as exc:  # report, do not hide
                    agg["probe"][pid] = {"error": str(exc)}
        agg_path.write_text(json.dumps(agg, indent=1, default=str), encoding="utf-8")
    if "walkprobe" in stages:
        agg["walkprobe"] = {}
        ids = list(puzzles())
        with ThreadPoolExecutor(9) as ex:
            futs = {pid: ex.submit(run_child, ["--job", "walkprobe", "--pid", pid, "--cap", str(cap)], cap + 900)
                    for pid in ids}
            for pid, fu in futs.items():
                try:
                    agg["walkprobe"][pid] = fu.result()
                except Exception as exc:
                    agg["walkprobe"][pid] = {"error": str(exc)}
        agg_path.write_text(json.dumps(agg, indent=1, default=str), encoding="utf-8")
    (DOCS / "PHASE7_1_PROFILE_BASELINE.json").write_text(json.dumps(agg, indent=1, default=str), encoding="utf-8")
    print("written", DOCS / "PHASE7_1_PROFILE_BASELINE.json")


if __name__ == "__main__":
    main()
