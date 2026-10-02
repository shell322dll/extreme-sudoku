from dataclasses import replace
import unittest
from unittest.mock import patch
from generator.rating.config import DifficultyConfig
from generator.rating.profiles import BASIC_PROFILE
from generator.rating.state_analysis import StateAnalyzer
from generator.solver.human_solver import HumanSolver
from generator.solver.models import LogicStep
from generator.solver.techniques.base import Technique
from generator.sudoku.candidates import SudokuState

class Stub(Technique):
    def __init__(self,name,rating):
        self.name=name
        self.difficulty=rating
    def find_steps(self,state):
        return [LogicStep(self.name,self.difficulty,eliminations=((0,1),))] if state.candidates[0]&1 else []

class StateRatingTests(unittest.TestCase):
    def check(self,names,expected):
        analyzer=StateAnalyzer()
        solver=HumanSolver([Stub(n,r) for n,r in names])
        state=SudokuState([0]*81)
        with patch("generator.rating.state_analysis.solver_for_profile",return_value=solver):
            full=analyzer.analyze_state(state)
            minimum=analyzer.minimum_available_rating(state)
        self.assertEqual(full.minimum_rating,expected)
        self.assertEqual(minimum.minimum_rating,expected)
        self.assertTrue(full.enumeration_complete)
        self.assertFalse(minimum.enumeration_complete)
        return full

    def test_hidden_single_prevents_aic_floor(self):
        self.check([("AIC",30),("Hidden Single",1.2)],1.2)
    def test_only_aic(self):
        self.check([("AIC",30)],30)
    def test_aic_and_als(self):
        self.check([("ALS-XZ",36),("AIC",30)],30)
    def test_cache_mutation_profile_config_and_clear(self):
        analyzer=StateAnalyzer()
        state=SudokuState([0]*81)
        with patch("generator.rating.state_analysis.solver_for_profile",return_value=HumanSolver([Stub("AIC",30)])):
            first=analyzer.analyze_state(state)
            self.assertIs(first,analyzer.analyze_state(state.copy()))
            self.assertEqual(analyzer.cache_hits,1)
            state.eliminate(0,1)
            self.assertIsNone(analyzer.analyze_state(state).minimum_rating)
            analyzer.analyze_state(state,BASIC_PROFILE)
            analyzer.config=replace(analyzer.config,chain_length_factor=2)
            analyzer.analyze_state(state)
            self.assertEqual(analyzer.cache_misses,4)
            analyzer.clear_cache()
            self.assertEqual(len(analyzer._cache),0)
    def test_bad_deduction_is_error_not_missing_move(self):
        solver=HumanSolver([Stub("AIC",30)])
        solver.techniques[0].find_steps=lambda state:[LogicStep("AIC",30,eliminations=((0,10),))]
        with patch("generator.rating.state_analysis.solver_for_profile",return_value=solver):
            with self.assertRaises(ValueError): StateAnalyzer().analyze_state(SudokuState([0]*81))

    def test_equal_rating_detectors_and_minimum_count(self):
        from generator.rating.registry import TechniqueRegistry
        config=StateAnalyzer().config
        registry=TechniqueRegistry(tuple(replace(e,base_rating=30) if e.name=="Nice Loop" else e
                                           for e in config.registry.entries))
        analyzer=StateAnalyzer(replace(config,registry=registry))
        solver=HumanSolver([Stub("ALS-XZ",36),Stub("Nice Loop",30),Stub("AIC",30)])
        with patch("generator.rating.state_analysis.solver_for_profile",return_value=solver):
            minimum=analyzer.minimum_available_rating(SudokuState([0]*81))
            full=analyzer.analyze_state(SudokuState([0]*81))
        self.assertEqual(len(minimum.minimum_steps),2)
        self.assertEqual(minimum.number_of_alternatives,2)
        self.assertEqual(full.number_of_alternatives,3)
        self.assertEqual(full.maximum_rating,36)

    def test_cache_disabled_and_eviction(self):
        for size in (0,1):
            analyzer=StateAnalyzer(replace(StateAnalyzer().config,cache_size=size))
            first=SudokuState([0]*81)
            second=first.copy()
            second.eliminate(80,9)
            with patch("generator.rating.state_analysis.solver_for_profile",return_value=HumanSolver([Stub("AIC",30)])):
                analyzer.analyze_state(first)
                analyzer.analyze_state(second)
                analyzer.analyze_state(first)
            self.assertEqual(analyzer.cache_hits,0)
            self.assertEqual(len(analyzer._cache),size)
