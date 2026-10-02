"""Independent known-solution audit; the oracle is never passed to detectors."""

import random
import unittest
from collections import Counter

from generator.solution_generator import generate_solution
from generator.sudoku.candidates import SudokuState, digit_mask
from generator.solver.techniques import advanced_techniques
from generator.solver.advanced_config import AdvancedConfig


class AdvancedSoundnessTests(unittest.TestCase):
    def test_deductions_preserve_independent_witness_on_varied_candidate_states(self):
        rng = random.Random(9824)
        config = AdvancedConfig(max_chain_search_nodes=10000, max_als_search_nodes=3000,
                                max_forcing_starts=40)
        techniques = advanced_techniques(config=config)
        counts = Counter()
        for sample in range(18):
            solution = generate_solution(sample)
            grid = [digit if rng.random() < 0.25 else 0 for digit in solution]
            state = SudokuState(grid)
            for cell, mask in enumerate(state.candidates):
                if mask:
                    state.candidates[cell] = digit_mask(solution[cell]) | sum(
                        digit_mask(digit) for digit in range(1, 10)
                        if digit != solution[cell] and mask & digit_mask(digit) and rng.random() < 0.7)
            state.validate()
            before = (state.grid[:], state.candidates[:])
            for technique in techniques:
                with self.subTest(sample=sample, technique=technique.name):
                    steps = technique.find_steps(state)
                    self.assertEqual(before, (state.grid, state.candidates))
                    for step in steps:
                        counts[technique.name] += 1
                        self.assertTrue(all(solution[c] == d for c, d in step.placements), step)
                        self.assertTrue(all(solution[c] != d for c, d in step.eliminations), step)
        self.assertEqual(set(counts), {technique.name for technique in techniques})
        self.assertGreater(sum(counts.values()), 1000)


if __name__ == "__main__":
    unittest.main()
