import unittest
from unittest.mock import patch
from generator.rating.mandatory import required_level,technique_necessity
from generator.solver.models import HumanSolveResult,LogicStep
from generator.tests.test_human_solver import PUZZLE,SOLUTION
from generator.tests.test_rating_profiles import INTERMEDIATE,ADVANCED,EXTREME

class MandatoryTests(unittest.TestCase):
    def test_real_required_levels(self):
        for puzzle,rating,tier in ((PUZZLE,1.,"TRIVIAL"),(list(map(int,INTERMEDIATE)),10.,"INTERMEDIATE"),
                                  (list(map(int,ADVANCED)),14.,"ADVANCED")):
            result=required_level(puzzle)
            self.assertTrue(result.solved and result.verified)
            self.assertEqual((result.rating,result.tier),(rating,tier))
            self.assertTrue(all(a.status=="STUCK" for a in result.attempts[:-1]))

    def test_complete_and_invalid(self):
        complete=required_level(SOLUTION)
        self.assertEqual(complete.rating,0)
        self.assertEqual(len(complete.attempts),1)
        invalid=required_level([1]*81)
        self.assertFalse(invalid.verified)
        self.assertIsNone(invalid.rating)

    def test_invalid_lower_threshold_cannot_verify_floor(self):
        def solve(puzzle,rating,**kwargs):
            return HumanSolveResult(rating>0,False,rating==0,SOLUTION,
                steps=[LogicStep("Full House",.5)] if rating else [])
        with patch("generator.rating.mandatory.solve_with_max_rating",side_effect=solve):
            self.assertFalse(required_level(PUZZLE).verified)

    def test_specific_technique_is_not_same_as_required_level(self):
        # Seed 4 admits an alternative ALS/forcing repertoire after AIC is disabled.
        result=technique_necessity(list(map(int,EXTREME)),"AIC")
        self.assertEqual(result.baseline_status,"SOLVED")
        self.assertEqual(result.disabled_status,"SOLVED")
        self.assertFalse(result.necessary_within_solver)
