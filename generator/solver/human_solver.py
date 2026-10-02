"""Deterministic greedy logic only: no guessing or exact-solver dependency."""

from collections import Counter

from .models import HumanSolveResult, LogicStep
from .techniques import default_techniques, INTERMEDIATE_TECHNIQUE_NAMES, ADVANCED_TECHNIQUE_NAMES
from .techniques.base import step_key
from ..sudoku.candidates import SudokuState, digit_mask
from ..sudoku.grid import validate_grid


def apply_step(state: SudokuState, step: LogicStep) -> SudokuState:
    """Apply a deduction atomically to a copy, suitable for path replay."""
    if not step.placements and not step.eliminations:
        raise ValueError("A logical step must make progress")
    updated = state.copy()
    for cell, digit in step.placements + step.eliminations:
        if type(cell) is not int or not 0 <= cell < 81:
            raise ValueError("Invalid cell in logical step")
        if updated.grid[cell] or not state.candidates[cell] & digit_mask(digit):
            raise ValueError("Logical step targets an absent candidate")
    for cell, digit in step.placements:
        updated.place(cell, digit)
    for cell, digit in step.eliminations:
        updated.eliminate(cell, digit)
    updated.validate()
    return updated


class HumanSolver:
    def __init__(self, techniques=None, *, weights=None, config=None):
        if techniques is not None and (weights is not None or config is not None):
            raise ValueError("Configure weights/limits on custom technique instances")
        items = default_techniques(weights, config=config) if techniques is None else list(techniques)
        self.techniques = tuple(sorted(items, key=lambda t: (t.difficulty, t.name)))

    def all_available_steps(self, state):
        """All representative deductions within each detector's configured bounds.

        An empty result is not proof that no unrestricted logical move exists.
        This API prepares bottleneck analysis; it does not certify necessity.
        """
        return sorted((step for technique in self.techniques for step in technique.find_steps(state)),
                      key=lambda step: (step.rating, step_key(step)))

    def minimum_available_rating(self, state):
        for technique in self.techniques:
            if technique.find_steps(state):
                return technique.difficulty
        return None

    def solve(self, grid):
        steps = []
        # Malformed input is an API error; contradictory clues are a result.
        values = validate_grid(grid)
        try:
            state = SudokuState(values)
        except ValueError:
            return HumanSolveResult(False, False, True, values)
        invalid = False
        while not state.is_solved:
            for technique in self.techniques:
                available = technique.find_steps(state)
                if available:
                    step = min(available, key=step_key)
                    try:
                        state = apply_step(state, step)
                    except ValueError:
                        invalid = True
                    else:
                        steps.append(step)
                    break  # Restart at the easiest technique after every step.
            else:
                break
            if invalid:
                break
        hardest = max(steps, key=lambda step: step.rating, default=None)
        return HumanSolveResult(
            solved=state.is_solved and not invalid,
            stuck=not state.is_solved and not invalid,
            invalid=invalid,
            grid=state.grid.copy(), steps=steps,
            hardest_technique=hardest.technique if hardest else None,
            max_rating=hardest.rating if hardest else 0.0,
            total_score=sum(step.rating ** 2 for step in steps),
            technique_counts=dict(Counter(step.technique for step in steps)),
            intermediate_steps=sum(step.technique in INTERMEDIATE_TECHNIQUE_NAMES for step in steps),
            advanced_steps=sum(step.technique in ADVANCED_TECHNIQUE_NAMES for step in steps),
            chain_step_count=sum(bool(step.chain or step.assumptions) for step in steps),
            longest_chain=max((step.chain_length for step in steps), default=0),
            als_step_count=sum(bool(step.als) for step in steps),
            forcing_step_count=sum(bool(step.assumptions) for step in steps),
        )


def solve(grid, **kwargs):
    return HumanSolver(**kwargs).solve(grid)


def all_available_steps(state, **kwargs):
    return HumanSolver(**kwargs).all_available_steps(state)
