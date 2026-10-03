"""Generate rated Sudoku batches or run the original Phase 1 seed demo."""

import argparse
import json
from pathlib import Path
import sys

from .clue_generator import is_minimal, minimize_puzzle
from .config import GeneratorConfig
from .export import export_puzzles
from .models import DIFFICULTIES
from .pipeline import generate_many
from .solution_generator import generate_solution
from .solver.exact_solver import has_unique_solution


def _demo(argv):
    parser = argparse.ArgumentParser(description="Phase 1 seed puzzle demo; use 'generate' for rated JSON export")
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args(argv)
    solution = generate_solution(args.seed)
    puzzle = minimize_puzzle(solution, args.seed)
    print('Phase 1 seed puzzle (difficulty not certified)')
    print('Puzzle:  ', ''.join(map(str, puzzle)))
    print('Solution:', ''.join(map(str, solution)))
    print('Clues:', sum(bool(n) for n in puzzle))
    print('Unique:', has_unique_solution(puzzle))
    print('Minimal:', is_minimal(puzzle))
    return 0


def _generate(argv):
    parser = argparse.ArgumentParser(prog="python -m generator generate", description="Generate validated, human-rated Sudoku")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--difficulty", choices=DIFFICULTIES)
    parser.add_argument("--min-clues", type=int, default=17)
    parser.add_argument("--max-clues", type=int, default=23)
    parser.add_argument("--minimal", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--rating", choices=("quick", "deep", "quick_then_deep"), default="quick_then_deep")
    parser.add_argument("--max-attempts", type=int, default=100)
    parser.add_argument("--timeout", type=float, dest="timeout_seconds")
    parser.add_argument("--output", type=Path, default=Path("data/puzzles.json"))
    args = parser.parse_args(argv)
    best = None

    def progress(stats, latest):
        nonlocal best
        if latest is not None and (best is None or (DIFFICULTIES.index(latest.difficulty), latest.rating) > (DIFFICULTIES.index(best.difficulty), best.rating)):
            best = latest
        if latest is not None or stats.attempts % 10 == 0:
            label = f"{best.difficulty} / rating {best.rating:.3f}" if best is not None else "none rated"
            print(f"Attempts: {stats.attempts} | Accepted: {stats.accepted}/{args.count} | Best candidate: {label}", file=sys.stderr, flush=True)

    try:
        config = GeneratorConfig(seed=args.seed, min_clues=args.min_clues, max_clues=args.max_clues,
                                 target_difficulty=args.difficulty, require_minimal=args.minimal,
                                 max_attempts=args.max_attempts, rating_mode=args.rating,
                                 timeout_seconds=args.timeout_seconds)
        result = generate_many(args.count, config, progress=progress)
        if result.puzzles:
            export_puzzles(result.puzzles, args.output)
            print(f"Exported {len(result.puzzles)} puzzles: {args.output}")
            print("ID | clues | difficulty | rating | minimal | hardest observed technique")
            for puzzle in result.puzzles:
                print(f"{puzzle.id} | {puzzle.clues} | {puzzle.difficulty} | {puzzle.rating:.3f} | {puzzle.minimal} | {puzzle.difficulty_result.hardest_technique or '-'}")
        if result.preliminary_candidates:
            archive = args.output.with_name(args.output.stem + "_preliminary" + args.output.suffix)
            export_puzzles(result.preliminary_candidates, archive)
            print(f"Preliminary Extreme candidates: {archive}")
        print(f"Seed: {result.seed} | Found: {len(result.puzzles)}/{result.requested} | Attempts: {result.stats.attempts}", file=sys.stderr)
        print("Generation stats: " + json.dumps(result.stats.to_dict(), sort_keys=True), file=sys.stderr)
        if not result.complete:
            print("Generation incomplete: timeout or max-attempts reached; only accepted puzzles were exported." if result.puzzles else
                  "Generation incomplete: no accepted puzzles; output file was not changed.", file=sys.stderr)
            return 1
        return 0
    except (ValueError, OSError) as exc:
        print(f"Generation failed: {exc}", file=sys.stderr)
        return 2


def _evolve(argv):
    from .evolution import EvolutionConfig, evolve, export_evolution, save_snapshot, target_match

    parser = argparse.ArgumentParser(prog="python -m generator evolve",
        description="Search preliminary Sudoku candidates using bounded human evidence")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--population", type=int, default=32)
    parser.add_argument("--generations", type=int, default=30)
    parser.add_argument("--mode", choices=("balanced", "extreme", "monster", "min_clues"), default="balanced")
    parser.add_argument("--min-clues", type=int, default=17)
    parser.add_argument("--max-clues", type=int, default=21)
    parser.add_argument("--search-max-clues", type=int, default=32)
    parser.add_argument("--max-seconds", type=float)
    parser.add_argument("--output", type=Path, default=Path("data/evolution_candidates.json"))
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--export-limit", type=int, default=10)
    parser.add_argument("--targets-only", action="store_true")
    args = parser.parse_args(argv)

    def progress(stats, best):
        detail = "no verified Deep candidate yet"
        if best is not None:
            r = best.deep_rating
            detail = (f"clues {best.clue_count} | {r.difficulty_class} | required {r.hardest_required_rating:g}"
                      f" | bottlenecks {r.true_bottleneck_count} | advanced {r.advanced_steps}"
                      f" | longest chain {r.longest_chain} | target match {target_match(best, config)}")
        print(f"Generation {stats.generation} | {detail} | diversity {stats.diversity:.2f}"
              f" | population {stats.unique_population_size}", file=sys.stderr, flush=True)

    try:
        if args.export_limit < 1:
            raise ValueError("export limit must be positive")
        if args.population < 2:
            raise ValueError("population must be at least 2")
        snapshot = args.snapshot or args.output.with_name(args.output.stem + "_snapshot.json")
        if snapshot.resolve() == args.output.resolve():
            raise ValueError("snapshot and puzzle output must use different paths")
        config = EvolutionConfig.for_mode(args.mode, seed=args.seed, population_size=args.population,
            elite_size=max(1, args.population // 10), offspring_count=args.population,
            random_injection_count=max(1, args.population // 10), max_generations=args.generations,
            min_clues=args.min_clues, max_clues=args.max_clues, search_max_clues=args.search_max_clues,
            max_seconds=args.max_seconds)
        print(f"Target clues {config.min_clues}-{config.max_clues}; exploration allows up to "
              f"{config.search_max_clues}. Outputs are preliminary candidates.", file=sys.stderr)
        result = evolve(config, progress=progress)
        save_snapshot(result, snapshot)
        records = (*result.archive, *((result.best,) if result.best is not None else ()))
        selected = [p for p in records if not args.targets_only or target_match(p, config)]
        if selected:
            database = export_evolution(result, args.output, limit=args.export_limit, targets_only=args.targets_only)
            print(f"Exported {len(database['puzzles'])} preliminary candidates: {args.output}")
        else:
            print("No matching Deep-rated candidates; puzzle output was not changed.", file=sys.stderr)
        print(f"Seed {result.seed} | generations {result.generations} | stop {result.stop_reason}"
              f" | snapshot {snapshot}", file=sys.stderr)
        print("Evolution stages: " + json.dumps(result.stage_seconds, sort_keys=True), file=sys.stderr)
        return 0 if selected else 1
    except (ValueError, OSError) as exc:
        print(f"Evolution failed: {exc}", file=sys.stderr)
        return 2


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "certify":
        from .certification.cli import main as certify_main
        return certify_main(argv[1:])
    if argv and argv[0] == "evolve":
        return _evolve(argv[1:])
    if argv and argv[0] == "production-batch":
        from .production.cli import batch_main
        return batch_main(argv[1:])
    if argv and argv[0] == "production-report":
        from .production.cli import report_main
        return report_main(argv[1:])
    if argv and argv[0] == "production-merge":
        from .production.cli import merge_main
        return merge_main(argv[1:])
    return _generate(argv[1:]) if argv and argv[0] == "generate" else _demo(argv)


if __name__ == '__main__':
    raise SystemExit(main())
