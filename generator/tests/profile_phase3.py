"""Reproduce Phase 3 timings: python -m generator.tests.profile_phase3.

Wall times are diagnostic, not pass/fail thresholds. Run without another CPU
heavy task for useful comparisons. No profiling code enters production imports.
"""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

from generator.solver.advanced_config import AdvancedConfig
from generator.solver.human_solver import HumanSolver, apply_step
from generator.solver.techniques import advanced_techniques, phase2_techniques
from generator.solver.techniques.als import ALSGraph
from generator.solver.techniques.chains import InferenceGraph
from generator.sudoku.candidates import SudokuState


ROOT = Path(__file__).resolve().parents[2]


def timed(action):
    start = perf_counter()
    result = action()
    return result, round(perf_counter() - start, 6)


def proof_metrics(steps):
    return {
        "maximum_candidate_chain_links": max((s.chain.length for s in steps
                                             if s.chain and not s.als), default=0),
        "maximum_als_rcc_links": max((s.chain.length for s in steps if s.als), default=0),
        "maximum_forcing_dependency_depth": max((p.depth for s in steps for p in s.assumptions), default=0),
    }


def result_metrics(result):
    if not result.solved or result.invalid:
        raise AssertionError("Profile fixture must solve without invalid steps")
    return {"solved": result.solved, "step_count": len(result.steps),
            "advanced_steps": result.advanced_steps,
            "technique_counts": result.technique_counts, **proof_metrics(result.steps)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/PHASE3_PROFILE.json")
    args = parser.parse_args()
    fixtures = json.loads((Path(__file__).parent / "fixtures/phase3_puzzles.json").read_text(encoding="utf-8"))
    config = AdvancedConfig()
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "command": "python -m generator.tests.profile_phase3",
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "processor": platform.processor()},
        "config": asdict(config),
        "notes": ["One wall-clock sample per operation; no timing assertions.",
                  "Unique puzzles are profiled once; target repertoires separately.",
                  "Candidate links, ALS RCC edges and forcing dependency depth are distinct units.",
                  "search_complexity is proof discovery work, not full detector elapsed work.",
                  "Graph building and search are finite; emitted deductions are representative, not exhaustive."],
        "puzzles": [], "target_repertoires": [],
    }
    unique = {f["puzzle"]: f for f in fixtures}
    for text, fixture in unique.items():
        puzzle = list(map(int, text))
        basic, phase2_seconds = timed(lambda: HumanSolver(phase2_techniques()).solve(puzzle))
        if not basic.stuck:
            raise AssertionError("Expected Phase 2 to be stuck")
        state = SudokuState(puzzle)
        for step in basic.steps:
            state = apply_step(state, step)
        item = {"seed": fixture["seed"], "puzzle": text,
                "phase2_seconds": phase2_seconds, "phase2_step_count": len(basic.steps),
                "remaining_candidates": sum(m.bit_count() for m in state.candidates),
                "inference_graphs": {}, "detectors": {}}
        for mode, grouped in (("x", False), ("xy", False), ("aic", False), ("aic", True)):
            graph, seconds = timed(lambda: InferenceGraph(state, mode=mode, grouped=grouped))
            item["inference_graphs"]["grouped_aic" if grouped else mode] = {
                "build_seconds": seconds, "nodes": len(graph.nodes),
                "strong_edges": sum(map(len, graph.strong)) // 2,
                "weak_edges": sum(map(len, graph.weak)) // 2}
        als_graph, seconds = timed(lambda: ALSGraph.build(state, config))
        item["als_graph"] = {"build_seconds": seconds, "nodes": len(als_graph.nodes),
                             "rcc_edges": sum(map(len, als_graph.adjacency)) // 2,
                             "pair_checks": als_graph.pair_checks, "truncated": als_graph.truncated}
        for technique in advanced_techniques(config=config):
            before = (state.grid[:], state.candidates[:])
            steps, seconds = timed(lambda: technique.find_steps(state))
            if before != (state.grid, state.candidates):
                raise AssertionError("Detector mutated profile state")
            item["detectors"][technique.name] = {
                "seconds": seconds, "emitted_steps": len(steps),
                "maximum_reported_search_complexity": max((s.search_complexity for s in steps), default=0),
                **proof_metrics(steps)}
        solved, seconds = timed(lambda: HumanSolver(config=config).solve(puzzle))
        item["default_solve"] = {"seconds": seconds, **result_metrics(solved)}
        report["puzzles"].append(item)
        print(f"seed={fixture['seed']} solved in {seconds:.3f}s", flush=True)
    by_name = {t.name: t for t in advanced_techniques(config=config)}
    for fixture in fixtures:
        if fixture["target_repertoire"] == "default":
            continue
        solver = HumanSolver(phase2_techniques() + [by_name[fixture["target_technique"]]])
        solved, seconds = timed(lambda: solver.solve(list(map(int, fixture["puzzle"]))))
        report["target_repertoires"].append({"id": fixture["id"], "seconds": seconds, **result_metrics(solved)})
    totals = {name: round(sum(p["detectors"][name]["seconds"] for p in report["puzzles"]), 6)
              for name in by_name}
    report["summary"] = {
        "unique_puzzles": len(unique), "fixture_entries": len(fixtures),
        "default_solves_seconds": round(sum(p["default_solve"]["seconds"] for p in report["puzzles"]), 6),
        "detectors_seconds_by_name": dict(sorted(totals.items(), key=lambda item: -item[1])),
        "slowest_detector": max(totals, key=totals.get),
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
