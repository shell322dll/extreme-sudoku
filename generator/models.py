"""Public results and diagnostic counters for the ordinary generator."""
from dataclasses import dataclass, field
from enum import Enum

from .config import DIFFICULTIES
from .rating.models import DifficultyResult
from .solver.models import HumanSolveResult

GENERATOR_VERSION = "0.5.0"


class RejectionReason(str, Enum):
    NOT_UNIQUE = "NOT_UNIQUE"
    OUTSIDE_CLUE_RANGE = "OUTSIDE_CLUE_RANGE"
    HUMAN_UNSOLVED = "HUMAN_UNSOLVED"
    WRONG_DIFFICULTY = "WRONG_DIFFICULTY"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True)
class GeneratedPuzzle:
    id: str
    puzzle: str
    solution: str
    clues: int
    unique: bool
    minimal: bool
    difficulty: str
    rating: float
    difficulty_result: DifficultyResult
    human_result: HumanSolveResult
    seed: int
    attempt_seed: int
    attempts: int
    clue_mask: int

    @property
    def clue_count(self):
        return self.clues


@dataclass
class GenerationStats:
    attempts: int = 0
    generated_complete_grids: int = 0
    accepted: int = 0
    rejections: dict[RejectionReason, int] = field(default_factory=dict)
    stage_seconds: dict[str, float] = field(default_factory=dict)
    stage_calls: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    timed_out: bool = False

    def reject(self, reason):
        self.rejections[reason] = self.rejections.get(reason, 0) + 1

    def to_dict(self):
        return {
            "attempts": self.attempts,
            "generatedCompleteGrids": self.generated_complete_grids,
            "accepted": self.accepted,
            "uniquenessRejects": self.rejections.get(RejectionReason.NOT_UNIQUE, 0),
            "difficultyRejects": self.rejections.get(RejectionReason.WRONG_DIFFICULTY, 0),
            "clueRangeRejects": self.rejections.get(RejectionReason.OUTSIDE_CLUE_RANGE, 0),
            "humanSolverStuck": self.rejections.get(RejectionReason.HUMAN_UNSOLVED, 0),
            "rejections": {reason.value: count for reason, count in sorted(self.rejections.items())},
            "stageSeconds": dict(sorted(self.stage_seconds.items())),
            "stageCalls": dict(sorted(self.stage_calls.items())),
            "elapsedSeconds": self.elapsed_seconds,
            "timedOut": self.timed_out,
        }


@dataclass(frozen=True)
class BatchResult:
    puzzles: tuple[GeneratedPuzzle, ...]
    requested: int
    seed: int
    stats: GenerationStats
    preliminary_candidates: tuple[GeneratedPuzzle, ...] = ()

    @property
    def complete(self):
        return len(self.puzzles) == self.requested


class GenerationError(RuntimeError):
    def __init__(self, result):
        self.result = result
        super().__init__(f"Generated {len(result.puzzles)}/{result.requested} puzzles after "
                         f"{result.stats.attempts} attempts; rejections={result.stats.to_dict()['rejections']}; "
                         f"timed_out={result.stats.timed_out}")
