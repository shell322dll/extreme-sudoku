"""Unique, individually minimal clue sets; no difficulty certification."""

import random

from .solver.exact_solver import has_unique_solution
from .sudoku.grid import is_complete, validate_grid


def minimize_puzzle(solution, seed=None) -> list[int]:
    """Remove clues while unique, then verify a pass removes nothing more.

    Minimal means no single clue is removable, not a minimum clue count.
    """
    puzzle = validate_grid(solution)
    if not is_complete(puzzle):
        raise ValueError("solution must be a complete valid Sudoku")
    rng = random.Random(seed)
    while True:
        positions = [i for i, value in enumerate(puzzle) if value]
        rng.shuffle(positions)
        changed = False
        for cell in positions:
            value, puzzle[cell] = puzzle[cell], 0
            if has_unique_solution(puzzle):
                changed = True
            else:
                puzzle[cell] = value
        if not changed:
            return puzzle


def generate_clue_mask(solution, seed=None) -> int:
    puzzle = minimize_puzzle(solution, seed=seed)
    return sum(1 << i for i, value in enumerate(puzzle) if value)


def is_minimal(puzzle) -> bool:
    board = validate_grid(puzzle)
    if not has_unique_solution(board):
        return False
    for cell, value in enumerate(board):
        if value:
            board[cell] = 0
            unique = has_unique_solution(board)
            board[cell] = value
            if unique:
                return False
    return True
