from dataclasses import replace
import unittest
from generator.rating.classification import classify
from generator.rating.config import DifficultyConfig
from generator.rating.difficulty import analyze_difficulty
from generator.rating.models import DifficultyResult
from generator.rating.report import diagnostic_report
from generator.tests.test_rating_profiles import EXTREME

class ClassificationTests(unittest.TestCase):
    def candidate(self):
        return DifficultyResult(True,"deep",hardest_required_rating=36,required_level_verified=True,
            unique=True,advanced_steps=5,true_bottleneck_count=3,longest_chain=9,
            chain_steps=5,distributed_advanced_steps=2,
            profile_statuses={"Basic":"STUCK","Intermediate":"STUCK","Extreme":"SOLVED"})

    def test_all_classes_and_boundaries(self):
        config=DifficultyConfig()
        for rating,expected in ((0,"Easy"),(2,"Medium"),(7,"Hard"),(12,"Expert")):
            self.assertEqual(classify(DifficultyResult(True,"quick",hardest_rating=rating),config).difficulty_class,expected)
        result=self.candidate()
        self.assertEqual(classify(result,config).difficulty_class,"Ultra Extreme")
        result.hardest_required_rating=30
        self.assertEqual(classify(result,config).difficulty_class,"Extreme")
        self.assertEqual(classify(result,replace(config,extreme_threshold=35)).difficulty_class,"Expert")

    def test_fake_peak_clues_and_missing_evidence(self):
        for change in ({"advanced_steps":1},{"true_bottleneck_count":1},{"unique":None},
                       {"unique":False},{"used_backtracking":True},{"guesses":1},
                       {"mode":"quick"},{"required_level_verified":False}):
            result=replace(self.candidate(),**change)
            classify(result,DifficultyConfig())
            self.assertFalse(result.is_extreme_candidate)
        result=self.candidate()
        result.clue_count=17
        result.hardest_required_rating=1
        self.assertEqual(classify(result,DifficultyConfig()).difficulty_class,"Easy")

    def test_real_extreme_preliminary_candidate_and_report(self):
        result=analyze_difficulty(list(map(int,EXTREME)))
        self.assertTrue(result.unique and result.is_extreme_candidate)
        self.assertEqual(result.difficulty_class,"Extreme")
        self.assertFalse(result.is_ultra_extreme_candidate)
        report=diagnostic_report(result)
        self.assertIn("preliminary only",report)
        self.assertIn("Basic profile: STUCK",report)
        self.assertIn("Hardest required rating: 30",report)
