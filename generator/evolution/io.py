"""Evolution diagnostics and conversion to the existing schema-v1 exporter."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import tempfile

from ..construction import check_minimal, validate_candidate
from ..export import export_puzzles
from ..models import GeneratedPuzzle
from ..rating.profiles import solve_with_max_rating


def target_match(individual, config):
    if individual is None or individual.status != "DEEP_RATED" or individual.unique is not True:
        return False
    result, target = individual.deep_rating, config.target
    return bool(result is not None and result.solved and result.required_level_verified
        and config.min_clues <= individual.clue_count <= config.max_clues
        and result.hardest_required_rating is not None
        and result.hardest_required_rating >= target.required_rating
        and result.true_bottleneck_count >= target.bottlenecks
        and result.advanced_steps >= target.advanced_steps
        and result.longest_chain >= target.longest_chain
        and (not target.require_minimal or individual.minimal is True)
        and (not target.reject_intermediate or result.profile_statuses.get("Intermediate") == "STUCK"))


def individual_summary(individual):
    if individual is None:
        return None
    result = individual.deep_rating or individual.quick_rating
    return {
        "puzzle": "".join(map(str, individual.to_puzzle())),
        "solution": "".join(map(str, individual.solution)),
        "clue_mask": str(individual.clue_mask),
        "clues": individual.clue_count, "unique": individual.unique,
        "minimal": individual.minimal, "status": individual.status,
        "fitness": individual.fitness if isfinite(individual.fitness) else None,
        "fitness_vector": list(individual.fitness_vector),
        "generation": individual.generation, "operator": individual.operator,
        "rating": None if result is None else {
            "mode": result.mode, "solved": result.solved,
            "difficulty": result.difficulty_class,
            "required_rating": result.hardest_required_rating,
            "required_technique": result.hardest_required_technique,
            "required_level_verified": result.required_level_verified,
            "observed_rating": result.hardest_rating,
            "total_score": result.total_score,
            "bottlenecks": result.true_bottleneck_count,
            "advanced_steps": result.advanced_steps,
            "extreme_steps": result.extreme_steps,
            "longest_chain": result.longest_chain,
            "chain_complexity": result.chain_complexity,
            "als_steps": result.als_steps, "forcing_steps": result.forcing_steps,
            "profile_statuses": dict(result.profile_statuses),
            "preliminary": True, "scope": result.scope,
        },
    }


def to_generated_puzzle(individual, *, seed, config):
    """Reconstruct the identical required-threshold human path before export.

    Fresh exact uniqueness and minimality checks are validation, not Phase 7
    certification. No solution values are supplied to the human solver.
    """
    rating = individual.deep_rating
    if (individual.status != "DEEP_RATED" or rating is None or not rating.solved
            or not rating.required_level_verified or rating.hardest_required_rating is None):
        raise ValueError("evolution export requires a verified Deep human solution")
    if not validate_candidate(individual.candidate):
        raise ValueError("evolution export requires a unique solution")
    human = solve_with_max_rating(individual.to_puzzle(), rating.hardest_required_rating,
                                 config=config.difficulty_config)
    if (not human.solved or human.invalid or human.used_backtracking or human.guesses
            or tuple(human.grid) != individual.solution):
        raise ValueError("human path failed independent reconstruction")
    minimal = check_minimal(individual.candidate)
    rating = deepcopy(rating)
    rating.minimal, rating.preliminary = minimal, True
    puzzle = "".join(map(str, individual.to_puzzle()))
    return GeneratedPuzzle(id="puzzle-" + sha256(puzzle.encode("ascii")).hexdigest()[:20],
        puzzle=puzzle, solution="".join(map(str, individual.solution)),
        clues=individual.clue_count, unique=True, minimal=minimal,
        difficulty=rating.difficulty_class, rating=rating.rating,
        difficulty_result=rating, human_result=human, seed=seed,
        attempt_seed=seed, attempts=individual.generation, clue_mask=individual.clue_mask)


def export_evolution(result, path, *, limit=10, targets_only=False, generated_at=None):
    """Export bounded candidates, including exploratory clue counts by default.

    targets_only=True restricts to the configured clue range and target profile.
    An empty selection leaves an existing destination untouched.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    records = (*result.archive, *((result.best,) if result.best is not None else ()))
    candidates = sorted({p.key: p for p in records}.values(), key=lambda p: (-p.fitness, p.key))
    if targets_only:
        candidates = [p for p in candidates if target_match(p, result.config)]
    if not candidates:
        raise ValueError("no verified evolution candidates available for export")
    records = [to_generated_puzzle(p, seed=result.seed, config=result.config) for p in candidates[:limit]]
    return export_puzzles(records, path, generated_at=generated_at)


def save_snapshot(result, path):
    """Save minimum Phase 6 checkpoint: archive/config/seed/generation/stats.

    This is an inspectable snapshot, not a resumable RNG/population checkpoint.
    """
    document = {
        "snapshotVersion": 1, "phase": 6, "resumable": False,
        "seed": result.seed, "generation": result.generations,
        "config": result.config.to_dict(), "stop_reason": result.stop_reason,
        "timed_out": result.timed_out, "elapsed_seconds": result.elapsed_seconds,
        "initial_best": individual_summary(result.initial_best),
        "best": individual_summary(result.best),
        "archive": [individual_summary(p) for p in result.archive],
        "stats": [asdict(s) for s in result.stats],
        "stage_seconds": result.stage_seconds, "stage_calls": result.stage_calls,
        "counters": result.counters,
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(document, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return document
