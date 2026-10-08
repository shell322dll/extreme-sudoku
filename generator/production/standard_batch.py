"""Research-only standard difficulty branch of production-batch."""
from itertools import combinations
import json
from pathlib import Path
from time import perf_counter

from ..certification.io import read_json
from ..config import GeneratorConfig
from ..pipeline import PuzzleGenerator
from .archive import archive_lock, atomic_write_text, utc_now
from .diversity import DiversityIndex, mask_distance, technique_similarity
from .verification import verify_standard


def run_standard_batch(options, *, log=None, clock=perf_counter):
    options.validate()
    if options.resume or options.reuse_archive or options.bands or options.retry_timeouts:
        raise ValueError("Standard batches use fresh seeded generation; resume/reuse/bands/retries are Extreme options")
    log = log or print
    started = clock()
    run_id = options.run_id or utc_now().replace("-", "").replace(":", "") + "-" + options.difficulty.lower()
    run_dir = Path(options.run_dir or Path("data/research/phase10/runs") / run_id)
    production = read_json(options.production) if options.production is not None else {"puzzles": []}
    if run_dir.exists() and (run_dir / "batch_report.json").exists():
        raise ValueError("Run already exists; use a new --run-dir to preserve its report")
    index = DiversityIndex()
    for record in production["puzzles"]:
        index.add(record, "production")
    selected, rejected, seed_runs = [], [], []
    with archive_lock(run_dir / "standard-batch", "standard-production-batch"):
        pool = []
        for seed in options.seeds:
            remaining = None if options.runtime_budget is None else options.runtime_budget - (clock() - started)
            if remaining is not None and remaining <= 0:
                break
            limits = [v for v in (remaining, options.generation_seconds) if v is not None]
            config = GeneratorConfig(seed=seed, min_clues=options.min_clues, max_clues=options.max_clues,
                target_difficulty=options.difficulty, require_minimal=options.minimal,
                max_attempts=options.max_attempts, rating_mode="quick_then_deep",
                timeout_seconds=min(limits) if limits else None)
            generated = PuzzleGenerator(config).generate_many(options.per_seed_count)
            seed_runs.append({"seed": seed, **generated.stats.to_dict()})
            for candidate in generated.puzzles:
                try:
                    record = verify_standard(candidate.puzzle, candidate.solution, options.difficulty,
                                             puzzle_id=candidate.id)
                except ValueError as exc:
                    rejected.append({"id": candidate.id, "reason": "VERIFICATION_FAILED", "detail": str(exc)})
                    continue
                record.update({"generatorSeed": seed,
                               "generationMetadata": {"attemptSeed": candidate.attempt_seed,
                                                      "attempt": candidate.attempts}})
                pool.append(record)
            log(f"{options.difficulty} seed {seed}: {len(generated.puzzles)} generated / {generated.stats.attempts} attempts")
        # Pick different required ratings, clue counts, and profile vectors first.
        # Similarity is a preference, never a difficulty classifier.
        while pool and len(selected) < options.target_new:
            def preference(record):
                levels = {p["verification"]["requiredRating"] for p in selected}
                counts = {p["clues"] for p in selected}
                similarity = max((technique_similarity(record["techniques"], p["techniques"])
                                  for p in selected), default=0)
                return (record["verification"]["requiredRating"] in levels,
                        record["clues"] in counts, similarity, record["id"])
            pool.sort(key=preference)
            record = pool.pop(0)
            duplicate = index.check(record)
            if duplicate:
                rejected.append({"id": record["id"], "reason": duplicate[0].value, "detail": duplicate[1]})
                continue
            record["diversityWarnings"] = index.technique_warnings(record)
            selected.append(record)
            index.add(record, "selected")
        attempts = sum(item["attempts"] for item in seed_runs)
        report = {"kind": "standard-batch-report", "runId": run_id, "runDir": str(run_dir),
                  "archive": None, "difficulty": options.difficulty, "command": options.command,
                  "targetNew": options.target_new, "complete": len(selected) == options.target_new,
                  "seeds": seed_runs, "attempts": attempts,
                  "elapsedSeconds": clock() - started,
                  "generationYield": len(selected) / attempts if attempts else 0,
                  "selected": selected, "verifiedUnselected": pool, "rejected": rejected,
                  "diversity": {"uniqueIds": len({p["id"] for p in selected}),
                      "uniquePuzzles": len({p["puzzle"] for p in selected}),
                      "uniqueSolutions": len({p["solution"] for p in selected}),
                      "uniqueClueMasks": len({tuple(i for i, n in enumerate(p["puzzle"]) if n != "0") for p in selected}),
                      "minimumClueMaskDistance": min((mask_distance(a["puzzle"], b["puzzle"])
                                                      for a, b in combinations(selected, 2)), default=None)}}
        atomic_write_text(run_dir / "batch_report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report
