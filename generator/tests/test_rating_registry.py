from dataclasses import replace
import json
import unittest
from generator.rating.config import DifficultyConfig
from generator.rating.registry import DEFAULT_REGISTRY, TechniqueRegistry, Tier
from generator.solver.techniques import DEFAULT_WEIGHTS, TECHNIQUE_TYPES

class RatingRegistryTests(unittest.TestCase):
    def test_legacy_values_and_order(self):
        self.assertEqual({e.name:e.base_rating for e in DEFAULT_REGISTRY.entries}, DEFAULT_WEIGHTS)
        self.assertEqual(DEFAULT_REGISTRY.rating_of("AIC"),30)
        self.assertEqual(DEFAULT_REGISTRY.tier_of("Swordfish"),Tier.ADVANCED)
        self.assertEqual(TechniqueRegistry(tuple(reversed(DEFAULT_REGISTRY.entries))),DEFAULT_REGISTRY)
        self.assertEqual(set(DEFAULT_WEIGHTS),{t.name for t in TECHNIQUE_TYPES})

    def test_duplicates_unknown_invalid(self):
        e=DEFAULT_REGISTRY.entries[0]
        with self.assertRaises(ValueError): TechniqueRegistry((e,e))
        with self.assertRaises(ValueError): DEFAULT_REGISTRY.get("missing")
        for value in (-1,float("nan"),float("inf"),True):
            with self.assertRaises(ValueError): replace(e,weight=value)

    def test_config_roundtrip(self):
        c=DifficultyConfig(chain_length_factor=2.2)
        self.assertEqual(c,DifficultyConfig.from_dict(json.loads(json.dumps(c.to_dict()))))
        for kw in ({"cache_size":1.1},{"late_fraction":2},{"ultra_threshold":1},
                   {"score_exponent":0},{"distribution_bins":0}):
            with self.assertRaises(ValueError): DifficultyConfig(**kw)
