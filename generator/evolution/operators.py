"""Mask-only mutations. Every outcome requires fresh uniqueness and rating."""
from ..chromosome import Individual
from ..sudoku.grid import ALL_UNITS, PEERS

OPERATORS = ("remove", "add", "swap", "multi_swap", "region", "guided")


def guided_cells(rating):
    """Prioritize unresolved bottleneck candidates and their influencing peers.

    A signature contains both grid and logical candidate masks. Small candidate
    structures are a local heuristic, never a predicted improvement or proof.
    """
    if rating is None:
        return ()
    events = sorted((b for b in rating.bottlenecks if b.genuine),
                    key=lambda b: (-b.required_rating, b.step_index))
    if not events:
        return ()
    grid, masks = events[0].state_signature
    cells = sorted((i for i in range(81) if not grid[i] and masks[i]),
                   key=lambda i: (masks[i].bit_count(), i))[:4]
    region = set(cells)
    for cell in cells:
        region.update(PEERS[cell])
    return tuple(sorted(region))


def _swap(candidate, rng, count, cells=None):
    scope = range(81) if cells is None else cells
    present = [i for i in scope if candidate.clue_mask & (1 << i)]
    absent = [i for i in scope if not candidate.clue_mask & (1 << i)]
    count = min(count, len(present), len(absent))
    mask = candidate.clue_mask
    for cell in rng.sample(present, count):
        mask &= ~(1 << cell)
    for cell in rng.sample(absent, count):
        mask |= 1 << cell
    return Individual(mask, candidate.solution)


def mutate(candidate, rng, operator="swap", *, multi_swap_sizes=(2, 3), rating=None, strength=1):
    if operator not in OPERATORS:
        raise ValueError("unknown mutation operator")
    if type(strength) is not int or strength < 1:
        raise ValueError("strength must be a positive integer")
    if operator in ("remove", "add"):
        present = operator == "remove"
        cells = [i for i in range(81) if bool(candidate.clue_mask & (1 << i)) == present]
        mask = candidate.clue_mask
        for cell in rng.sample(cells, min(strength, len(cells))):
            mask ^= 1 << cell
        return Individual(mask, candidate.solution)
    if operator == "multi_swap":
        if not multi_swap_sizes or any(type(n) is not int or n < 1 for n in multi_swap_sizes):
            raise ValueError("multi_swap_sizes must be positive integers")
        return _swap(candidate, rng, rng.choice(multi_swap_sizes) * strength)
    if operator == "region":
        return _swap(candidate, rng, strength, rng.choice(ALL_UNITS))
    if operator == "guided":
        return _swap(candidate, rng, strength, guided_cells(rating) or None)
    return _swap(candidate, rng, strength)


def crossover(a, b, rng):
    """Recombine only masks sharing a target; caller repairs and reduces."""
    if a.solution != b.solution:
        raise ValueError("crossover requires identical target solutions")
    mask = a.clue_mask & b.clue_mask
    optional = a.clue_mask ^ b.clue_mask
    for cell in range(81):
        if optional & (1 << cell) and rng.random() < .5:
            mask |= 1 << cell
    return Individual(mask, a.solution)
