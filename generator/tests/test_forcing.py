import unittest

from generator.tests.test_chains import state_with_cells
from generator.solver.advanced_config import AdvancedConfig
from generator.solver.models import LogicStep
from generator.solver.techniques.forcing import (
    ForcingChain, Nishio, propagate, logical_clauses, proof_for, Inference, Propagation,
)


class ForcingTests(unittest.TestCase):
    def setUp(self):
        self.state = state_with_cells({0: (1, 2), 4: (2, 3), 40: (1, 3)})

    def test_contradiction(self):
        proof = propagate(self.state, (36, 1, True))
        self.assertTrue(proof.contradiction)
        self.assertTrue(all(p < i for i, item in enumerate(proof.inferences) for p in item.parents))
        self.assertEqual(proof.inferences[0].rule, "assumption")

    def test_no_contradiction(self):
        proof = propagate(state_with_cells({}), (0, 1, True))
        self.assertFalse(proof.contradiction)
        self.assertFalse(proof.limited)

    def test_depth_and_node_limits_are_not_contradictions(self):
        for config in (AdvancedConfig(max_forcing_depth=1), AdvancedConfig(max_forcing_nodes=1)):
            proof = propagate(self.state, (36, 1, True), config)
            self.assertTrue(proof.limited)
            self.assertFalse(proof.contradiction)
            self.assertLessEqual(len(proof.inferences), config.max_forcing_nodes)
            self.assertLessEqual(proof.depth, config.max_forcing_depth)

    def test_common_forcing_and_nishio_deterministic_pure_and_unique(self):
        before = (self.state.grid[:], self.state.candidates[:])
        # Include the contradiction's start cell despite wide synthetic candidates.
        config = AdvancedConfig(max_forcing_starts=729)
        for technique in (ForcingChain(config=config), Nishio(config=config)):
            steps = technique.find_steps(self.state)
            self.assertTrue(any((36, 1) in s.eliminations for s in steps))
            self.assertEqual(steps, technique.find_steps(self.state))
            self.assertEqual(len(steps), len({(s.placements, s.eliminations) for s in steps}))
            self.assertTrue(all(s.assumptions for s in steps))
        self.assertEqual(before, (self.state.grid, self.state.candidates))

    def test_broken_link_near_pattern(self):
        state = state_with_cells({0: (1, 2), 4: (2, 3, 4), 40: (1, 3)})
        self.assertFalse(propagate(state, (36, 1, True)).contradiction)
        self.assertEqual(ForcingChain().find_steps(state), [])
        self.assertEqual(Nishio().find_steps(state), [])

    def test_invalid_assumption(self):
        for assumption in ((0, 3, True), (0, 1, 1), (81, 1, True)):
            with self.assertRaises(ValueError):
                propagate(self.state, assumption)

    def test_trace_rules_replay(self):
        for truth in (False, True):
            self.assert_trace_rules(propagate(self.state, (0, 1, truth)))

    def assert_trace_rules(self, proof):
        clauses = logical_clauses(self.state)
        for index, inference in enumerate(proof.inferences):
            self.assertTrue(all(0 <= p < index for p in inference.parents))
            parents = [proof.inferences[i] for i in inference.parents]
            if parents:
                self.assertEqual(inference.depth, 1 + max(p.depth for p in parents))
            if inference.rule == "assumption":
                self.assertEqual(index, 0)
            elif inference.rule == "single":
                self.assertIn(inference.clause, clauses)
                self.assertEqual(inference.clause, (inference.candidate,))
            elif inference.rule == "exclusion":
                self.assertIn(inference.clause, clauses)
                self.assertEqual(len(parents), 1)
                self.assertTrue(parents[0].value)
                self.assertFalse(inference.value)
                self.assertIn(parents[0].candidate, inference.clause)
                self.assertIn(inference.candidate, inference.clause)
                self.assertNotEqual(parents[0].candidate, inference.candidate)
            else:
                self.assertEqual(inference.rule, "last-support")
                self.assertIn(inference.clause, clauses)
                self.assertTrue(inference.value)
                self.assertTrue(all(not p.value for p in parents))
                self.assertEqual({p.candidate for p in parents}, set(inference.clause) - {inference.candidate})

    def test_trimmed_common_conclusion_proofs_replay(self):
        steps = ForcingChain(config=AdvancedConfig(max_forcing_starts=2)).find_steps(self.state)
        self.assertTrue(steps)
        for step in steps:
            conclusion = ((step.placements or step.eliminations)[0], bool(step.placements))
            for proof in step.assumptions:
                self.assert_trace_rules(proof)
                self.assertIn(conclusion, proof.facts)
                needed = {0}
                pending = [i for i, item in enumerate(proof.inferences)
                           if (item.candidate, item.value) == conclusion]
                while pending:
                    index = pending.pop()
                    if index not in needed:
                        needed.add(index)
                        pending.extend(proof.inferences[index].parents)
                self.assertEqual(needed, set(range(len(proof.inferences))))
            self.assertEqual(step.chain_length, max(p.depth for p in step.assumptions))

    def test_trimmed_proof_reindexes_parents_and_excludes_unrelated_depth(self):
        raw = Propagation((0, 1, True), (
            Inference((0, 1), True, 0, "assumption", (), ()),
            Inference((0, 2), False, 1, "exclusion", ((0, 1), (0, 2)), (0,)),
            Inference((1, 1), False, 1, "exclusion", ((0, 1), (1, 1)), (0,)),
            Inference((1, 2), True, 2, "last-support", ((1, 1), (1, 2)), (2,)),
            Inference((10, 2), False, 3, "exclusion", ((1, 2), (10, 2)), (3,)),
        ))
        trimmed = proof_for(raw, ((1, 2), True))
        self.assertEqual([x.candidate for x in trimmed.inferences], [(0, 1), (1, 1), (1, 2)])
        self.assertEqual([x.parents for x in trimmed.inferences], [(), (0,), (1,)])
        self.assertEqual(trimmed.depth, 2)
        self.assertEqual(raw.depth, 3)
        step = LogicStep("Forcing Chain", 50, placements=((1, 2),), assumptions=(trimmed,))
        self.assertEqual(step.chain_length, 2)

    def test_trimmed_contradiction_retains_and_reindexes_roots(self):
        raw = propagate(self.state, (36, 1, True))
        proof = proof_for(raw)
        self.assert_trace_rules(proof)
        self.assertLess(len(proof.inferences), len(raw.inferences))
        self.assertLessEqual(proof.depth, raw.depth)
        kind = proof.contradiction[0]
        indices = proof.contradiction[1:] if kind == "opposite" else proof.contradiction[2]
        roots = [proof.inferences[i] for i in indices]
        if kind == "opposite":
            self.assertEqual(roots[0].candidate, roots[1].candidate)
            self.assertNotEqual(roots[0].value, roots[1].value)
        else:
            self.assertIn(proof.contradiction[1], logical_clauses(self.state))
            if kind == "empty-clause":
                self.assertTrue(all(not item.value for item in roots))
                self.assertEqual({item.candidate for item in roots}, set(proof.contradiction[1]))
            else:
                self.assertEqual(kind, "two-true")
                self.assertGreaterEqual(len(roots), 2)
                self.assertTrue(all(item.value for item in roots))


if __name__ == "__main__":
    unittest.main()
