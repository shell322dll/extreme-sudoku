"""A clue chromosome references one immutable complete solution."""

from dataclasses import dataclass

from .sudoku.grid import is_complete, validate_grid


@dataclass(frozen=True)
class Individual:
    clue_mask: int
    solution: tuple[int, ...]

    def __post_init__(self):
        if type(self.clue_mask) is not int or not 0 <= self.clue_mask < (1 << 81):
            raise ValueError("clue_mask must be an 81-bit nonnegative integer")
        solution = tuple(validate_grid(self.solution))
        if not is_complete(solution):
            raise ValueError("solution must be a complete valid Sudoku")
        object.__setattr__(self, "solution", solution)

    @property
    def clue_count(self) -> int:
        return self.clue_mask.bit_count()

    def to_puzzle(self) -> list[int]:
        return [value if self.clue_mask & (1 << i) else 0
                for i, value in enumerate(self.solution)]
