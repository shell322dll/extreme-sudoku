"""Validated, atomic schema-v1 export independent of the command line."""

import json
import math
import os
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
import re
import tempfile

from .clue_generator import is_minimal
from .models import DIFFICULTIES, GENERATOR_VERSION, GeneratedPuzzle
from .solver.exact_solver import count_solutions
from .sudoku.grid import is_complete


class ExportValidationError(ValueError):
    """The entire export is rejected; an existing destination is unchanged."""


def _number(value, field):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ExportValidationError(f"{field} must be a finite nonnegative number")


def _integer(value, field):
    if type(value) is not int or value < 0:
        raise ExportValidationError(f"{field} must be a nonnegative integer")


def validate_puzzle(record: Mapping) -> None:
    """Validate a serialized puzzle, independently checking exact uniqueness.

    Minimality is rechecked when claimed. Optional unknown fields are permitted
    by the frontend contract; standard numeric metadata is checked explicitly.
    """
    if not isinstance(record, Mapping):
        raise ExportValidationError("puzzle must be an object")
    identifier = record.get("id")
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier):
        raise ExportValidationError("id must be a nonempty identifier using letters, digits, '.', '_' or '-'")
    for field, alphabet in (("puzzle", "0123456789"), ("solution", "123456789")):
        value = record.get(field)
        if not isinstance(value, str) or len(value) != 81 or any(c not in alphabet for c in value):
            raise ExportValidationError(f"{identifier}: {field} must contain 81 ASCII digits from {alphabet}")
    puzzle, solution = record["puzzle"], record["solution"]
    if not is_complete([int(c) for c in solution]):
        raise ExportValidationError(f"{identifier}: solution is not a valid complete Sudoku")
    clues = record.get("clues")
    if type(clues) is not int or clues != sum(c != "0" for c in puzzle):
        raise ExportValidationError(f"{identifier}: clues does not match puzzle")
    if any(given != "0" and given != answer for given, answer in zip(puzzle, solution)):
        raise ExportValidationError(f"{identifier}: given clues do not match solution")
    if record.get("unique") is not True:
        raise ExportValidationError(f"{identifier}: unique must be true")
    if record.get("difficulty") not in DIFFICULTIES:
        raise ExportValidationError(f"{identifier}: unsupported difficulty")
    if "rating" in record:
        _number(record["rating"], "rating")
    if "minimal" in record and type(record["minimal"]) is not bool:
        raise ExportValidationError(f"{identifier}: minimal must be boolean")
    if "hardestTechnique" in record and (not isinstance(record["hardestTechnique"], str) or not record["hardestTechnique"]):
        raise ExportValidationError(f"{identifier}: hardestTechnique must be a nonempty string")
    if "difficultyData" in record:
        metadata = record["difficultyData"]
        if not isinstance(metadata, Mapping):
            raise ExportValidationError(f"{identifier}: difficultyData must be an object")
        for field in ("hardestRating", "totalScore"):
            if field in metadata:
                _number(metadata[field], f"difficultyData.{field}")
        for field in ("advancedSteps", "trueBottlenecks", "longestChain"):
            if field in metadata:
                _integer(metadata[field], f"difficultyData.{field}")
    if "techniques" in record:
        counts = record["techniques"]
        if not isinstance(counts, Mapping) or any(
            not isinstance(name, str) or not name or type(count) is not int or count <= 0
            for name, count in counts.items()
        ):
            raise ExportValidationError(f"{identifier}: techniques must contain positive integer counts")
    board = [int(c) for c in puzzle]
    if count_solutions(board, limit=2) != 1:
        raise ExportValidationError(f"{identifier}: puzzle does not have exactly one solution")
    if record.get("minimal") and not is_minimal(board):
        raise ExportValidationError(f"{identifier}: minimal=true is not justified")


def _timestamp(value):
    if not isinstance(value, str):
        raise ExportValidationError("generatedAt must be an ISO 8601 UTC string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExportValidationError("generatedAt must be an ISO 8601 UTC string") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ExportValidationError("generatedAt must use UTC")


def validate_database(database: Mapping) -> None:
    """Validate the root contract, unique IDs and exact duplicate suppression."""
    if not isinstance(database, Mapping):
        raise ExportValidationError("database must be an object")
    if type(database.get("schemaVersion")) is not int or database["schemaVersion"] != 1:
        raise ExportValidationError("schemaVersion must be 1")
    _timestamp(database.get("generatedAt"))
    version = database.get("generatorVersion")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
        raise ExportValidationError("generatorVersion must be a semantic version")
    puzzles = database.get("puzzles")
    if not isinstance(puzzles, list):
        raise ExportValidationError("puzzles must be an array")
    ids, grids = set(), set()
    for record in puzzles:
        validate_puzzle(record)
        if record["id"] in ids:
            raise ExportValidationError(f"duplicate id: {record['id']}")
        if record["puzzle"] in grids:
            raise ExportValidationError(f"duplicate puzzle: {record['id']}")
        ids.add(record["id"])
        grids.add(record["puzzle"])
    try:
        json.dumps(database, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ExportValidationError(f"database is not valid JSON: {exc}") from exc


def puzzle_record(puzzle: GeneratedPuzzle) -> dict:
    """Translate core results without presenting observed techniques as mandatory."""
    difficulty = puzzle.difficulty_result
    human = puzzle.human_result
    if (not difficulty.solved or difficulty.invalid or difficulty.used_backtracking
            or difficulty.guesses or not human.solved or human.invalid
            or human.used_backtracking or human.guesses):
        raise ExportValidationError(f"{puzzle.id}: accepted puzzle needs a valid human solution")
    if puzzle.difficulty != difficulty.difficulty_class or puzzle.rating != difficulty.rating:
        raise ExportValidationError(f"{puzzle.id}: result does not match difficulty analysis")
    metadata = {}
    record = {
        "id": puzzle.id,
        "puzzle": puzzle.puzzle,
        "solution": puzzle.solution,
        "clues": puzzle.clues,
        "difficulty": puzzle.difficulty,
        "rating": puzzle.rating,
        "unique": puzzle.unique,
        "minimal": puzzle.minimal,
    }
    if difficulty.mode == "deep" and difficulty.required_level_verified:
        if difficulty.hardest_required_technique is not None:
            record["hardestTechnique"] = difficulty.hardest_required_technique
        if difficulty.hardest_required_rating is not None:
            metadata["hardestRating"] = difficulty.hardest_required_rating
    metadata.update({
        "totalScore": difficulty.total_score,
        "advancedSteps": difficulty.advanced_steps,
        "trueBottlenecks": difficulty.true_bottleneck_count,
        "longestChain": difficulty.longest_chain,
    })
    record["difficultyData"] = metadata
    record["techniques"] = {name: count for name, count in sorted(human.technique_counts.items()) if count}
    record["techniquesUsed"] = list(record["techniques"])
    record["generatorSeed"] = puzzle.seed
    record["ratingMetadata"] = {
        "mode": difficulty.mode,
        "scope": difficulty.scope,
        "preliminary": difficulty.preliminary,
        "requiredLevelVerified": difficulty.required_level_verified,
        "observedHardestTechnique": difficulty.hardest_technique,
        "observedHardestRating": difficulty.hardest_rating,
    }
    record["generationMetadata"] = {
        "attemptSeed": puzzle.attempt_seed,
        "attempt": puzzle.attempts,
    }
    return record


def build_database(puzzles: Iterable[GeneratedPuzzle], *, generated_at: str | None = None) -> dict:
    """Build and validate schema 1; a supplied timestamp enables byte stability."""
    records = [puzzle_record(puzzle) for puzzle in puzzles]
    database = {
        "schemaVersion": 1,
        "generatedAt": generated_at if generated_at is not None else datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "generatorVersion": GENERATOR_VERSION,
        "puzzles": records,
    }
    validate_database(database)
    records.sort(key=lambda p: (DIFFICULTIES.index(p["difficulty"]), -p["rating"], p["clues"], p["id"]))
    counts = Counter(record["difficulty"] for record in records)
    database["stats"] = {
        "total": len(records),
        "byDifficulty": {name: counts[name] for name in DIFFICULTIES if counts[name]},
    }
    return database


def export_puzzles(puzzles: Iterable[GeneratedPuzzle], path="data/puzzles.json", *, generated_at: str | None = None) -> dict:
    """Validate every puzzle, then atomically replace the destination in UTF-8.

    On validation or write failure the existing file is retained. This function
    deliberately fails the entire export instead of silently dropping bad data.
    """
    database = build_database(puzzles, generated_at=generated_at)
    text = json.dumps(database, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=destination.parent,
                                         prefix=f".{destination.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return database
