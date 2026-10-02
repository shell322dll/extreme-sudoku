"""Candidate bitmasks; mutations retain logical eliminations and are atomic."""

from .grid import ALL_UNITS, PEERS, is_consistent, validate_cell, validate_grid

ALL = (1 << 9) - 1


def digit_mask(digit: int) -> int:
    if type(digit) is not int or not 1 <= digit <= 9:
        raise ValueError("digit must be an integer in 1..9")
    return 1 << (digit - 1)


def mask_digits(mask: int) -> tuple[int, ...]:
    if type(mask) is not int or not 0 <= mask <= ALL:
        raise ValueError("candidate mask must be a 9-bit nonnegative integer")
    return tuple(d for d in range(1, 10) if mask & (1 << (d - 1)))


class SudokuState:
    """Mutable logical state; filled cells have zero candidate masks.

    Explicit masks may omit candidates already eliminated by logic. Validation
    detects local contradictions, not global satisfiability (no search here).
    """

    def __init__(self, grid, candidates=None):
        self.grid = validate_grid(grid)
        if candidates is None:
            self.candidates = [0 if value else self._allowed(i)
                               for i, value in enumerate(self.grid)]
        else:
            try:
                self.candidates = list(candidates)
            except TypeError as exc:
                raise ValueError("candidates must contain 81 masks") from exc
        self.validate()

    def _allowed(self, cell: int) -> int:
        used = 0
        for peer in PEERS[cell]:
            if self.grid[peer]:
                used |= digit_mask(self.grid[peer])
        return ALL & ~used

    def validate(self) -> None:
        validate_grid(self.grid)
        if not is_consistent(self.grid):
            raise ValueError("conflicting givens")
        if len(self.candidates) != 81:
            raise ValueError("candidates must contain 81 masks")
        for cell, mask in enumerate(self.candidates):
            mask_digits(mask)
            if self.grid[cell]:
                if mask:
                    raise ValueError("filled cells must have zero candidates")
            elif not mask or mask & ~self._allowed(cell):
                raise ValueError("empty or conflicting candidate mask")
        for unit in ALL_UNITS:
            supported = 0
            for cell in unit:
                supported |= (digit_mask(self.grid[cell]) if self.grid[cell]
                              else self.candidates[cell])
            if supported != ALL:
                raise ValueError("a unit has no position for a required digit")

    def copy(self):
        return SudokuState(self.grid, self.candidates)

    def signature(self):
        """Canonical immutable state key, including logical eliminations."""
        return tuple(self.grid), tuple(self.candidates)

    @property
    def is_solved(self) -> bool:
        self.validate()
        return all(self.grid)

    def place(self, cell: int, digit: int) -> None:
        validate_cell(cell)
        bit = digit_mask(digit)
        if self.grid[cell] or not self.candidates[cell] & bit:
            raise ValueError("placement is not an available candidate")
        trial = self.copy()
        trial.grid[cell] = digit
        trial.candidates[cell] = 0
        for peer in PEERS[cell]:
            trial.candidates[peer] &= ~bit
        trial.validate()
        self.grid, self.candidates = trial.grid, trial.candidates

    def eliminate(self, cell: int, digit: int) -> None:
        validate_cell(cell)
        bit = digit_mask(digit)
        if self.grid[cell]:
            raise ValueError("cannot eliminate from a filled cell")
        trial = self.copy()
        trial.candidates[cell] &= ~bit
        trial.validate()
        self.grid, self.candidates = trial.grid, trial.candidates
