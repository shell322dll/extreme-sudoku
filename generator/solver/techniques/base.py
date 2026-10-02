"""Plugin contract: find deductions without mutating the supplied state."""

from abc import ABC, abstractmethod
from math import isfinite

from ..models import LogicStep
from ...sudoku.candidates import SudokuState


class Technique(ABC):
    name: str
    difficulty: float

    def __init__(self, difficulty: float | None = None):
        value = self.difficulty if difficulty is None else difficulty
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Difficulty must be a finite nonnegative number")
        if not isfinite(value) or value < 0:
            raise ValueError("Difficulty must be a finite nonnegative number")
        self.difficulty = float(value)

    @abstractmethod
    def find_steps(self, state: SudokuState) -> list[LogicStep]:
        """Return all useful deductions in deterministic order."""

    def step(self, *, placements=(), eliminations=(), premises=(), explanation="", **proof):
        return LogicStep(
            technique=self.name,
            rating=self.difficulty,
            placements=tuple(sorted(set(placements))),
            eliminations=tuple(sorted(set(eliminations))),
            premises=tuple(premises),
            explanation=explanation,
            **proof,
        )


def step_key(step: LogicStep):
    """Stable tie break, independent of sets and plugin result ordering."""
    return (step.placements, step.eliminations, step.technique,
            step.chain.length if step.chain else 0, repr(step.premises), step.explanation)


def unique_steps(steps):
    by_effect = {}
    for step in sorted(steps, key=step_key):
        by_effect.setdefault((step.placements, step.eliminations), step)
    return list(by_effect.values())


def cell_name(cell):
    return f"r{cell // 9 + 1}c{cell % 9 + 1}"


def unit_name(index):
    return f"{('row', 'column', 'box')[index // 9]} {index % 9 + 1}"
