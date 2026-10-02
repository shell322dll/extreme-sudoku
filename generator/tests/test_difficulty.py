from dataclasses import replace
import unittest
from unittest.mock import patch
from generator.rating.config import DifficultyConfig
from generator.rating.difficulty import DifficultyAnalyzer, path_metrics, step_score
from generator.solver.models import LogicStep, Chain, HumanSolveResult
from generator.solver.human_solver import HumanSolver
from generator.sudoku.candidates import SudokuState
from generator.tests.test_human_solver import PUZZLE, SOLUTION

class QuickDifficultyTests(unittest.TestCase):
    def test_quick_is_deterministic_and_no_alternative_enumeration(self):
        with patch.object(HumanSolver,"all_available_steps",side_effect=AssertionError):
            a=DifficultyAnalyzer().quick(PUZZLE)
            self.assertEqual(a,DifficultyAnalyzer().quick(PUZZLE))
        self.assertTrue(a.solved)
        self.assertEqual(a.step_count,len(a.difficulty_profile))
        self.assertEqual(a.step_count,len(a.state_signatures))
        self.assertIsNone(a.hardest_required_rating)
        self.assertFalse(a.is_extreme_candidate)

    def test_chain_lengths_grouping_and_weights(self):
        c=DifficultyConfig()
        short=LogicStep("AIC",30,chain=Chain((),(None,)*4))
        long=replace(short,chain=Chain((),(None,)*18))
        self.assertGreater(step_score(long,c),step_score(short,c))
        self.assertGreater(step_score(replace(short,grouped_nodes=(1,2)),c),step_score(short,c))

    def test_signature_includes_candidates_and_copy_independence(self):
        state=SudokuState([0]*81)
        signature=state.signature()
        clone=state.copy()
        clone.eliminate(0,1)
        self.assertNotEqual(signature,clone.signature())
        self.assertEqual(signature,state.signature())

    def test_solved_invalid_and_unsolved(self):
        solved=DifficultyAnalyzer().quick(SOLUTION)
        self.assertEqual(solved.total_score,0)
        self.assertEqual(solved.difficulty_profile,[])
        self.assertFalse(DifficultyAnalyzer().quick([0]*81).solved)
        self.assertTrue(DifficultyAnalyzer().quick([1]*81).invalid)

    def test_als_and_forcing_proof_metadata_affect_cost(self):
        from generator.solver.techniques.forcing import Inference,Propagation
        config=DifficultyConfig()
        plain=LogicStep("ALS-XZ",36)
        self.assertEqual(step_score(replace(plain,als=(object(),)),config)-step_score(plain,config),
                         config.als_bonus)
        proof=Propagation((0,1,True),(
            Inference((0,1),True,0,"assumption",(),()),
            Inference((1,1),False,1,"exclusion",(),(0,)),
            Inference((1,2),True,2,"last-support",(),(0,1)),
        ))
        forcing=LogicStep("Forcing Chain",50,assumptions=(proof,proof))
        self.assertEqual(forcing.chain_length,2)
        # 2 link-depth units, two branch points plus the second assumption.
        expected=50**2+2*config.chain_length_factor+3*config.branching_factor+config.forcing_bonus
        self.assertEqual(step_score(forcing,config),expected)
