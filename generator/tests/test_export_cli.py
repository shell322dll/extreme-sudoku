"""Schema, atomic export and command-line failure contracts."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from generator.__main__ import main
from generator.config import GeneratorConfig
from generator.export import (ExportValidationError, build_database, export_puzzles,
                              puzzle_record, validate_database, validate_puzzle)
from generator.models import BatchResult, GenerationStats, RejectionReason
from generator.pipeline import generate_many, generate_puzzle
from generator.solver.exact_solver import count_solutions


TIMESTAMP = "2026-09-28T12:00:00Z"


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch = generate_many(2, GeneratorConfig(seed=42, min_clues=40, max_clues=40,
                                  require_minimal=False, max_attempts=3, rating_mode="quick"))
        if not cls.batch.complete:
            raise AssertionError("deterministic easy export fixture must complete")
        cls.puzzle = cls.batch.puzzles[0]

    def test_real_generation_export_roundtrip_and_frontend_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data" / "puzzles.json"
            database = export_puzzles(self.batch.puzzles, path, generated_at=TIMESTAMP)
            parsed = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(parsed, database)
        validate_database(parsed)
        self.assertEqual(parsed["schemaVersion"], 1)
        self.assertEqual(parsed["stats"]["total"], 2)
        self.assertEqual(len({item["id"] for item in parsed["puzzles"]}), 2)
        required = {"id", "puzzle", "solution", "clues", "difficulty", "unique"}
        for item in parsed["puzzles"]:
            self.assertTrue(required <= item.keys())
            self.assertEqual(count_solutions([int(c) for c in item["puzzle"]], 2), 1)

    def test_full_minimal_pipeline_roundtrip(self):
        puzzle = generate_puzzle(GeneratorConfig(seed=42, min_clues=17, max_clues=81,
                                  require_minimal=True, max_attempts=3, rating_mode="quick"))
        self.assertTrue(puzzle.minimal)
        self.assertTrue(puzzle.difficulty_result.solved)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "puzzles.json"
            export_puzzles([puzzle], path)
            validate_database(json.loads(path.read_text(encoding="utf-8")))

    def test_byte_stability_for_reversed_input_with_fixed_timestamp(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder) / "a.json", Path(folder) / "b.json"
            export_puzzles(self.batch.puzzles, first, generated_at=TIMESTAMP)
            export_puzzles(reversed(self.batch.puzzles), second, generated_at=TIMESTAMP)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertFalse(first.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertEqual(list(json.loads(first.read_text()))[:4],
                             ["schemaVersion", "generatedAt", "generatorVersion", "puzzles"])

    def test_quick_export_does_not_claim_mandatory_hardest(self):
        record = puzzle_record(self.puzzle)
        self.assertNotIn("hardestTechnique", record)
        self.assertNotIn("hardestRating", record["difficultyData"])
        self.assertEqual(record["ratingMetadata"]["mode"], "quick")
        self.assertEqual(record["ratingMetadata"]["observedHardestTechnique"], self.puzzle.difficulty_result.hardest_technique)

    def test_deep_export_uses_verified_required_instead_of_observed(self):
        difficulty = replace(self.puzzle.difficulty_result, mode="deep", required_level_verified=True,
                             hardest_required_technique="Hidden Single", hardest_required_rating=1.0,
                             hardest_technique="AIC", hardest_rating=30.0)
        record = puzzle_record(replace(self.puzzle, difficulty_result=difficulty))
        self.assertEqual(record["hardestTechnique"], "Hidden Single")
        self.assertEqual(record["difficultyData"]["hardestRating"], 1.0)
        self.assertEqual(record["ratingMetadata"]["observedHardestRating"], 30.0)

    def test_rejects_invalid_standard_fields(self):
        record = puzzle_record(self.puzzle)
        cases = {"id": "bad id", "puzzle": "0" * 80, "solution": "1" * 81,
                 "clues": 41, "unique": 1, "difficulty": "Unrated", "rating": float("nan"),
                 "minimal": 1, "hardestTechnique": "", "techniques": {"AIC": 0},
                 "difficultyData": {"advancedSteps": -1}}
        for field, value in cases.items():
            with self.subTest(field=field), self.assertRaises(ExportValidationError):
                validate_puzzle(dict(record, **{field: value}))
        for field in ("puzzle", "solution"):
            with self.subTest(non_ascii=field), self.assertRaises(ExportValidationError):
                validate_puzzle(dict(record, **{field: "１" * 81}))

    def test_rejects_givens_that_do_not_match_solution(self):
        record = puzzle_record(self.puzzle)
        cell = next(i for i, c in enumerate(record["puzzle"]) if c != "0")
        changed = list(record["puzzle"])
        changed[cell] = str(int(changed[cell]) % 9 + 1)
        record["puzzle"] = "".join(changed)
        with self.assertRaisesRegex(ExportValidationError, "do not match"):
            validate_puzzle(record)

    def test_rechecks_actual_uniqueness_and_minimality(self):
        record = puzzle_record(self.puzzle)
        with self.assertRaisesRegex(ExportValidationError, "exactly one solution"):
            validate_puzzle(dict(record, puzzle="0" * 81, clues=0))
        with self.assertRaisesRegex(ExportValidationError, "minimal=true"):
            validate_puzzle(dict(record, puzzle=record["solution"], clues=81, minimal=True))

    def test_rejects_duplicate_ids_and_exact_duplicate_grids(self):
        database = build_database(self.batch.puzzles, generated_at=TIMESTAMP)
        duplicate_id = deepcopy(database)
        duplicate_id["puzzles"][1]["id"] = duplicate_id["puzzles"][0]["id"]
        with self.assertRaisesRegex(ExportValidationError, "duplicate id"):
            validate_database(duplicate_id)
        duplicate_grid = deepcopy(database)
        duplicate_grid["puzzles"][1] = dict(duplicate_grid["puzzles"][0], id="different-id")
        with self.assertRaisesRegex(ExportValidationError, "duplicate puzzle"):
            validate_database(duplicate_grid)

    def test_rejects_bad_root_contract_and_nonfinite_optional_data(self):
        database = build_database([self.puzzle], generated_at=TIMESTAMP)
        cases = {"schemaVersion": True, "generatedAt": "2026-09-28", "generatorVersion": "latest",
                 "puzzles": {}, "extension": float("inf")}
        for field, value in cases.items():
            with self.subTest(field=field), self.assertRaises(ExportValidationError):
                validate_database(dict(database, **{field: value}))

    def test_validation_failure_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "puzzles.json"
            path.write_bytes(b"original")
            with self.assertRaises(ExportValidationError):
                export_puzzles([replace(self.puzzle, unique=False)], path)
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_atomic_replace_failure_preserves_existing_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "puzzles.json"
            path.write_bytes(b"original")
            with patch("generator.export.os.replace", side_effect=OSError("write failed")):
                with self.assertRaisesRegex(OSError, "write failed"):
                    export_puzzles([self.puzzle], path)
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_rejects_unsolved_and_inconsistent_rating_results(self):
        for changed in (replace(self.puzzle, difficulty="Hard"), replace(self.puzzle, rating=-1),
                        replace(self.puzzle, difficulty_result=replace(self.puzzle.difficulty_result, solved=False))):
            with self.subTest(puzzle=changed.id), self.assertRaises(ExportValidationError):
                build_database([changed])


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.puzzle = generate_puzzle(GeneratorConfig(seed=42, min_clues=40, max_clues=40,
                                     require_minimal=False, max_attempts=2, rating_mode="quick"))

    def invoke(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_legacy_seed_demo_is_retained(self):
        code, stdout, _ = self.invoke(["--seed", "42"])
        self.assertEqual(code, 0)
        self.assertIn("Phase 1 seed puzzle", stdout)
        self.assertIn("Unique: True", stdout)
        self.assertIn("Minimal: True", stdout)

    def test_real_generate_command_writes_json_and_shows_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "puzzles.json"
            code, stdout, stderr = self.invoke(["generate", "--seed", "42", "--count", "1",
                "--min-clues", "40", "--max-clues", "40", "--no-minimal", "--rating", "quick",
                "--max-attempts", "2", "--output", str(path)])
            self.assertEqual(code, 0, stderr)
            validate_database(json.loads(path.read_text(encoding="utf-8")))
        self.assertIn("Exported 1", stdout)
        self.assertIn("Accepted: 1/1", stderr)
        self.assertIn("Found: 1/1", stderr)

    def test_partial_batch_exports_only_accepted_and_returns_failure(self):
        stats = GenerationStats(attempts=3, accepted=1, rejections={RejectionReason.WRONG_DIFFICULTY: 2})
        batch = BatchResult((self.puzzle,), 2, 42, stats)
        with tempfile.TemporaryDirectory() as folder, patch("generator.__main__.generate_many", return_value=batch):
            path = Path(folder) / "puzzles.json"
            code, _, stderr = self.invoke(["generate", "--count", "2", "--output", str(path)])
            self.assertEqual(len(json.loads(path.read_text())["puzzles"]), 1)
        self.assertEqual(code, 1)
        self.assertIn("Found: 1/2", stderr)
        self.assertIn("WRONG_DIFFICULTY", stderr)

    def test_empty_batch_does_not_replace_existing_output(self):
        batch = BatchResult((), 1, 42, GenerationStats(attempts=2))
        with tempfile.TemporaryDirectory() as folder, patch("generator.__main__.generate_many", return_value=batch):
            path = Path(folder) / "puzzles.json"
            path.write_bytes(b"original")
            code, _, stderr = self.invoke(["generate", "--output", str(path)])
            self.assertEqual(path.read_bytes(), b"original")
        self.assertEqual(code, 1)
        self.assertIn("no accepted puzzles", stderr)

    def test_preliminary_archive_is_separate_from_acceptance(self):
        batch = BatchResult((), 1, 42, GenerationStats(attempts=1), (self.puzzle,))
        with tempfile.TemporaryDirectory() as folder, patch("generator.__main__.generate_many", return_value=batch):
            path = Path(folder) / "puzzles.json"
            code, stdout, _ = self.invoke(["generate", "--output", str(path)])
            self.assertFalse(path.exists())
            archive = path.with_name("puzzles_preliminary.json")
            validate_database(json.loads(archive.read_text()))
        self.assertEqual(code, 1)
        self.assertIn("Preliminary Extreme candidates", stdout)

    def test_invalid_configuration_and_export_error_return_nonzero(self):
        code, _, stderr = self.invoke(["generate", "--min-clues", "80", "--max-clues", "20"])
        self.assertEqual(code, 2)
        self.assertIn("Generation failed", stderr)
        batch = BatchResult((self.puzzle,), 1, 42, GenerationStats(attempts=1, accepted=1))
        with patch("generator.__main__.generate_many", return_value=batch), patch("generator.__main__.export_puzzles", side_effect=OSError("denied")):
            code, _, stderr = self.invoke(["generate"])
        self.assertEqual(code, 2)
        self.assertIn("denied", stderr)

    def test_count_timeout_and_difficulty_flags_reach_configuration(self):
        batch = BatchResult((), 2, 42, GenerationStats())
        with patch("generator.__main__.generate_many", return_value=batch) as generate:
            self.invoke(["generate", "--count", "2", "--seed", "42", "--difficulty", "Expert",
                         "--rating", "deep", "--minimal", "--max-attempts", "7", "--timeout", "2.5"])
        count, config = generate.call_args.args
        self.assertEqual((count, config.seed, config.target_difficulty, config.rating_mode,
                          config.require_minimal, config.max_attempts, config.timeout_seconds),
                         (2, 42, "Expert", "deep", True, 7, 2.5))


if __name__ == "__main__":
    unittest.main()
