import unittest
from generator.rating.profiles import (PROFILES,solver_for_profile,solve_with_max_rating,
    solve_with_max_tier,solve_with_disabled_techniques)
from generator.tests.test_human_solver import PUZZLE

INTERMEDIATE="728000000000000500000409000640070020900000000000645009201000870090380000000000040"
ADVANCED="710000004800000020090000830004700000050040200007800000040002500000094702001380090"
EXTREME="009000830001340020040050000030900006024100000000007090080000050002700049000000600"

class RatingProfileTests(unittest.TestCase):
    def test_profile_boundaries(self):
        self.assertEqual([max(t.difficulty for t in solver_for_profile(p).techniques)
                          for p in PROFILES],[5.2,11,18,55])

    def test_real_tier_fixtures(self):
        self.assertTrue(solve_with_max_tier(PUZZLE,"BASIC").solved)
        for text,lower,upper in ((INTERMEDIATE,"BASIC","INTERMEDIATE"),
                                 (ADVANCED,"INTERMEDIATE","ADVANCED")):
            puzzle=list(map(int,text))
            self.assertTrue(solve_with_max_tier(puzzle,lower).stuck)
            self.assertTrue(solve_with_max_tier(puzzle,upper).solved)

    def test_threshold_inclusion_and_disabled(self):
        puzzle=list(map(int,INTERMEDIATE))
        self.assertTrue(solve_with_max_rating(puzzle,9.2).stuck)
        self.assertTrue(solve_with_max_rating(puzzle,10).solved)
        self.assertTrue(solve_with_disabled_techniques(PUZZLE,{"AIC"}).solved)
        with self.assertRaises(ValueError): solve_with_disabled_techniques(PUZZLE,{"missing"})
        with self.assertRaises(ValueError): solve_with_max_rating(PUZZLE,-1)
