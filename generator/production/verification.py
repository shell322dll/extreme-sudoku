"""Standard production verification, separate from immutable Extreme certification.

The required rating is the lowest successful deterministic threshold in the
existing DifficultyAnalyzer. It is not a proof about every logical path.
"""
from collections import Counter
from dataclasses import asdict
from itertools import islice
import json
from math import isfinite, nextafter

from ..certification.io import (_canonical_json, validate_production_database as
                                validate_certified_database)
from ..certification.proofs import validate_path
from ..export import ExportValidationError, validate_database, validate_puzzle
from ..rating.config import DifficultyConfig
from ..rating.difficulty import DifficultyAnalyzer
from ..rating.profiles import solve_with_max_rating
from .archive import content_id

STANDARD_DIFFICULTIES = ("Easy", "Medium", "Hard", "Expert")


def _metadata_differences(actual, expected, path="$"):
    """Yield leaf diagnostics; callers cap output rather than dumping proofs."""
    if _canonical_json(actual) == _canonical_json(expected):
        return
    if isinstance(actual, dict) and isinstance(expected, dict):
        if actual.keys() != expected.keys():
            yield f"{path}: saved keys {sorted(actual)}; fresh keys {sorted(expected)}"
            return
        for key in expected:
            yield from _metadata_differences(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            yield f"{path}: saved length {len(actual)}; fresh length {len(expected)}"
            return
        for index, (saved, fresh) in enumerate(zip(actual, expected)):
            yield from _metadata_differences(saved, fresh, f"{path}[{index}]")
    else:
        yield f"{path}: saved {repr(actual)[:160]}; fresh {repr(expected)[:160]}"


def _first_metadata_difference(actual, expected, path="$"):
    return next(_metadata_differences(actual, expected, path), None)


def _standard_metadata_equal(actual, expected):
    """Strict proof identity, allowing one adjacent float only for aggregate rating.

    Windows/Linux libm log1p can change the final descriptive Deep score by one
    representable float. This field is not the difficulty threshold or proof.
    The fresh logical verification has already run; every other field, including
    requiredRating, totalScore and the entire evidence, remains JSON-exact.
    Stored data is never rounded, rewritten, or otherwise normalized in place.
    """
    if _canonical_json(actual) == _canonical_json(expected):
        return True
    saved_rating, fresh_rating = actual.get("rating"), expected.get("rating")
    if (type(saved_rating) is not float or type(fresh_rating) is not float
            or not isfinite(saved_rating) or not isfinite(fresh_rating)
            or saved_rating < 0 or fresh_rating < 0
            or nextafter(saved_rating, fresh_rating) != fresh_rating):
        return False
    adjusted = dict(actual, rating=fresh_rating)
    return _canonical_json(adjusted) == _canonical_json(expected)


def technique_ceiling(difficulty, config=None):
    if difficulty not in STANDARD_DIFFICULTIES:
        raise ExportValidationError("Unknown standard difficulty")
    config = config or DifficultyConfig()
    thresholds = dict(config.classification_thresholds)
    # Expert is the final standard class, including high-rated paths which do
    # not meet Extreme's additional gates. Fresh Deep classification below is
    # authoritative; imposing a ceiling of 29 would redefine the existing class.
    if difficulty == "Expert":
        return max(entry.base_rating for entry in config.registry.entries)
    upper = thresholds[STANDARD_DIFFICULTIES[STANDARD_DIFFICULTIES.index(difficulty) + 1]]
    return max(entry.base_rating for entry in config.registry.entries if entry.base_rating < upper)


def verify_standard(puzzle, solution, difficulty, *, puzzle_id=None):
    """Return fresh JSON-native verified metadata, or fail closed.

    No saved status, rating, path, or solver flags are accepted as evidence.
    Exact solving is used only by validate_puzzle for uniqueness.
    """
    if difficulty not in STANDARD_DIFFICULTIES:
        raise ExportValidationError("Standard verification supports Easy, Medium, Hard and Expert")
    if not isinstance(puzzle, str):
        raise ExportValidationError("puzzle must be an ASCII digit string")
    identifier = content_id(puzzle)
    if puzzle_id is not None and puzzle_id != identifier:
        raise ExportValidationError("ID does not match the content hash")
    base = {"id": identifier, "puzzle": puzzle, "solution": solution,
            "clues": sum(c != "0" for c in puzzle), "difficulty": difficulty, "unique": True}
    validate_puzzle(base)
    if base["clues"] == 81:
        raise ExportValidationError("Production puzzles must contain at least one empty cell")
    grid = list(map(int, puzzle))
    config = DifficultyConfig()
    ceiling = technique_ceiling(difficulty, config)
    # Reject harder puzzles cheaply before running the complete Deep analysis.
    capped = solve_with_max_rating(grid, ceiling, config=config)
    if not capped.solved or capped.invalid or capped.used_backtracking or capped.guesses:
        raise ExportValidationError("Human solver cannot solve within the declared technique ceiling")
    analysis = DifficultyAnalyzer(config).deep(grid, check_unique=True)
    if (not analysis.solved or analysis.invalid or analysis.unique is not True
            or not analysis.required_level_verified or analysis.used_backtracking or analysis.guesses
            or analysis.difficulty_class != difficulty):
        raise ExportValidationError("Declared difficulty does not match fresh Deep classification")
    required = analysis.hardest_required_rating
    first = solve_with_max_rating(grid, required, config=config)
    replay = solve_with_max_rating(grid, required, config=config)
    for result in (first, replay):
        if (not result.solved or result.invalid or result.used_backtracking or result.guesses
                or "".join(map(str, result.grid)) != solution
                or any(config.registry.rating_of(step.technique) > ceiling for step in result.steps)):
            raise ExportValidationError("Human path does not reproduce the unique solution within ceiling")
    if first.steps != replay.steps or first.grid != replay.grid:
        raise ExportValidationError("Logical replay is not deterministic")
    proof = validate_path(grid, first.steps)
    if not proof.valid:
        raise ExportValidationError("Invalid logical proof: " + "; ".join(proof.errors))
    counts = dict(sorted(Counter(step.technique for step in first.steps).items()))
    base.update({"rating": analysis.rating, "hardestTechnique": analysis.hardest_required_technique,
                 "techniques": counts, "techniquesUsed": sorted(counts), "solutionSteps": len(first.steps),
                 "difficultyData": {"hardestRating": required, "totalScore": analysis.total_score,
                                    "advancedSteps": analysis.advanced_steps,
                                    "trueBottlenecks": analysis.true_bottleneck_count,
                                    "longestChain": analysis.longest_chain},
                 "verification": {"status": "VERIFIED", "version": 1,
                     "method": "DETERMINISTIC_THRESHOLD_REPLAY", "difficulty": difficulty,
                     "requiredRating": required, "techniqueCeiling": ceiling,
                     "humanSolved": True, "proofValidated": True, "reproducible": True,
                     "unique": True, "guesses": 0, "usedBacktracking": False,
                     "scope": "lowest successful tested threshold; bounded deterministic paths, not global necessity",
                     "evidence": {"thresholds": [asdict(t) for t in analysis.threshold_results],
                                  "path": [asdict(step) for step in first.steps]}}})
    return json.loads(json.dumps(base, allow_nan=False))


def validate_production_database(database):
    """Validate mixed production; retain the existing Extreme verifier intact."""
    validate_database(database)
    if database.get("datasetKind") != "production-certified":
        raise ExportValidationError("Missing production dataset marker")
    certified = []
    for record in database["puzzles"]:
        if record["difficulty"] in STANDARD_DIFFICULTIES:
            if "certification" in record:
                raise ExportValidationError("Standard puzzles must not claim Extreme certification")
            expected = verify_standard(record["puzzle"], record["solution"], record["difficulty"],
                                       puzzle_id=record["id"])
            # Unknown future top-level fields remain compatible. Every field in
            # the standard verification contract, including proof, is checked.
            actual = {key: record.get(key) for key in expected}
            if not _standard_metadata_equal(actual, expected):
                differences = "; ".join(islice(_metadata_differences(actual, expected), 5))
                raise ExportValidationError(
                    f"{record['id']}: metadata differs from fresh standard verification ({differences})")
        else:
            certified.append(record)
    subset = dict(database, puzzles=certified, stats=_stats(certified))
    validate_certified_database(subset)
    if _canonical_json(database.get("stats")) != _canonical_json(_stats(database["puzzles"])):
        raise ExportValidationError("Production statistics do not match records")


def _stats(puzzles):
    counts = Counter(record["difficulty"] for record in puzzles)
    return {"total": len(puzzles), "byDifficulty": dict(sorted(counts.items()))}
