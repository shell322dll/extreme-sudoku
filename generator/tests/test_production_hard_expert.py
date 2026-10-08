"""Hard/Expert admission uses the existing Deep classification and proof path."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from generator.export import ExportValidationError
from generator.production.batch import BatchOptions, run_batch
from generator.production.cli import batch_main
from generator.production.merge import merge_production
from generator.production.verification import (
    technique_ceiling, verify_standard, validate_production_database, _stats)
from generator.rating.config import DifficultyConfig
from generator.solver.exact_solver import solve_one

ROOT = Path(__file__).resolve().parents[2]


class HardExpertProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = json.loads((ROOT / 'web/tests/fixtures/production_standard.json').read_text())
        cls.records = {}
        fixtures = json.loads((ROOT / 'generator/tests/fixtures/difficulty/regression.json').read_text())
        cls.fixtures = {p['difficulty_class']: p['puzzle'] for p in fixtures}
        for difficulty in ('Hard', 'Expert'):
            puzzle = cls.fixtures[difficulty]
            solution = ''.join(map(str, solve_one(list(map(int, puzzle)))))
            cls.records[difficulty] = verify_standard(puzzle, solution, difficulty)

    def database(self, records):
        return dict(self.base, puzzles=records, stats=_stats(records))

    def test_real_hard_expert_paths_and_existing_metadata(self):
        for difficulty, required, ceiling in (('Hard', 10, 11), ('Expert', 14, 55)):
            record = self.records[difficulty]
            self.assertEqual(record['verification']['requiredRating'], required)
            self.assertEqual(record['verification']['techniqueCeiling'], ceiling)
            self.assertNotIn('certification', record)
            validate_production_database(self.database([record]))
        for old in self.base['puzzles']:
            fresh = verify_standard(old['puzzle'], old['solution'], old['difficulty'])
            self.assertEqual(fresh['verification'], old['verification'])

    def test_ceiling_follows_registry_not_an_arbitrary_expert_band(self):
        config = DifficultyConfig()
        self.assertEqual([technique_ceiling(d, config) for d in ('Easy', 'Medium', 'Hard', 'Expert')],
                         [1.2, 5.2, 11, max(e.base_rating for e in config.registry.entries)])
        with self.assertRaises(ExportValidationError):
            technique_ceiling('Extreme')

    def test_real_expert_with_aic_is_not_arbitrarily_excluded(self):
        # Phase 11, seed 11201..11203: one bottleneck fails Extreme's gates
        # despite a required AIC step. Preserve the existing Expert classifier.
        puzzle = '200000190000000003000008000706100000049020050820600900070004308000560000004000006'
        solution = ''.join(map(str, solve_one(list(map(int, puzzle)))))
        record = verify_standard(puzzle, solution, 'Expert')
        self.assertEqual(record['verification']['requiredRating'], 30)
        self.assertEqual(record['difficultyData']['trueBottlenecks'], 1)
        self.assertEqual(record['hardestTechnique'], 'AIC')
        self.assertNotIn('certification', record)

    def test_wrong_declared_classes_and_extreme_downgrade_rejected(self):
        for source, declared in (('Easy', 'Hard'), ('Hard', 'Expert'), ('Expert', 'Hard'),
                                 ('Extreme', 'Expert')):
            puzzle = self.fixtures[source]
            solution = ''.join(map(str, solve_one(list(map(int, puzzle)))))
            with self.subTest(source=source, declared=declared), self.assertRaises(ExportValidationError):
                verify_standard(puzzle, solution, declared)

    def test_forged_metadata_and_proof_fail_fresh_validation(self):
        for difficulty in ('Hard', 'Expert'):
            for mutate in ('proof', 'rating', 'ceiling', 'status', 'certification'):
                record = deepcopy(self.records[difficulty])
                if mutate == 'proof':
                    record['verification']['evidence']['path'].pop()
                elif mutate == 'rating':
                    record['verification']['requiredRating'] += 1
                elif mutate == 'ceiling':
                    record['verification']['techniqueCeiling'] = 30
                elif mutate == 'status':
                    record['verification']['status'] = 'PRELIMINARY'
                else:
                    record['certification'] = {'status': 'CERTIFIED_EXTREME'}
                with self.subTest(difficulty=difficulty, mutation=mutate), self.assertRaises(ExportValidationError):
                    validate_production_database(self.database([record]))

    def test_cli_and_batch_route_both_levels_to_standard_verifier(self):
        for difficulty in ('Hard', 'Expert'):
            options = BatchOptions(seeds=(11101,), difficulty=difficulty)
            options.validate()
            with patch('generator.production.standard_batch.run_standard_batch', return_value='standard') as standard:
                self.assertEqual(run_batch(options), 'standard')
                standard.assert_called_once()
            def run(received):
                self.assertEqual(received.difficulty, difficulty)
                return dict(runId='test', selected=[], runDir='unused', archive=None, complete=True)
            self.assertEqual(batch_main(['--difficulty', difficulty, '--seeds', '11101'], run=run), 0)

    def test_merge_reverifies_and_preserves_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'production' / 'puzzles.json'
            path.parent.mkdir()
            old = self.base['puzzles'][0]
            original = (json.dumps(self.database([old]), indent=2) + '\n').encode()
            path.write_bytes(original)
            records = deepcopy(list(self.records.values()))
            for record in records:
                record['verification']['status'] = 'PRELIMINARY'
            dry = merge_production(path, records, backup_dir=Path(folder) / 'backups', dry_run=True)
            self.assertEqual(len(dry.merged), 2)
            self.assertEqual(path.read_bytes(), original)
            result = merge_production(path, records, backup_dir=Path(folder) / 'backups')
            self.assertEqual(len(result.merged), 2)
            self.assertEqual(Path(result.backup).read_bytes(), original)
            actual = json.loads(path.read_text())
            self.assertEqual(next(p for p in actual['puzzles'] if p['id'] == old['id']), old)
            self.assertEqual(actual['stats']['byDifficulty'], {'Easy': 1, 'Expert': 1, 'Hard': 1})


if __name__ == '__main__':
    unittest.main()
