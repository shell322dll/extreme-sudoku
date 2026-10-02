import unittest
from unittest.mock import patch
from generator.rating.difficulty import DifficultyAnalyzer
from generator.solver import exact_solver
from generator.tests.test_human_solver import PUZZLE
from generator.tests.test_rating_profiles import EXTREME

class DeepRatingTests(unittest.TestCase):
    def test_easy_deep_and_exact_boundary(self):
        with patch.object(exact_solver,"count_solutions",side_effect=AssertionError("Exact forbidden")), \
             patch.object(exact_solver,"solve_one",side_effect=AssertionError("Exact forbidden")):
            result=DifficultyAnalyzer().deep(PUZZLE)
        self.assertTrue(result.solved and result.required_level_verified)
        self.assertEqual(result.hardest_required_rating,1)
        self.assertEqual(result.profile_statuses["Basic"],"SOLVED")
        self.assertEqual(result.true_bottleneck_count,0)

    def test_real_aic_floor_and_distinct_crises(self):
        result=DifficultyAnalyzer().deep(list(map(int,EXTREME)))
        self.assertTrue(result.solved and result.required_level_verified)
        self.assertEqual(result.hardest_required_rating,30)
        self.assertEqual(result.profile_statuses["Advanced"],"STUCK")
        self.assertGreaterEqual(result.true_bottleneck_count,2)
        self.assertEqual(result.advanced_steps,5)
        self.assertTrue(all(e.easier_steps_available==0 for e in result.bottlenecks))
