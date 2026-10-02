import unittest
from dataclasses import replace

from generator.solver.advanced_config import AdvancedConfig
from generator.solver.models import CandidateNode, Chain, ChainLink
from generator.solver.techniques.chains import InferenceGraph, XChain, XYChain, AIC, NiceLoop, GroupedAIC
from generator.sudoku.candidates import ALL, SudokuState, digit_mask
from generator.sudoku.grid import ROWS, COLS, BOXES


def state_with_cells(mapping):
    masks = [ALL] * 81
    for cell, digits in mapping.items():
        masks[cell] = sum(digit_mask(d) for d in digits)
    return SudokuState([0] * 81, masks)


def restricted_digit(*restrictions):
    masks = [ALL] * 81
    for unit, allowed in restrictions:
        for cell in unit:
            if cell not in allowed:
                masks[cell] &= ~digit_mask(5)
    return SudokuState([0] * 81, masks)


class ChainTests(unittest.TestCase):
    def check(self, technique, state, expected):
        before = (state.grid[:], state.candidates[:])
        steps = technique.find_steps(state)
        self.assertTrue(any(expected in step.eliminations for step in steps), (technique.name, steps))
        self.assertEqual(steps, technique.find_steps(state))
        self.assertEqual(before, (state.grid, state.candidates))
        effects = [(s.placements, s.eliminations) for s in steps]
        self.assertEqual(len(effects), len(set(effects)))
        graph = InferenceGraph(state, grouped=technique.grouped, mode=technique.mode)
        for step in steps:
            self.assertTrue(graph.valid_chain(step.chain), step)
            self.assertLessEqual(step.chain.length, getattr(technique.config, technique.limit_name))
        return steps

    def test_strong_and_weak_cell_semantics(self):
        state = state_with_cells({0: (1, 2), 4: (1, 2, 3)})
        graph = InferenceGraph(state)
        a, b, c = CandidateNode((0,), 1), CandidateNode((0,), 2), CandidateNode((4,), 1)
        self.assertTrue(graph.has_link(a, b, "strong"))
        self.assertTrue(graph.has_link(a, b, "weak"))
        self.assertTrue(graph.has_link(a, c, "weak"))
        self.assertFalse(graph.has_link(a, c, "strong"))
        self.assertFalse(graph.has_link(c, CandidateNode((4,), 2), "strong"))
        self.assertFalse(graph.has_link(a, CandidateNode((40,), 1), "weak"))

    def test_unit_links_and_broken_pair(self):
        a, b = CandidateNode((0,), 5), CandidateNode((4,), 5)
        self.assertTrue(InferenceGraph(restricted_digit((ROWS[0], (0, 4)))).has_link(a, b, "strong"))
        self.assertFalse(InferenceGraph(restricted_digit((ROWS[0], (0, 4, 8)))).has_link(a, b, "strong"))

    def test_x_chain(self):
        self.check(XChain(), restricted_digit((ROWS[0], (0, 4)), (ROWS[3], (27, 32))), (14, 5))

    def test_x_negative_broken_link_and_no_conclusion(self):
        for state in (restricted_digit((ROWS[0], (0, 4, 8)), (ROWS[3], (27, 32))),
                      restricted_digit((ROWS[0], (0, 4))), SudokuState([0] * 81)):
            self.assertEqual(XChain().find_steps(state), [])

    def test_xy_chain_multivalue_target(self):
        self.check(XYChain(), state_with_cells({0: (1, 2), 4: (2, 3), 40: (1, 3)}), (36, 1))

    def test_xy_wrong_endpoint_broken_bivalue_and_visibility(self):
        for mapping in ({0: (1, 2), 4: (2, 3), 40: (3, 4)},
                        {0: (1, 2), 4: (2, 3, 4), 40: (1, 3)},
                        {0: (1, 2), 4: (2, 3), 41: (1, 3)}):
            self.assertEqual(XYChain().find_steps(state_with_cells(mapping)), [])

    def test_aic(self):
        self.check(AIC(), state_with_cells({0: (1, 2), 4: (2, 3), 40: (1, 3)}), (36, 1))

    def test_aic_negative(self):
        self.assertEqual(AIC().find_steps(state_with_cells({0: (1, 2, 4), 4: (2, 3, 4), 40: (1, 3, 4)})), [])

    def test_aic_strong_discontinuity_places_candidate(self):
        # not r1c1=5 forces both r1c2=5 and r2c1=5, which conflict in box 1.
        state = restricted_digit((ROWS[0], (0, 1)), (COLS[0], (0, 9)))
        steps = AIC().find_steps(state)
        step = next(s for s in steps if s.placements == ((0, 5),))
        self.assertTrue(step.chain.closed)
        self.assertEqual(step.chain.nodes[0], CandidateNode((0,), 5))
        self.assertEqual([e.kind for e in step.chain.links], ["strong", "weak", "strong"])
        self.assertTrue(InferenceGraph(state).valid_chain(step.chain))
        self.assertFalse(any((40, 5) in s.eliminations or (40, 5) in s.placements for s in steps))

    def test_aic_weak_discontinuity_eliminates_candidate(self):
        state = restricted_digit((ROWS[0], (0, 1)), (COLS[0], (0, 9)))
        step = next(s for s in AIC().find_steps(state) if s.eliminations == ((1, 5),))
        self.assertTrue(step.chain.closed)
        self.assertEqual(step.chain.nodes[0], CandidateNode((1,), 5))
        self.assertEqual([e.kind for e in step.chain.links], ["weak", "strong", "weak"])
        self.assertTrue(InferenceGraph(state).valid_chain(step.chain))

    def test_aic_discontinuities_require_every_strong_link(self):
        # The third column support breaks the strong edge r1c1--r2c1.
        state = restricted_digit((ROWS[0], (0, 1)), (COLS[0], (0, 9, 27)))
        steps = AIC().find_steps(state)
        self.assertFalse(any((0, 5) in s.placements for s in steps))
        self.assertFalse(any((1, 5) in s.eliminations for s in steps))

    def test_nice_loop(self):
        steps = self.check(NiceLoop(), restricted_digit((ROWS[0], (0, 4)), (ROWS[3], (27, 31))), (54, 5))
        self.assertTrue(all("continuous" in s.explanation and "discontinuity" not in s.explanation
                            for s in steps))

    def test_nice_loop_negative(self):
        self.assertEqual(NiceLoop().find_steps(restricted_digit((ROWS[0], (0, 4)), (ROWS[3], (27, 31, 35)))), [])

    def test_grouped_aic(self):
        state = restricted_digit((BOXES[0], (1, 2, 9, 18)), (COLS[4], (4, 40)))
        self.check(GroupedAIC(), state, (36, 5))
        graph = InferenceGraph(state, grouped=True)
        a, b = CandidateNode((1, 2), 5), CandidateNode((9, 18), 5)
        self.assertTrue(graph.has_link(a, b, "strong"))
        self.assertTrue(graph.has_link(a, b, "weak"))
        self.assertFalse(graph.has_link(a, CandidateNode((10,), 5), "weak"))  # absent candidate

    def test_grouped_invalid_partition_and_visibility(self):
        state = restricted_digit((BOXES[0], (1, 2, 9, 18, 20)), (COLS[4], (4, 40)))
        graph = InferenceGraph(state, grouped=True)
        self.assertFalse(graph.has_link(CandidateNode((1, 2), 5), CandidateNode((9, 18), 5), "strong"))
        self.assertFalse(graph.has_link(CandidateNode((9, 18), 5), CandidateNode((12,), 5), "weak"))
        self.assertFalse(any((36, 5) in s.eliminations for s in GroupedAIC().find_steps(state)))

    def test_invalid_chain_certificates(self):
        state = state_with_cells({0: (1, 2), 4: (2, 3), 40: (1, 3)})
        graph = InferenceGraph(state)
        step = next(s for s in AIC().find_steps(state) if (36, 1) in s.eliminations)
        chain = step.chain
        broken = replace(chain.links[1], kind="strong")
        self.assertFalse(graph.valid_chain(replace(chain, links=(chain.links[0], broken) + chain.links[2:])))
        self.assertFalse(graph.valid_chain(replace(chain, nodes=chain.nodes[:-1] + (chain.nodes[0],))))
        self.assertFalse(graph.valid_chain(Chain((chain.nodes[0],), ())))

    def test_search_bounds(self):
        state = state_with_cells({0: (1, 2), 4: (2, 3), 40: (1, 3)})
        self.assertEqual(XYChain(config=AdvancedConfig(max_xy_chain_length=3)).find_steps(state), [])
        self.assertEqual(AIC(config=AdvancedConfig(max_chain_search_nodes=1)).find_steps(state), [])
        for value in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                AdvancedConfig(max_aic_length=value)

    def test_nineteen_link_xy_chain_and_exact_length_cutoff(self):
        state = state_with_cells({0: (1, 2), 4: (2, 3), 40: (3, 4), 43: (4, 5),
                                  70: (5, 6), 68: (6, 7), 14: (7, 8), 12: (8, 9),
                                  21: (9, 2), 18: (2, 1)})
        technique = XYChain(config=AdvancedConfig(max_xy_chain_length=19))
        steps = self.check(technique, state, (8, 2))
        step = next(s for s in steps if (8, 2) in s.eliminations)
        self.assertEqual(step.chain.length, 19)
        self.assertEqual(len(set(step.chain.nodes)), 20)
        shorter = XYChain(config=AdvancedConfig(max_xy_chain_length=18)).find_steps(state)
        self.assertFalse(any((8, 2) in s.eliminations for s in shorter))


if __name__ == "__main__":
    unittest.main()
