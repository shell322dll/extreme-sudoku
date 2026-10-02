"""Reproduce Phase 4 timings: python -m generator.tests.profile_phase4.

Run without concurrent test suites or other CPU-heavy jobs. Timings are diagnostic,
never pass/fail thresholds. Add --include-expensive for the existing seed 48 puzzle.
Only the requested output report is written; no fixtures or solver files change.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter

from generator.rating.config import DifficultyConfig
from generator.rating.difficulty import DifficultyAnalyzer
from generator.rating.state_analysis import StateAnalyzer
from generator.solver.human_solver import HumanSolver, apply_step
from generator.solver.techniques import advanced_techniques
from generator.sudoku.candidates import SudokuState


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
BASIC = "530070000600195000098000060800060003400803001700020006060000280000419005000080079"


def measure(action, repeats):
    samples = []
    first = None
    for index in range(repeats):
        start = perf_counter()
        result = action()
        samples.append(perf_counter() - start)
        if index == 0:
            first = result
        elif first != result:
            raise AssertionError("Identical configuration must produce identical results")
    return first, {"samples_seconds": [round(s, 6) for s in samples],
                   "median_seconds": round(statistics.median(samples), 6)}


def rating_metrics(result):
    if not result.solved or result.invalid or result.used_backtracking or result.guesses:
        raise AssertionError("The profile fixture must solve using valid human logic")
    names = ("difficulty_class", "rating", "hardest_rating", "hardest_required_rating",
             "minimum_tier", "step_count", "advanced_steps", "extreme_steps",
             "true_bottleneck_count", "longest_chain", "is_extreme_candidate",
             "is_ultra_extreme_candidate", "profile_statuses", "unique")
    return {name: getattr(result, name) for name in names}


def profile_puzzle(fixture, config, repeats):
    puzzle = list(map(int, fixture["puzzle"]))
    normal, normal_time = measure(lambda: HumanSolver(config=config.search).solve(puzzle), repeats)
    if not normal.solved or normal.invalid or normal.used_backtracking or normal.guesses:
        raise AssertionError("Normal HumanSolver must solve the fixture")
    quick, quick_time = measure(lambda: DifficultyAnalyzer(config).quick(puzzle), repeats)
    deep, deep_time = measure(lambda: DifficultyAnalyzer(config).deep(puzzle, check_unique=True), repeats)
    cached_analyzer = DifficultyAnalyzer(config)
    cached_analyzer.deep(puzzle, check_unique=True)  # Prime outside the warm timing sample.
    warm, warm_time = measure(lambda: cached_analyzer.deep(puzzle, check_unique=True), repeats)
    if warm != deep:
        raise AssertionError("Warm cache changed the difficulty result")
    item = {**fixture,
            "normal": {**normal_time, "steps": len(normal.steps), "hardest_rating": normal.max_rating},
            "quick": {**quick_time, **rating_metrics(quick)},
            "deep_cold": {**deep_time, **rating_metrics(deep)},
            "deep_warm": {**warm_time, "cache_hits": cached_analyzer.state_analyzer.cache_hits,
                          "cache_misses": cached_analyzer.state_analyzer.cache_misses}}
    item["deep_to_normal_ratio"] = round(deep_time["median_seconds"] / normal_time["median_seconds"], 3)
    print(f"{fixture['id']}: normal={normal_time['median_seconds']:.3f}s "
          f"quick={quick_time['median_seconds']:.3f}s deep={deep_time['median_seconds']:.3f}s "
          f"warm={warm_time['median_seconds']:.3f}s", flush=True)
    return item


def profile_state(puzzle, config, repeats):
    solver = HumanSolver(config=config.search)
    state = SudokuState(list(map(int, puzzle)))
    path = solver.solve(state.grid).steps
    for index, step in enumerate(path):
        if step.technique == "AIC":
            break
        state = apply_step(state, step)
    else:
        raise AssertionError("The seed 4 fixture must contain an AIC bottleneck")
    signature = state.signature()
    minimum, minimum_time = measure(lambda: StateAnalyzer(config).minimum_available_rating(state), repeats)
    full, full_time = measure(lambda: StateAnalyzer(config).analyze_state(state), repeats)
    raw, raw_time = measure(lambda: solver.all_available_steps(state), repeats)
    if minimum.minimum_rating != full.minimum_rating or tuple(raw) != full.steps:
        raise AssertionError("Minimum/full analysis and HumanSolver enumeration disagree")
    cached = StateAnalyzer(config)
    cached.analyze_state(state)
    hit, hit_time = measure(lambda: cached.analyze_state(state), repeats)
    if hit != full or cached.cache_hits != repeats or cached.cache_misses != 1:
        raise AssertionError("Expected exactly one cache miss followed by cache hits")
    detector_stats = {}
    for technique in advanced_techniques(config=config.search):
        steps, timing = measure(lambda: technique.find_steps(state), repeats)
        detector_stats[technique.name] = {**timing, "emitted_steps": len(steps)}
    if state.signature() != signature:
        raise AssertionError("A profile operation mutated the state")
    return {"fixture": "seed_4", "path_step_index": index, "next_technique": step.technique,
            "remaining_candidates": sum(mask.bit_count() for mask in state.candidates),
            "minimum_rating": full.minimum_rating, "available_steps": full.number_of_alternatives,
            "minimum_only_cold": minimum_time, "full_analysis_cold": full_time,
            "human_all_available_steps": raw_time, "full_analysis_cache_hit": hit_time,
            "cache_hits": cached.cache_hits, "cache_misses": cached.cache_misses,
            "detectors": dict(sorted(detector_stats.items(),
                                      key=lambda item: (-item[1]["median_seconds"], item[0])))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/PHASE4_PROFILE.json")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--include-expensive", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    phase2 = json.loads((FIXTURES / "phase2_puzzles.json").read_text(encoding="utf-8"))
    phase3 = json.loads((FIXTURES / "phase3_puzzles.json").read_text(encoding="utf-8"))
    by_seed = {f["seed"]: f for f in phase2 + phase3}
    selected = [{"id": "basic", "puzzle": BASIC, "source": "test_human_solver.PUZZLE"}]
    for seed in [21, 3, 4] + ([48] if args.include_expensive else []):
        selected.append({"id": f"seed_{seed}", "puzzle": by_seed[seed]["puzzle"],
                         "source": "existing Phase 2/3 regression fixture", "seed": seed})
    config = DifficultyConfig()
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "command": "python -m generator.tests.profile_phase4 " + " ".join(sys.argv[1:]),
              "environment": {"executable": sys.executable, "python": sys.version,
                              "platform": platform.platform(), "processor": platform.processor()},
              "config": config.to_dict(), "repeats": args.repeats,
              "notes": ["Wall-clock measurements; medians and raw samples; no timing assertions.",
                        "Run with no competing test suites or CPU-heavy processes.",
                        "Cold means a new analyzer, not a new Python process or empty OS cache.",
                        "Warm Deep caches state analyses; threshold and profile solves still run.",
                        "Quick has no threshold solves, alternative enumeration or uniqueness check.",
                        "Deep includes a separate exact uniqueness check for preliminary certification.",
                        "Analysis validates emitted steps; raw HumanSolver enumeration does not.",
                        "All necessity evidence is bounded; no exhaustive logical-path minimum proof.",
                        "Optional seed 48 is omitted unless --include-expensive is supplied."],
              "puzzles": [profile_puzzle(f, config, args.repeats) for f in selected],
              "bottleneck_state": profile_state(by_seed[4]["puzzle"], config, args.repeats)}
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Profile written to {args.output}", flush=True)


if __name__ == "__main__":
    main()
