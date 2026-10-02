import unittest
from unittest.mock import patch
from generator.rating.bottlenecks import bottleneck_at,detect_bottlenecks,summarize_bottlenecks
from generator.rating.models import DifficultyResult
from generator.rating.state_analysis import StateAnalyzer
from generator.solver.human_solver import HumanSolver
from generator.solver.models import LogicStep
from generator.sudoku.candidates import SudokuState
from generator.tests.test_state_rating import Stub

class BottleneckTests(unittest.TestCase):
    def test_fake_and_genuine_minimum(self):
        for techniques,expected in (([Stub("Hidden Single",1.2),Stub("AIC",30)],None),
                                    ([Stub("AIC",30)],30),
                                    ([Stub("AIC",30),Stub("ALS-XZ",36)],30)):
            with patch("generator.rating.state_analysis.solver_for_profile",return_value=HumanSolver(techniques)):
                event=bottleneck_at(SudokuState([0]*81),0,StateAnalyzer())
                self.assertEqual(event.required_rating if event else None,expected)

    def test_adjacent_eliminations_grouped(self):
        detector=Stub("AIC",30)
        detector.find_steps=lambda state:[LogicStep("AIC",30,eliminations=((c,1),),premises=(c,))
                                          for c in (0,1) if state.candidates[c]&1]
        steps=[LogicStep("AIC",30,eliminations=((c,1),),premises=(c,)) for c in (0,1)]
        analyzer=StateAnalyzer()
        with patch("generator.rating.state_analysis.solver_for_profile",return_value=HumanSolver([detector])):
            events=detect_bottlenecks([0]*81,steps,analyzer=analyzer)
        self.assertEqual(len(events),2)
        result=DifficultyResult(False,"deep",bottlenecks=events,step_count=2)
        summarize_bottlenecks(result,analyzer.config)
        self.assertEqual(result.true_bottleneck_count,1)
        self.assertEqual(result.bottleneck_severity,30)

    def test_applied_hard_step_cannot_hide_simple_alternative(self):
        step=LogicStep("AIC",30,eliminations=((0,1),))
        with patch("generator.rating.state_analysis.solver_for_profile",return_value=HumanSolver(
                [Stub("Hidden Single",1.2),Stub("AIC",30)])):
            self.assertEqual(detect_bottlenecks([0]*81,[step]),[])

    def test_repeated_pattern_merges_adjacent_episode_transitively(self):
        from types import SimpleNamespace
        steps=[LogicStep("AIC",30,eliminations=((0,1),),premises=("A",)),
               LogicStep("Locked Candidates",2,eliminations=((1,1),)),
               LogicStep("AIC",30,eliminations=((2,1),),premises=("B",)),
               LogicStep("AIC",30,eliminations=((3,1),),premises=("A",))]
        analyzer=StateAnalyzer()
        def minimum(state):
            index=next(i for i in (0,2,3) if state.candidates[i]&1)
            return SimpleNamespace(minimum_rating=30,minimum_technique="AIC",minimum_steps=(steps[index],))
        with patch.object(analyzer,"minimum_available_rating",side_effect=minimum):
            events=detect_bottlenecks([0]*81,steps,analyzer=analyzer)
        self.assertEqual(len(events),3)
        self.assertEqual(len({e.group_id for e in events}),1)
