"""Real lower-tier verification and mixed production admission regressions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from generator.export import ExportValidationError
from generator.production.archive import content_id
from generator.production.batch import BatchOptions, run_batch
from generator.production.merge import merge_production, merge_order
from generator.production.verification import verify_standard, validate_production_database, _stats
from generator.rating.difficulty import DifficultyAnalyzer
from generator.solver.exact_solver import solve_one as exact_solve

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / 'web/tests/fixtures/production_standard.json').read_text(encoding='utf-8'))


def database(records):
    return dict(FIXTURE, puzzles=records, stats=_stats(records))


class StandardVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.easy = FIXTURE['puzzles'][0]
        cls.medium = FIXTURE['puzzles'][2]

    def test_easy_and_medium_classification_and_replay(self):
        for record in (self.easy, self.medium):
            with self.subTest(difficulty=record['difficulty']):
                result = verify_standard(record['puzzle'], record['solution'], record['difficulty'])
                self.assertEqual(result['id'], record['id'])
                self.assertEqual(result['verification'], record['verification'])
                self.assertNotIn('certification', result)
                self.assertEqual(result['verification']['status'], 'VERIFIED')
                self.assertEqual(result['solutionSteps'], sum(result['techniques'].values()))
                self.assertLessEqual(result['verification']['requiredRating'], result['verification']['techniqueCeiling'])

    def test_medium_cannot_masquerade_as_easy(self):
        with self.assertRaises(ExportValidationError):
            verify_standard(self.medium['puzzle'], self.medium['solution'], 'Easy')

    def test_easy_cannot_masquerade_as_medium(self):
        with self.assertRaises(ExportValidationError):
            verify_standard(self.easy['puzzle'], self.easy['solution'], 'Medium')

    def test_hard_cannot_masquerade_as_medium(self):
        fixtures = json.loads((ROOT / 'generator/tests/fixtures/difficulty/regression.json').read_text())
        puzzle = next(p['puzzle'] for p in fixtures if p['difficulty_class'] == 'Hard')
        analysis = DifficultyAnalyzer().deep(list(map(int, puzzle)), check_unique=True)
        self.assertEqual(analysis.difficulty_class, 'Hard')
        solution = ''.join(map(str, exact_solve(list(map(int, puzzle)))))
        with self.assertRaises(ExportValidationError):
            verify_standard(puzzle, solution, 'Medium')

    def test_standard_never_calls_extreme_minimax_certification(self):
        with patch('generator.certification.certify_puzzle', side_effect=AssertionError('Extreme certification called')):
            verify_standard(self.easy['puzzle'], self.easy['solution'], 'Easy')

    def test_full_grid_and_nonunique_puzzles_rejected(self):
        for puzzle in (self.easy['solution'], '0' * 81):
            with self.subTest(puzzle=puzzle), self.assertRaises(ExportValidationError):
                verify_standard(puzzle, self.easy['solution'], 'Easy')

    def test_bad_solution_id_and_format_rejected(self):
        for args in ((self.easy['puzzle'], '1' * 81, 'Easy'),
                     ('.' * 81, self.easy['solution'], 'Easy'),
                     (self.easy['puzzle'], self.easy['solution'], 'Hard')):
            with self.subTest(args=args), self.assertRaises(ExportValidationError):
                verify_standard(*args)
        with self.assertRaises(ExportValidationError):
            verify_standard(self.easy['puzzle'], self.easy['solution'], 'Easy', puzzle_id='wrong')

    def test_easy_medium_production_eligibility_and_future_fields(self):
        records = deepcopy([self.easy, self.medium])
        records[0]['futureField'] = {'optional': True}
        validate_production_database(database(records))

    def test_unverified_and_wrong_status_records_rejected(self):
        for status in (None, 'PRELIMINARY', 'INCONCLUSIVE', 'INVALID', 'CERTIFIED_EXTREME'):
            record = deepcopy(self.easy)
            if status is None:
                del record['verification']
            else:
                record['verification']['status'] = status
            with self.subTest(status=status), self.assertRaises(ExportValidationError):
                validate_production_database(database([record]))

    def test_wrong_flags_rating_and_proof_rejected(self):
        for key, value in (('guesses', 1), ('usedBacktracking', True), ('proofValidated', False),
                           ('requiredRating', 3), ('techniqueCeiling', 7)):
            record = deepcopy(self.easy)
            record['verification'][key] = value
            with self.subTest(key=key), self.assertRaises(ExportValidationError):
                validate_production_database(database([record]))
        for key in ('rating', 'solutionSteps'):
            record = deepcopy(self.easy)
            record[key] += 1
            with self.subTest(key=key), self.assertRaises(ExportValidationError):
                validate_production_database(database([record]))
        record = deepcopy(self.easy)
        record['verification']['evidence']['path'].pop()
        with self.assertRaises(ExportValidationError):
            validate_production_database(database([record]))

    def test_false_extreme_claim_and_wrong_difficulty_rejected(self):
        record = deepcopy(self.easy)
        record['certification'] = {'status': 'CERTIFIED_EXTREME'}
        with self.assertRaises(ExportValidationError):
            validate_production_database(database([record]))
        record = deepcopy(self.medium)
        record['difficulty'] = 'Easy'
        with self.assertRaises(ExportValidationError):
            validate_production_database(database([record]))

    def test_duplicate_and_wrong_stats_rejected(self):
        with self.assertRaises(ExportValidationError):
            validate_production_database(database([self.easy, self.easy]))
        db = database([self.easy])
        db['stats']['total'] = 2
        with self.assertRaises(ExportValidationError):
            validate_production_database(db)

    def test_mixed_database_keeps_extreme_validation(self):
        production = json.loads((ROOT / 'data/production/puzzles.json').read_text(encoding='utf-8'))
        extreme = next(p for p in production['puzzles'] if p['difficulty'] == 'Extreme')
        db = database([self.easy, self.medium, extreme])
        validate_production_database(db)
        invalid = deepcopy(db)
        invalid['puzzles'][2]['certification']['status'] = 'PRELIMINARY'
        with self.assertRaises(ExportValidationError):
            validate_production_database(invalid)
        for index, field in ((0, 'verification'), (1, 'verification'), (2, 'certification')):
            invalid = deepcopy(db)
            del invalid['puzzles'][index][field]
            with self.subTest(difficulty=db['puzzles'][index]['difficulty'], missing=field):
                with self.assertRaises(ExportValidationError):
                    validate_production_database(invalid)

    def test_standard_merge_fresh_validation_dry_run_duplicates_and_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'production/puzzles.json'
            path.parent.mkdir()
            original = (json.dumps(database([self.easy]), indent=2) + '\n').encode()
            path.write_bytes(original)
            candidate = deepcopy(self.medium)
            candidate['verification']['status'] = 'PRELIMINARY'  # ignored: fresh verification required
            dry = merge_production(path, [candidate], backup_dir=Path(folder) / 'backups', dry_run=True)
            self.assertEqual(dry.total, 2)
            self.assertFalse(dry.written)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((Path(folder) / 'backups').exists())
            result = merge_production(path, [candidate, self.easy], backup_dir=Path(folder) / 'backups')
            self.assertEqual(len(result.merged), 1)
            self.assertEqual(len(result.skipped), 1)
            actual = json.loads(path.read_text())
            self.assertEqual(next(p for p in actual['puzzles'] if p['id'] == self.easy['id']), self.easy)
            self.assertEqual(Path(result.backup).read_bytes(), original)
            path.write_bytes(original)
            with patch('generator.production.merge.atomic_json', side_effect=OSError('write failed')):
                from generator.production.merge import MergeError
                with self.assertRaises(MergeError):
                    merge_production(path, [candidate], backup_dir=Path(folder) / 'backups')
            self.assertEqual(path.read_bytes(), original)

    def test_seeded_standard_batch_uses_existing_generator_and_research_only(self):
        with tempfile.TemporaryDirectory() as folder:
            production = Path(folder) / 'production/puzzles.json'
            production.parent.mkdir()
            production.write_text(json.dumps(database([])))
            before = production.read_bytes()
            options = BatchOptions(difficulty='Easy', seeds=(10101,), per_seed_count=1,
                                   target_new=1, min_clues=35, max_clues=45, minimal=False,
                                   max_attempts=10, production=production, run_dir=Path(folder) / 'run')
            report = run_batch(options, log=lambda _: None)
            self.assertTrue(report['complete'])
            self.assertEqual(len(report['selected']), 1)
            self.assertEqual(report['selected'][0]['id'], content_id(report['selected'][0]['puzzle']))
            self.assertEqual(production.read_bytes(), before)
            self.assertEqual(merge_order([dict(report['selected'][0], selected=True)]),
                             [dict(report['selected'][0], selected=True)])


if __name__ == '__main__':
    unittest.main()
