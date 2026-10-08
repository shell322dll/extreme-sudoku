"""Only the derived aggregate rating tolerates one platform-dependent float step."""
from copy import deepcopy
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from generator.export import ExportValidationError
from generator.production.verification import (
    _first_metadata_difference, _metadata_differences, _standard_metadata_equal,
    _stats, validate_production_database, verify_standard)


class StandardMetadataDiagnosticsTests(unittest.TestCase):
    def test_exact_float_difference_identifies_the_leaf(self):
        saved = 9.507467369019215
        fresh = math.nextafter(saved, -math.inf)
        difference = _first_metadata_difference({'rating': saved}, {'rating': fresh})
        self.assertEqual(difference, f'$.rating: saved {saved!r}; fresh {fresh!r}')

    def test_proof_differences_are_diagnostic_and_type_sensitive(self):
        self.assertEqual(_first_metadata_difference({'proof': [True]}, {'proof': [1]}),
                         '$.proof[0]: saved True; fresh 1')
        self.assertEqual(_first_metadata_difference({'proof': [1]}, {'proof': [1, 2]}),
                         '$.proof: saved length 1; fresh length 2')
        self.assertIsNone(_first_metadata_difference({'a': 1}, {'a': 1}))

    def test_diagnostics_do_not_hide_a_second_nested_difference(self):
        actual = {'rating': 1.0, 'proof': {'threshold': 2.0}}
        expected = {'rating': 1.1, 'proof': {'threshold': 2.1}}
        self.assertEqual(list(_metadata_differences(actual, expected)), [
            '$.rating: saved 1.0; fresh 1.1', '$.proof.threshold: saved 2.0; fresh 2.1'])


class StandardMetadataPortabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        production = json.loads((root / 'data/production/puzzles.json').read_text(encoding='utf-8'))
        cls.saved = next(p for p in production['puzzles'] if p['id'] == 'puzzle-9e0e600550621e398036')
        cls.fresh = verify_standard(cls.saved['puzzle'], cls.saved['solution'], cls.saved['difficulty'],
                                    puzzle_id=cls.saved['id'])
        cls.base = dict(production, puzzles=[], stats=_stats([]))

    def validate_against(self, record, fresh):
        database = dict(self.base, puzzles=[record], stats=_stats([record]))
        # Fresh verification itself is independently exercised in setUpClass;
        # inject the other platform's sole floating result to test integration.
        with patch('generator.production.verification.verify_standard', return_value=fresh) as verifier:
            validate_production_database(database)
            verifier.assert_called_once_with(record['puzzle'], record['solution'], record['difficulty'],
                                             puzzle_id=record['id'])

    def test_observed_windows_linux_scores_pass_without_mutating_records(self):
        windows, linux = deepcopy(self.fresh), deepcopy(self.fresh)
        windows['rating'] = 9.507467369019215
        linux['rating'] = 9.507467369019214
        self.assertEqual(math.nextafter(windows['rating'], -math.inf), linux['rating'])
        before = deepcopy(windows)
        self.validate_against(windows, linux)
        self.validate_against(linux, windows)
        self.assertEqual(windows, before)

    def test_two_float_steps_and_material_rating_tampering_are_rejected(self):
        for direction in (-math.inf, math.inf):
            record = deepcopy(self.fresh)
            record['rating'] = math.nextafter(math.nextafter(record['rating'], direction), direction)
            with self.subTest(direction=direction), self.assertRaises(ExportValidationError):
                self.validate_against(record, self.fresh)
        record = deepcopy(self.fresh)
        record['rating'] += 0.001
        with self.assertRaises(ExportValidationError):
            self.validate_against(record, self.fresh)

    def test_no_type_coercion_or_nonfinite_numbers(self):
        self.assertFalse(_standard_metadata_equal({'rating': 1}, {'rating': 1.0}))
        self.assertFalse(_standard_metadata_equal({'rating': True}, {'rating': 1.0}))
        for invalid in (math.nan, math.inf, -math.inf):
            record = deepcopy(self.fresh)
            record['rating'] = invalid
            with self.subTest(value=invalid), self.assertRaises((ValueError, ExportValidationError)):
                self.validate_against(record, self.fresh)

    def test_even_one_float_step_in_threshold_score_or_proof_is_rejected(self):
        paths = [
            ('verification', 'requiredRating'), ('verification', 'techniqueCeiling'),
            ('difficultyData', 'hardestRating'), ('difficultyData', 'totalScore'),
            ('verification', 'evidence', 'thresholds', 0, 'max_rating'),
            ('verification', 'evidence', 'path', 0, 'rating'),
        ]
        for path in paths:
            record = deepcopy(self.fresh)
            # Even an otherwise allowable aggregate difference cannot mask evidence changes.
            record['rating'] = math.nextafter(record['rating'], math.inf)
            value = record
            for key in path[:-1]:
                value = value[key]
            value[path[-1]] = math.nextafter(value[path[-1]], math.inf)
            with self.subTest(path=path), self.assertRaises(ExportValidationError):
                self.validate_against(record, self.fresh)


if __name__ == '__main__':
    unittest.main()
