import unittest
from itertools import product

from generator.tests.test_chains import state_with_cells
from generator.solver.advanced_config import AdvancedConfig
from generator.solver.techniques.als import (
    AlmostLockedSet, enumerate_als, restricted_common_candidates, endpoint_eliminations,
    ALSGraph, ALSXZ, ALSXYWing, ALSChain,
)
from generator.sudoku.grid import PEERS


class ALSTests(unittest.TestCase):
    def test_canonical_als_and_deduplication(self):
        self.assertEqual(AlmostLockedSet((1, 0), (6, 3)), AlmostLockedSet((0, 1), (3, 6)))
        state = state_with_cells({0: (1, 2), 1: (2, 3)})
        sets = enumerate_als(state)
        self.assertEqual(len(sets), len({a.cells for a in sets}))
        self.assertEqual(sets, enumerate_als(state))
        self.assertIn(AlmostLockedSet((0, 1), (3, 6)), sets)
        self.assertEqual(AlmostLockedSet((0, 1), (3, 6)).digits, (1, 2, 3))

    def test_invalid_als(self):
        for cells, masks in (((0, 1), (3, 3)), ((0, 1), (3, 12)), ((0, 40), (3, 6)),
                             ((0, 0), (3, 6)), ((0,), (0,)), ((), ())):
            with self.subTest(cells=cells, masks=masks), self.assertRaises(ValueError):
                AlmostLockedSet(cells, masks)

    def test_valid_and_invalid_rcc(self):
        a, b = AlmostLockedSet((0,), (3,)), AlmostLockedSet((4,), (6,))
        self.assertEqual(restricted_common_candidates(a, b), (2,))
        self.assertEqual(restricted_common_candidates(a, AlmostLockedSet((40,), (6,))), ())
        self.assertEqual(restricted_common_candidates(a, a), ())
        # Some visibility is insufficient: all occurrences must conflict.
        c = AlmostLockedSet((4, 40), (6, 10))
        self.assertEqual(restricted_common_candidates(a, c), ())

    def check(self, technique, mapping, expected):
        state = state_with_cells(mapping)
        before = (state.grid[:], state.candidates[:])
        steps = technique.find_steps(state)
        self.assertTrue(any(expected in s.eliminations for s in steps), steps)
        self.assertEqual(steps, technique.find_steps(state))
        self.assertEqual(before, (state.grid, state.candidates))
        self.assertEqual(len(steps), len({s.eliminations for s in steps}))
        for step in steps:
            self.assertTrue(step.als)
            self.assertEqual(step.chain.length, len(step.als) - 1)
            self.assertEqual(step.eliminations,
                             endpoint_eliminations(state, step.als, tuple(e.digit for e in step.chain.links)))

    def test_als_xz(self):
        self.check(ALSXZ(), {0: (1, 2), 4: (1, 2)}, (1, 1))

    def test_multicell_als_xz_and_independent_exact_local_assignments(self):
        mapping = {0: (1, 2), 1: (2, 3), 4: (1, 4), 13: (3, 4)}
        self.check(ALSXZ(), mapping, (10, 3))
        step = next(s for s in ALSXZ().find_steps(state_with_cells(mapping))
                    if tuple(a.cells for a in s.als) == ((0, 1), (4, 13)))
        self.assertEqual(step.eliminations, ((3, 3), (5, 3), (9, 3), (10, 3), (11, 3)))
        # Exact enumeration is confined to tests. It uses only ordinary peer
        # constraints, independently of ALS/RCC/chain implementation logic.
        cells = tuple(mapping)
        assignments = [dict(zip(cells, values)) for values in product(*(mapping[c] for c in cells))
                       if all(values[i] != values[j] or cells[j] not in PEERS[cells[i]]
                              for i in range(len(cells)) for j in range(i))]
        self.assertTrue(assignments, "The proof must not be vacuously unsatisfiable")
        for cell, digit in step.eliminations:
            self.assertTrue(all(any(value == digit and peer in PEERS[cell]
                                    for peer, value in assignment.items())
                                for assignment in assignments))

    def test_multicell_xz_requires_all_rcc_occurrences_to_see(self):
        # Add an occurrence of X=1 in r2c5, invisible from r1c1.
        state = state_with_cells({0: (1, 2), 1: (2, 3), 4: (1, 4), 13: (1, 3, 4)})
        self.assertFalse(any((10, 3) in s.eliminations for s in ALSXZ().find_steps(state)))

    def test_xy_wing_broken_rcc_and_wrong_endpoint(self):
        for mapping in ({0: (1, 2), 4: (2, 3), 41: (1, 3)},
                        {0: (1, 2), 4: (2, 3), 40: (3, 4)}):
            self.assertFalse(any((36, 1) in s.eliminations
                                 for s in ALSXYWing().find_steps(state_with_cells(mapping))))

    def test_chain_broken_rcc_and_wrong_endpoint(self):
        for mapping in ({0: (1, 2), 4: (2, 3), 41: (3, 4), 36: (1, 4)},
                        {0: (1, 2), 4: (2, 3), 40: (3, 4), 36: (4, 5)}):
            self.assertFalse(any((27, 1) in s.eliminations
                                 for s in ALSChain().find_steps(state_with_cells(mapping))))

    def test_als_xy_wing(self):
        self.check(ALSXYWing(), {0: (1, 2), 4: (2, 3), 40: (1, 3)}, (36, 1))

    def test_als_chain(self):
        self.check(ALSChain(), {0: (1, 2), 4: (2, 3), 40: (3, 4), 36: (1, 4)}, (27, 1))

    def test_all_techniques_invalid_visibility_and_no_conclusion(self):
        for cls in (ALSXZ, ALSXYWing, ALSChain):
            for mapping in ({0: (1, 2), 40: (1, 2)},
                            {0: (1, 2), 4: (2, 3), 40: (3, 4)}, {}):
                self.assertEqual(cls().find_steps(state_with_cells(mapping)), [], (cls, mapping))

    def test_broken_chain_adjacent_same_rcc_repeated_set_and_wrong_endpoint(self):
        state = state_with_cells({0: (1, 2), 4: (2, 3), 40: (1, 3)})
        a, b, c = (AlmostLockedSet((i,), (state.candidates[i],)) for i in (0, 4, 40))
        self.assertEqual(endpoint_eliminations(state, (a, b, c), (2, 2)), ())
        self.assertEqual(endpoint_eliminations(state, (a, b, a), (2, 2)), ())
        self.assertEqual(endpoint_eliminations(state, (a, b, c), (1, 3)), ())
        self.assertEqual(endpoint_eliminations(state, (a, b), (2,)), ())

    def test_limits(self):
        state = state_with_cells({0: (1, 2), 4: (2, 3), 40: (3, 4), 36: (1, 4)})
        self.assertEqual(ALSChain(config=AdvancedConfig(max_als_chain_length=3)).find_steps(state), [])
        graph = ALSGraph.build(state, AdvancedConfig(max_als_search_nodes=1))
        self.assertTrue(graph.truncated)
        self.assertEqual(graph.pair_checks, 1)
        self.assertTrue(all(len(a.cells) <= 1 for a in enumerate_als(state, 1)))


if __name__ == "__main__":
    unittest.main()
