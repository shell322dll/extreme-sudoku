import ast
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from generator.rating.config import DifficultyConfig
from generator.rating.difficulty import DifficultyAnalyzer,analyze_difficulty
from generator.solver import exact_solver
from generator.tests.test_rating_profiles import EXTREME

FIXTURES=json.loads((Path(__file__).parent/"fixtures/difficulty/regression.json").read_text())

class Phase4IntegrationTests(unittest.TestCase):
    def test_semantic_regression_fixtures(self):
        for fixture in FIXTURES:
            with self.subTest(id=fixture["id"]):
                result=analyze_difficulty(list(map(int,fixture["puzzle"])))
                self.assertEqual(result.solved,fixture["solved"])
                self.assertEqual(result.minimum_tier,fixture["minimum_tier"])
                self.assertEqual(result.difficulty_class,fixture["difficulty_class"])
                self.assertEqual(result.hardest_required_rating,fixture["hardest_required_level"])
                self.assertGreaterEqual(result.true_bottleneck_count,fixture["minimum_bottlenecks"])
                self.assertTrue(result.unique)

    def test_deep_fresh_cached_and_cache_disabled_identical(self):
        puzzle=list(map(int,EXTREME))
        analyzer=DifficultyAnalyzer()
        first=analyzer.deep(puzzle)
        self.assertEqual(first,analyzer.deep(puzzle))
        self.assertGreater(analyzer.state_analyzer.cache_hits,0)
        self.assertEqual(first,DifficultyAnalyzer(replace(DifficultyConfig(),cache_size=0)).deep(puzzle))

    def test_quick_and_human_deep_never_call_exact(self):
        puzzle=list(map(int,FIXTURES[0]["puzzle"]))
        with patch.object(exact_solver,"count_solutions",side_effect=AssertionError), \
             patch.object(exact_solver,"solve_one",side_effect=AssertionError):
            self.assertTrue(analyze_difficulty(puzzle,mode="quick").solved)
            self.assertTrue(analyze_difficulty(puzzle,check_unique=False).solved)
        root=Path(__file__).parents[1]/"rating"
        for path in root.glob("*.py"):
            if path.name=="precertification.py": continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.ImportFrom):
                    self.assertNotIn("exact_solver",node.module or "",str(path))

    def test_hash_seed_determinism(self):
        script="""
import hashlib,sys
from generator.rating.difficulty import analyze_difficulty
r=analyze_difficulty(list(map(int,sys.argv[1])),check_unique=False)
print(hashlib.sha256(repr(r).encode()).hexdigest())
"""
        outputs=[]
        for seed in ("1","902"):
            proc=subprocess.run([sys.executable,"-c",script,EXTREME],capture_output=True,text=True,
                check=True,env={**os.environ,"PYTHONHASHSEED":seed})
            outputs.append(proc.stdout)
        self.assertEqual(outputs[0],outputs[1])
