"""Real bounded Phase 6 experiment, with fresh independent final diagnostics.

Run serially, outside the unittest suite. Default artifacts stay under docs/.
Times are measurements, never correctness thresholds. No fixtures are seeded.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
from statistics import mean, median
import sys
from time import perf_counter

from generator.rating.difficulty import DifficultyAnalyzer
from generator.tests.profile_phase5 import independently_validate, check


ROOT = Path(__file__).resolve().parents[2]


def rating_summary(result):
    names = ("mode", "solved", "invalid", "difficulty_class", "rating",
             "hardest_technique", "hardest_rating", "hardest_required_technique",
             "hardest_required_rating", "required_level_verified", "total_score",
             "true_bottleneck_count", "advanced_steps", "extreme_steps",
             "chain_complexity", "longest_chain", "als_steps", "forcing_steps",
             "is_extreme_candidate", "is_ultra_extreme_candidate", "profile_statuses",
             "used_backtracking", "guesses", "scope")
    return {name: getattr(result, name) for name in names}


def fresh_diagnostic(individual, config):
    if individual is None:
        return None
    start = perf_counter()
    rating = DifficultyAnalyzer(config.difficulty_config).deep(
        individual.to_puzzle(), check_unique=True)
    elapsed = perf_counter() - start
    check(rating.solved and rating.unique is True and not rating.invalid,
          "Best candidate failed independent fresh Deep analysis")
    check(rating.required_level_verified and not rating.used_backtracking and not rating.guesses,
          "Best candidate has no verified bounded human rating")
    return {"puzzle": "".join(map(str, individual.to_puzzle())),
            "clues": individual.clue_count, "fitness": individual.fitness,
            "origin_generation": individual.generation, "origin_operator": individual.operator,
            "quick_rating": rating_summary(individual.quick_rating) if individual.quick_rating else None,
            "fresh_deep_seconds": elapsed, "rating": rating_summary(rating)}


def comparison(initial, final):
    if initial is None or final is None:
        return {"comparable": False, "reason": "No verified best available at one endpoint"}
    fields = ("hardest_required_rating", "true_bottleneck_count", "total_score",
              "advanced_steps", "longest_chain")
    changes = {name: final["rating"][name] - initial["rating"][name] for name in fields}
    changes["clues"] = final["clues"] - initial["clues"]
    return {"comparable": True, "same_puzzle": initial["puzzle"] == final["puzzle"],
            "deltas": changes,
            "final_from_initial_population": final["origin_generation"] == 0,
            "final_origin_operator": final["origin_operator"],
            "note": "Both endpoints use fresh Deep with the identical configured detector budgets."}


def performance_summary(result, evolution_seconds):
    """Measured inclusive stages, with explicit cache denominators."""
    generation_times = [s.generation_seconds for s in result.stats if s.generation > 0]
    cache_rates = {}
    for name in ("uniqueness", "quick", "deep", "fitness"):
        hits = result.counters.get(name + "_cache_hits", 0)
        misses = result.counters.get(name + "_cache_misses")
        lookups = result.counters.get(name + "_cache_lookups")
        if misses is None and lookups is not None:
            misses = lookups - hits
        if misses is None and name in ("quick", "deep"):
            misses = result.stage_calls.get(name + "_rating", 0)
        cache_rates[name] = {
            "hits": hits, "misses": misses,
            "hit_rate": hits / (hits + misses) if misses is not None and hits + misses else None,
        }
    return {
        "completed_generations": len(generation_times),
        "seconds_per_generation": {
            "mean": mean(generation_times) if generation_times else None,
            "median": median(generation_times) if generation_times else None,
            "minimum": min(generation_times, default=None),
            "maximum": max(generation_times, default=None),
            "values": generation_times,
        },
        "stage_fraction_of_evolution_wall": {
            name: seconds / evolution_seconds if evolution_seconds else 0
            for name, seconds in result.stage_seconds.items()
        },
        "cache_rates": cache_rates,
        "note": "Stages are inclusive and overlap. Local search includes its rating and uniqueness calls; fractions must not be summed as exclusive CPU shares. Missing cache denominators are null, not measured zero misses.",
    }


def main():
    from generator.evolution.config import EvolutionConfig
    from generator.evolution.engine import evolve
    from generator.evolution.io import export_evolution, save_snapshot, individual_summary, target_match

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--population", type=int, default=200)
    parser.add_argument("--generations", type=int, default=20)
    parser.add_argument("--offspring", type=int, default=32)
    parser.add_argument("--max-seconds", type=float, default=600)
    parser.add_argument("--mode", default="balanced")
    parser.add_argument("--min-clues", type=int, default=17)
    parser.add_argument("--max-clues", type=int, default=21)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/PHASE6_PROFILE.json")
    parser.add_argument("--database", type=Path, default=ROOT / "docs/PHASE6_CANDIDATES.json")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "docs/PHASE6_SNAPSHOT.json")
    args = parser.parse_args()
    elite_size = min(3, max(1, args.population // 10))
    config = EvolutionConfig.for_mode(args.mode, seed=args.seed, population_size=args.population,
                             max_generations=args.generations, max_seconds=args.max_seconds,
                             min_clues=args.min_clues, max_clues=args.max_clues,
                             offspring_count=args.offspring, elite_size=elite_size,
                             random_injection_count=min(3, args.population - elite_size))
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    def progress(stats, best):
        print(json.dumps({"generation": stats.generation,
                          "best": individual_summary(best) if best else None,
                          "stats": stats.to_dict()}, ensure_ascii=False), flush=True)

    start = perf_counter()
    result = evolve(config, progress=progress)
    evolution_seconds = perf_counter() - start
    save_snapshot(result, args.snapshot)
    exported, validation = [], []
    if result.archive:
        document = export_evolution(result, args.database, limit=10, generated_at=timestamp)
        parsed = json.loads(args.database.read_text(encoding="utf-8"))
        check(parsed == document, "Evolution export failed JSON round-trip")
        validation = independently_validate(parsed)
        exported = parsed["puzzles"]
    initial = fresh_diagnostic(result.initial_best, config)
    final = fresh_diagnostic(result.best, config)
    all_records = tuple({individual.key: individual for individual in
                         (*result.population, *result.archive,
                          *((result.best,) if result.best is not None else ()))}.values())
    rated = [i.deep_rating for i in all_records if i.deep_rating is not None]
    extreme_config = EvolutionConfig.for_mode("extreme", min_clues=17, max_clues=21)
    monster_config = EvolutionConfig.for_mode("monster", min_clues=17, max_clues=21)
    timed_total = sum(result.stage_seconds.values())
    report = {
        "timestamp_utc": timestamp,
        "command": "python -m generator.tests.profile_phase6 " + " ".join(sys.argv[1:]),
        "environment": {"python": sys.version, "executable": sys.executable,
                        "platform": platform.platform(), "processor": platform.processor()},
        "seed": result.seed, "config": config.to_dict(), "generations": result.generations,
        "evolution_seconds": evolution_seconds, "timed_out": result.timed_out,
        "stop_reason": result.stop_reason, "initial": initial, "final": final,
        "comparison": comparison(initial, final),
        "initial_deep_budget": {"fraction": config.deep_fraction,
                                "maximum_candidates": config.deep_candidates_per_generation},
        "stage_seconds": result.stage_seconds, "stage_calls": result.stage_calls,
        "stage_fraction_of_sum": {name: seconds / timed_total if timed_total else 0
                                  for name, seconds in result.stage_seconds.items()},
        "counters": result.counters, "generations_stats": [s.to_dict() for s in result.stats],
        "performance": performance_summary(result, evolution_seconds),
        "population_count": len(result.population), "archive_count": len(result.archive),
        "population": [individual_summary(i) for i in result.population],
        "archive": [individual_summary(i) for i in result.archive],
        "minimum_clues": min((i.clue_count for i in all_records), default=None),
        "minimum_deep_rated_clues": min((i.clue_count for i in all_records
                                        if i.status == "DEEP_RATED"), default=None),
        "maximum_required_rating": max((r.hardest_required_rating or 0 for r in rated), default=0),
        "maximum_genuine_bottlenecks": max((r.true_bottleneck_count for r in rated), default=0),
        "maximum_longest_chain": max((r.longest_chain for r in rated), default=0),
        "extreme_candidates": sum(r.is_extreme_candidate for r in rated),
        "ultra_candidates": sum(r.is_ultra_extreme_candidate for r in rated),
        "configured_target_matches": sum(target_match(i, config) for i in all_records),
        "extreme_17_to_21_target_matches": sum(target_match(i, extreme_config) for i in all_records),
        "monster_17_to_21_target_matches": sum(target_match(i, monster_config) for i in all_records),
        "exported_ids": [r["id"] for r in exported], "independent_validation": validation,
        "notes": [
            "Real search starts from newly generated solutions and masks; no stored difficult fixtures.",
            "Summary extrema and target counts deduplicate overlapping population/archive by solution and mask.",
            "Fresh Deep endpoint diagnostics and export validation are outside evolution time budget.",
            "Initial best is the best of initially Deep-rated candidates, not a Deep ranking of every initial seed; a final generation-zero winner can reflect delayed analysis instead of evolutionary improvement.",
            "Budget checked between bounded actions; an in-flight solver call can exceed wall budget.",
            "Ratings are preliminary bounded human evidence, never Phase 7 minimax certification.",
            "Stage fractions use the sum of measured stages, not exclusive CPU shares: seed_construction and minimality include uniqueness; repair includes its exact alternative-solution calls.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Profile: {args.output}; candidates: {args.database}; snapshot: {args.snapshot}", flush=True)


if __name__ == "__main__":
    main()
