"""MRV bitmask DFS for existence and uniqueness, never human difficulty."""

from ..sudoku.grid import validate_grid

_ALL = 511
_ROW = tuple(i // 9 for i in range(81))
_COL = tuple(i % 9 for i in range(81))
_BOX = tuple(i // 27 * 3 + i % 9 // 3 for i in range(81))


def _search(grid, limit: int, keep_solution: bool, solutions=None):
    board = validate_grid(grid)
    rows, cols, boxes = [0] * 9, [0] * 9, [0] * 9
    empty = []
    for cell, value in enumerate(board):
        if not value:
            empty.append(cell)
            continue
        bit = 1 << (value - 1)
        r, c, b = _ROW[cell], _COL[cell], _BOX[cell]
        if bit & (rows[r] | cols[c] | boxes[b]):
            return 0, None
        rows[r] |= bit
        cols[c] |= bit
        boxes[b] |= bit

    count, solution = 0, None

    def visit(depth):
        nonlocal count, solution
        if depth == len(empty):
            count += 1
            if solutions is not None:
                solutions.append(board.copy())
            if keep_solution and solution is None:
                solution = board.copy()
            return count >= limit
        best_index, best_mask, best_size = depth, 0, 10
        for index in range(depth, len(empty)):
            cell = empty[index]
            mask = _ALL & ~(rows[_ROW[cell]] | cols[_COL[cell]] | boxes[_BOX[cell]])
            size = mask.bit_count()
            if not size:
                return False
            if size < best_size:
                best_index, best_mask, best_size = index, mask, size
                if size == 1:
                    break
        empty[depth], empty[best_index] = empty[best_index], empty[depth]
        cell = empty[depth]
        r, c, b = _ROW[cell], _COL[cell], _BOX[cell]
        while best_mask:
            bit = best_mask & -best_mask
            best_mask ^= bit
            board[cell] = bit.bit_length()
            rows[r] |= bit
            cols[c] |= bit
            boxes[b] |= bit
            stop = visit(depth + 1)
            rows[r] ^= bit
            cols[c] ^= bit
            boxes[b] ^= bit
            board[cell] = 0
            if stop:
                empty[depth], empty[best_index] = empty[best_index], empty[depth]
                return True
        empty[depth], empty[best_index] = empty[best_index], empty[depth]
        return False

    visit(0)
    return count, solution


def solve_one(grid) -> list[int] | None:
    """Return one solution or None; malformed input raises ValueError."""
    return _search(grid, 1, True)[1]


def count_solutions(grid, limit: int = 2) -> int:
    """Count up to limit and stop immediately upon reaching it."""
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    return _search(grid, limit, False)[0]


def has_unique_solution(grid) -> bool:
    return count_solutions(grid, limit=2) == 1


def collect_solutions(grid, limit: int = 2) -> list[list[int]]:
    """Collect distinct exact witnesses for generator repair, never rating."""
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    solutions = []
    _search(grid, limit, False, solutions)
    return solutions
