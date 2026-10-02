"""Tournament selection, clone suppression and a verified Pareto archive."""
from math import isfinite


def mask_distance(a, b):
    return (a.clue_mask ^ b.clue_mask).bit_count()


def mean_diversity(population):
    population = tuple(population)
    pairs = len(population) * (len(population) - 1) // 2
    return (sum(mask_distance(a, b) for i, a in enumerate(population)
                for b in population[i + 1:]) / pairs if pairs else 0.)


def _near(a, b, distance):
    # Same mask on an unrelated target is not a duplicate Sudoku.
    return a.solution == b.solution and mask_distance(a, b) < distance


def _adjusted(individual, population, near_distance, penalty):
    neighbors = sum(p.key != individual.key and _near(individual, p, near_distance)
                    for p in population)
    return individual.fitness - (abs(individual.fitness) * penalty * neighbors
                                 if isfinite(individual.fitness) else 0.)


def tournament_select(population, rng, size=5, near_distance=4, penalty=.02):
    population = tuple(population)
    if not population:
        raise ValueError("cannot select from an empty population")
    if type(size) is not int or size < 1:
        raise ValueError("tournament size must be a positive integer")
    competitors = rng.sample(population, min(size, len(population)))
    return max(competitors, key=lambda p: (_adjusted(p, population, near_distance, penalty),
                                           p.fitness, p.key))


def select_survivors(population, size, *, elites=(), near_distance=4, penalty=.02):
    """Preserve exact elite objects, then greedily discourage near clones."""
    if type(size) is not int or size < 0:
        raise ValueError("population size must be a nonnegative integer")
    selected, seen = [], set()
    for individual in elites:
        if individual.key not in seen and len(selected) < size:
            selected.append(individual)
            seen.add(individual.key)
    unique = {}
    for individual in population:
        previous = unique.get(individual.key)
        if previous is None or (individual.deep_rating is not None, individual.fitness) > (previous.deep_rating is not None, previous.fitness):
            unique[individual.key] = individual
    remaining = [p for key, p in unique.items() if key not in seen]
    while remaining and len(selected) < size:
        chosen = max(remaining, key=lambda p: (_adjusted(p, selected, near_distance, penalty),
                                               p.fitness, p.key))
        selected.append(chosen)
        remaining.remove(chosen)
    return tuple(selected)


def dominates(a, b):
    """All objectives maximize; clue objective is stored negated."""
    return (len(a.fitness_vector) == len(b.fitness_vector) and bool(a.fitness_vector)
            and all(x >= y for x, y in zip(a.fitness_vector, b.fitness_vector))
            and any(x > y for x, y in zip(a.fitness_vector, b.fitness_vector)))


def pareto_archive(population, limit=100):
    """Only verified bounded Deep evidence may claim required difficulty."""
    if type(limit) is not int or limit < 1:
        raise ValueError("archive limit must be a positive integer")
    unique = {}
    for p in population:
        r = p.deep_rating
        if (p.unique is True and p.clue_count >= 17 and r is not None and r.solved
                and not r.invalid and not r.used_backtracking and not r.guesses
                and r.required_level_verified and isfinite(p.fitness) and p.fitness_vector):
            unique[p.key] = p
    frontier = [p for p in unique.values() if not any(dominates(other, p)
                                                     for other in unique.values() if other.key != p.key)]
    frontier.sort(key=lambda p: (-p.fitness, p.key))
    if len(frontier) <= limit:
        return tuple(frontier)
    # Preserve endpoints across objectives before filling with scalar leaders.
    preserved = [frontier[0]]
    for axis in range(len(frontier[0].fitness_vector)):
        endpoint = max(frontier, key=lambda p: (p.fitness_vector[axis], p.fitness, p.key))
        if endpoint.key not in {p.key for p in preserved} and len(preserved) < limit:
            preserved.append(endpoint)
    for p in frontier:
        if p.key not in {a.key for a in preserved} and len(preserved) < limit:
            preserved.append(p)
    return tuple(sorted(preserved, key=lambda p: (-p.fitness, p.key)))
