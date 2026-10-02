"""Seeded complete grids using a Latin pattern and Sudoku symmetries."""

import random


def generate_solution(seed=None) -> list[int]:
    """Return a reproducible valid solution; not uniform over all Sudoku grids."""
    rng = random.Random(seed)

    def order():
        return [group * 3 + offset
                for group in rng.sample(range(3), 3)
                for offset in rng.sample(range(3), 3)]

    rows, cols = order(), order()
    digits = rng.sample(range(1, 10), 9)
    grid = [digits[(r * 3 + r // 3 + c) % 9] for r in rows for c in cols]
    if rng.randrange(2):
        grid = [grid[c * 9 + r] for r in range(9) for c in range(9)]
    return grid
