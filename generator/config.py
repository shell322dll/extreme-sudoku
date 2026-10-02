"""Configuration for deterministic ordinary generation, without evolution."""
from dataclasses import dataclass
from math import isfinite

from .rating.config import DifficultyConfig

DIFFICULTIES = ("Easy", "Medium", "Hard", "Expert", "Extreme", "Ultra Extreme")


@dataclass(frozen=True)
class GeneratorConfig:
    seed: int | None = None
    min_clues: int = 17
    max_clues: int = 23
    target_difficulty: str | None = None
    require_minimal: bool = True
    require_unique: bool = True
    max_attempts: int = 100
    rating_mode: str = "quick_then_deep"
    symmetry: str | None = "none"
    timeout_seconds: float | None = None
    difficulty_config: DifficultyConfig = DifficultyConfig()

    def __post_init__(self):
        if self.seed is not None and type(self.seed) is not int:
            raise ValueError("seed must be an integer or None")
        if any(type(value) is not int for value in (self.min_clues, self.max_clues)):
            raise ValueError("clue limits must be integers")
        if not 17 <= self.min_clues <= self.max_clues <= 81:
            raise ValueError("clue limits must satisfy 17 <= min_clues <= max_clues <= 81")
        if self.target_difficulty is not None and self.target_difficulty not in DIFFICULTIES:
            raise ValueError("unknown target difficulty")
        if type(self.require_minimal) is not bool or self.require_unique is not True:
            raise ValueError("require_minimal must be boolean; unique puzzles are mandatory")
        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if self.rating_mode not in ("quick", "deep", "quick_then_deep"):
            raise ValueError("unknown rating_mode")
        if self.rating_mode == "quick" and self.target_difficulty in DIFFICULTIES[4:]:
            raise ValueError("Extreme targets require deep or quick_then_deep rating")
        if self.symmetry not in (None, "none"):
            raise ValueError("Phase 5 supports only symmetry='none'")
        if self.timeout_seconds is not None and (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")
        if not isinstance(self.difficulty_config, DifficultyConfig):
            raise ValueError("difficulty_config must be a DifficultyConfig")
