"""Reproduce local Phase 3 fixtures using the existing Phase 1 clue minimizer.

This is a finite test-data search, not an evolutionary generator or rating
certification. Run manually: python -m generator.tests.build_phase3_fixtures.
"""

import argparse
import json
from pathlib import Path
from time import perf_counter

from generator.solution_generator import generate_solution
from generator.clue_generator import minimize_puzzle
from generator.solver.human_solver import HumanSolver, apply_step
from generator.solver.techniques import phase2_techniques
from generator.solver.techniques.chains import XChain, XYChain, AIC
from generator.solver.techniques.als import ALSXZ
from generator.solver.techniques.forcing import ForcingChain, Nishio
from generator.sudoku.candidates import SudokuState


def discover():
    wanted = {cls.name: cls for cls in (XChain, XYChain, AIC, ALSXZ, ForcingChain, Nishio)}
    fixtures = []
    start = perf_counter()
    for seed in range(1000):
        puzzle = minimize_puzzle(generate_solution(seed=seed), seed=seed)
        phase2 = HumanSolver(phase2_techniques()).solve(puzzle)
        if phase2.solved:
            continue
        state = SudokuState(puzzle)
        for step in phase2.steps:
            state = apply_step(state, step)
        default = HumanSolver().solve(puzzle)
        print(seed, "default", default.solved, default.technique_counts, flush=True)
        if default.invalid:
            raise AssertionError((seed, "invalid deduction"))
        if not default.solved:
            continue
        for name, cls in list(wanted.items()):
            if not cls().find_steps(state):
                continue
            result = HumanSolver(phase2_techniques() + [cls()]).solve(puzzle)
            if result.solved and result.technique_counts.get(name):
                fixtures.append({"id": "seed-" + str(seed) + "-" + name.lower().replace(" ", "-"),
                                 "seed": seed, "puzzle": "".join(map(str, puzzle)),
                                 "source": "minimize_puzzle(generate_solution(seed=n), seed=n)",
                                 "target_technique": name,
                                 "target_repertoire": "Phase 2 + target technique",
                                 "target_steps": result.technique_counts[name],
                                 "target_longest_chain": result.longest_chain,
                                 "default_techniques": default.technique_counts,
                                 "solution": "".join(map(str, result.grid))})
                del wanted[name]
                print("FOUND", name, seed, result.longest_chain, flush=True)
        if not wanted:
            break
    path = Path(__file__).parent / "fixtures" / "phase3_puzzles.json"
    path.write_text(json.dumps(fixtures, indent=2) + "\n", encoding="utf-8")
    print("Saved", len(fixtures), "missing", list(wanted), "seconds", perf_counter() - start, flush=True)


def refresh():
    """Fixed recipes reproduce all validated fixtures, including the mixed one."""
    recipes = ((4, AIC), (4, ALSXZ), (4, ForcingChain), (4, Nishio),
               (29, XYChain), (193, XChain), (48, None))
    fixtures = []
    for seed, cls in recipes:
        puzzle = minimize_puzzle(generate_solution(seed=seed), seed=seed)
        if not HumanSolver(phase2_techniques()).solve(puzzle).stuck:
            raise AssertionError((seed, "Phase 2 must be stuck"))
        default = HumanSolver().solve(puzzle)
        if not default.solved or default.invalid:
            raise AssertionError((seed, "default solver must solve"))
        name = cls.name if cls else "mixed-advanced"
        result = HumanSolver(phase2_techniques() + [cls()]).solve(puzzle) if cls else default
        expected = [name] if cls else ["Grouped AIC", "ALS-XZ", "ALS-XY-Wing", "ALS Chain"]
        if not result.solved or any(not result.technique_counts.get(n) for n in expected):
            raise AssertionError((seed, expected, result.technique_counts))
        fixture = {"id": f"seed-{seed}-" + name.lower().replace(" ", "-"),
                   "seed": seed, "puzzle": "".join(map(str, puzzle)),
                   "source": "minimize_puzzle(generate_solution(seed=n), seed=n)",
                   "target_repertoire": "Phase 2 + target technique" if cls else "default",
                   "target_longest_chain": result.longest_chain,
                   "default_techniques": default.technique_counts,
                   "solution": "".join(map(str, result.grid))}
        if cls:
            fixture.update(target_technique=name, target_steps=result.technique_counts[name])
        else:
            fixture["target_techniques"] = expected
        fixtures.append(fixture)
    path = Path(__file__).parent / "fixtures" / "phase3_puzzles.json"
    path.write_text(json.dumps(fixtures, indent=2) + "\n", encoding="utf-8")
    print("Refreshed", len(fixtures), "fixtures", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true", help="Search seeds instead of refreshing known recipes")
    args = parser.parse_args()
    if args.discover:
        discover()
        # Discovery is exploratory; the committed regression corpus remains
        # stable and always includes the verified mixed-advanced fixture last.
    refresh()


if __name__ == "__main__":
    main()
