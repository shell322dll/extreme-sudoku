"""Validated flat 9 x 9 grids and immutable, precomputed topology."""

from collections.abc import Iterable


def validate_cell(cell: int) -> None:
    if type(cell) is not int or not 0 <= cell < 81:
        raise ValueError("cell must be an integer in 0..80")


def row_of(cell: int) -> int:
    validate_cell(cell)
    return cell // 9


def col_of(cell: int) -> int:
    validate_cell(cell)
    return cell % 9


def box_of(cell: int) -> int:
    validate_cell(cell)
    return cell // 27 * 3 + cell % 9 // 3


ROWS = tuple(tuple(r * 9 + c for c in range(9)) for r in range(9))
COLS = tuple(tuple(r * 9 + c for r in range(9)) for c in range(9))
BOXES = tuple(
    tuple((b // 3 * 3 + r) * 9 + b % 3 * 3 + c
          for r in range(3) for c in range(3))
    for b in range(9)
)
ALL_UNITS = ROWS + COLS + BOXES
UNITS = tuple((ROWS[row_of(i)], COLS[col_of(i)], BOXES[box_of(i)])
              for i in range(81))
PEERS = tuple(tuple(sorted(set().union(*UNITS[i]) - {i})) for i in range(81))
# Spellings used in the specification.
units = UNITS
peers = PEERS


def validate_grid(grid: Iterable[int]) -> list[int]:
    """Return an independent list; reject malformed data, not conflicting givens."""
    try:
        values = list(grid)
    except TypeError as exc:
        raise ValueError("grid must contain 81 integers") from exc
    if len(values) != 81 or any(type(n) is not int or not 0 <= n <= 9 for n in values):
        raise ValueError("grid must contain exactly 81 integers in 0..9")
    return values


def is_consistent(grid: Iterable[int]) -> bool:
    values = validate_grid(grid)
    for unit in ALL_UNITS:
        filled = [values[i] for i in unit if values[i]]
        if len(filled) != len(set(filled)):
            return False
    return True


def is_complete(grid: Iterable[int]) -> bool:
    values = validate_grid(grid)
    return all(values) and is_consistent(values)
