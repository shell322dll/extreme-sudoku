"""Reproduce real Phase 5 smoke/batch timings without concurrent CPU-heavy jobs.

Run: python -m generator.tests.profile_phase5
The default run writes docs/PHASE5_PROFILE.json and data/puzzles.json.
Timings are diagnostics, never test thresholds. No fixtures or ratings are mocked.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import random
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

from generator.clue_generator import is_minimal
from generator.chromosome import Individual
from generator.config import GeneratorConfig
from generator.construction import FULL_MASK, minimalize, remove_clues
from generator.models import GENERATOR_VERSION
from generator.pipeline import generate_many
from generator.rating.difficulty import DifficultyAnalyzer
from generator.solver.exact_solver import count_solutions
from generator.sudoku.grid import ALL_UNITS


ROOT = Path(__file__).resolve().parents[2]
CLASSES = ("Easy", "Medium", "Hard", "Expert", "Extreme", "Ultra Extreme")


def timed(action):
    start = perf_counter()
    result = action()
    return result, round(perf_counter() - start, 6)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def independently_validate(document):
    """Reparse exported content and use fresh exact checks, without pipeline caches."""
    check(document["schemaVersion"] == 1, "Unexpected schemaVersion")
    ids, puzzles = set(), set()
    records = []
    for record in document["puzzles"]:
        puzzle, solution = record["puzzle"], record["solution"]
        check(record["id"] not in ids, "Duplicate ID")
        check(puzzle not in puzzles, "Duplicate puzzle")
        check(len(puzzle) == 81 and set(puzzle) <= set("0123456789"), "Invalid puzzle string")
        check(len(solution) == 81 and set(solution) <= set("123456789"), "Invalid solution string")
        check(all(set(solution[index] for index in unit) == set("123456789")
                  for unit in ALL_UNITS), "Invalid complete solution")
        check(all(given == "0" or given == value for given, value in zip(puzzle, solution)),
              "Given does not match solution")
        check(record["clues"] == sum(value != "0" for value in puzzle), "Wrong clue count")
        check(record["difficulty"] in CLASSES, "Invalid difficulty class")
        board = list(map(int, puzzle))
        check(record["unique"] is True and count_solutions(board, limit=2) == 1,
              "Fresh uniqueness check failed")
        minimal = is_minimal(board)
        check(record["minimal"] is minimal, "Fresh minimality check disagrees")
        ids.add(record["id"])
        puzzles.add(puzzle)
        records.append({"id": record["id"], "unique": True, "minimal": minimal})
    return records


def summary(record):
    result = {key: record[key] for key in ("id", "clues", "difficulty", "rating", "minimal")}
    result["hardestTechnique"] = record.get("hardestTechnique")
    if result["hardestTechnique"] is None:
        result["observedHardestTechnique"] = record.get("ratingMetadata", {}).get("observedHardestTechnique")
    return result


def rating_summary(result):
    check(result.solved and not result.invalid and not result.used_backtracking and not result.guesses,
          "Human analysis must solve without guesses or backtracking")
    return {name: getattr(result, name) for name in
            ("mode", "difficulty_class", "rating", "hardest_technique", "hardest_rating",
             "hardest_required_rating", "true_bottleneck_count", "advanced_steps",
             "longest_chain", "is_extreme_candidate", "is_ultra_extreme_candidate")}


def config_dict(config):
    result = {name: value for name, value in vars(config).items() if name != "difficulty_config"}
    result["difficulty_config"] = config.difficulty_config.to_dict()
    return result


def run_batch(label, count, config):
    def progress(stats, record):
        description = (f"{record.difficulty}/{record.rating:g}" if record else "rejected")
        print(f"{label}: attempts={stats.attempts} accepted={stats.accepted}/{count} {description}",
              flush=True)
    result, elapsed = timed(lambda: generate_many(count, config, progress=progress))
    stats = result.stats.to_dict()
    means = {stage: round(seconds / result.stats.stage_calls[stage], 6)
             for stage, seconds in result.stats.stage_seconds.items()}
    report = {"config": config_dict(config), "requested": count,
              "complete": result.complete, "wall_seconds": elapsed, "stats": stats,
              "mean_stage_seconds": means,
              "acceptance_rate": result.stats.accepted / max(result.stats.attempts, 1),
              "accepted_class_counts": {name: sum(p.difficulty == name for p in result.puzzles)
                                        for name in CLASSES},
              "preliminary_candidates": len(result.preliminary_candidates)}
    return result, report


def main():
    # Import late so lightweight diagnostic helpers do not depend on export.
    from generator.export import export_puzzles, validate_database

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/PHASE5_PROFILE.json")
    parser.add_argument("--database", type=Path, default=ROOT / "data/puzzles.json")
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    smoke_config = GeneratorConfig(seed=args.seed, min_clues=35, max_clues=40,
                                   require_minimal=False, rating_mode="quick", max_attempts=4)
    smoke, smoke_report = run_batch("smoke", 1, smoke_config)
    check(smoke.complete, "Fixed-seed smoke failed")
    repeated, repeat_seconds = timed(lambda: generate_many(1, smoke_config))
    check(smoke.puzzles == repeated.puzzles, "Identical smoke seed/config changed results")
    with TemporaryDirectory(prefix="extreme-sudoku-phase5-") as folder:
        path = Path(folder) / "smoke.json"
        export_puzzles(smoke.puzzles, path, generated_at=timestamp)
        parsed = json.loads(path.read_text(encoding="utf-8"))
        validate_database(parsed)
        smoke_report.update(summary=summary(parsed["puzzles"][0]),
                            repeated_seconds=repeat_seconds, reproducible=True,
                            independent_validation=independently_validate(parsed))

    config = GeneratorConfig(seed=args.seed, min_clues=17, max_clues=30,
                             require_minimal=True, max_attempts=max(20, args.count * 3))
    batch, batch_report = run_batch("sample", args.count, config)
    check(batch.complete, "Real sample batch failed its bounded attempt budget")
    document, export_seconds = timed(lambda: export_puzzles(
        batch.puzzles, args.database, generated_at=timestamp))
    parsed = json.loads(args.database.read_text(encoding="utf-8"))
    check(parsed == document, "Export did not round-trip")
    validate_database(parsed)
    validation, validation_seconds = timed(lambda: independently_validate(parsed))
    batch_report.update(export_seconds=export_seconds, independent_validation_seconds=validation_seconds,
                        independent_validation=validation,
                        summary=[summary(record) for record in parsed["puzzles"]])

    # A bounded default-range diagnostic; partial acceptance is a valid outcome.
    narrow_config = GeneratorConfig(seed=args.seed, max_attempts=8)
    narrow, narrow_report = run_batch("default-range", 8, narrow_config)
    narrow_report["accepted_ids"] = [puzzle.id for puzzle in narrow.puzzles]

    # Cold rating uses fresh analyzers, outside pipeline caches, for both an easy
    # smoke puzzle and the highest-rated generated sample (no fixture selection).
    selected = (smoke.puzzles[0], max(batch.puzzles, key=lambda p: (p.rating, p.id)))
    cold = []
    for record in selected:
        board = list(map(int, record.puzzle))
        quick, quick_seconds = timed(lambda: DifficultyAnalyzer().quick(board))
        deep, deep_seconds = timed(lambda: DifficultyAnalyzer().deep(board, check_unique=True))
        candidate = Individual(FULL_MASK, tuple(map(int, record.solution)))
        partial = remove_clues(candidate, 35, rng=random.Random(record.attempt_seed))
        minimized, minimal_seconds = timed(lambda: minimalize(
            partial, rng=random.Random(record.attempt_seed)))
        check(is_minimal(minimized.to_puzzle()), "Standalone minimalization is not minimal")
        cold.append({"id": record.id, "clues": record.clues,
                     "quick_seconds": quick_seconds, "quick": rating_summary(quick),
                     "deep_seconds": deep_seconds, "deep": rating_summary(deep),
                     "minimalization_seconds": minimal_seconds,
                     "minimalization_start_clues": partial.clue_count,
                     "minimalization_end_clues": minimized.clue_count})
        print(f"cold {record.id}: quick={quick_seconds:.3f}s deep={deep_seconds:.3f}s "
              f"minimalize={minimal_seconds:.3f}s", flush=True)

    # Preserve incidental preliminary Extreme discoveries even if the requested
    # batch target rejected them. Ordinary runs usually leave this list empty.
    discoveries = {record.puzzle: record for result in (smoke, batch, narrow)
                   for record in (*result.puzzles, *result.preliminary_candidates)
                   if record.difficulty in ("Extreme", "Ultra Extreme")}
    if discoveries:
        export_puzzles(discoveries.values(), args.database.with_name("phase5_extreme_candidates.json"),
                       generated_at=timestamp)
    report = {
        "timestamp_utc": timestamp, "generator_version": GENERATOR_VERSION,
        "command": "python -m generator.tests.profile_phase5 " + " ".join(sys.argv[1:]),
        "environment": {"python": sys.version, "executable": sys.executable,
                        "platform": platform.platform(), "processor": platform.processor()},
        "baseline": {"tests": 184, "result": "OK", "suite_seconds": 54.853,
                     "wall_seconds": 55.184, "python": "3.11.9"},
        "notes": [
            "Single-process wall times, diagnostic only; no concurrent project CPU-heavy jobs.",
            "No difficulty is inferred from clues; production Phase 4 analysis is used without mocks.",
            "Class counts describe accepted records in this tiny deterministic sample only.",
            "Default-range and broad-range runs overlap seeds; do not pool them as independent samples.",
            "Pipeline Deep is conditional. Cold Deep diagnostics deliberately analyze two records separately.",
            "Minimality verification and cold diagnostic timings are outside generation attempt timings.",
            "Extreme findings are preliminary bounded-logic candidates, not final minimax certification.",
            "Dates and timings vary on rerun; seed/config/version determine puzzle results."],
        "smoke": smoke_report, "batch": batch_report, "default_range": narrow_report,
        "cold_stage_diagnostics": cold, "extreme_discoveries": len(discoveries),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Profile: {args.output}; database: {args.database}", flush=True)


if __name__ == "__main__":
    main()
