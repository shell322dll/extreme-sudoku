"""Production boundary tests use actual certification, never fake accepted flags."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from generator.__main__ import main
from generator.certification import CertificationConfig, certify_puzzle
from generator.certification.io import (BatchFailureReason, atomic_json, certify_batch,
    export_production, load_candidates, read_json, validate_production_database, _stable_record)
from generator.export import ExportValidationError


ROOT = Path(__file__).resolve().parents[2]
DEMO = json.loads((ROOT / "data/puzzles.json").read_text(encoding="utf-8-sig"))["puzzles"][0]


class CertificationIOTests(unittest.TestCase):
    def test_all_duplicate_ids_and_exact_grids_rejected_before_solver(self):
        first = deepcopy(DEMO)
        second = {**first, "id": "another-id"}
        third = {**first, "puzzle": first["solution"], "clues": 81}
        with patch("generator.certification.io.certify_puzzle", side_effect=AssertionError("duplicate reached solver")):
            entries = certify_batch([first, second, third])
        self.assertEqual([entry.reason for entry in entries], [BatchFailureReason.DUPLICATE] * 3)

    def test_bad_objects_ids_and_clue_counts_are_structured_rejections(self):
        entries = certify_batch([None, {**DEMO, "id": "../escape"}, {**DEMO, "clues": True}])
        self.assertTrue(all(entry.reason == BatchFailureReason.INVALID_FORMAT for entry in entries))

    def test_stale_certified_flags_cannot_publish_actual_easy_grid(self):
        record = {**DEMO, "puzzle": DEMO["solution"], "clues": 81,
                  "difficulty": "Ultra Extreme", "certification": {"status": "CERTIFIED_ULTRA_EXTREME",
                  "searchConclusive": True, "proofValidated": True}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "production.json"
            database, research = export_production([record], path)
            self.assertEqual(database["puzzles"], [])
            self.assertEqual(research["stats"]["certified"], 0)
            self.assertEqual(read_json(path), database)
            validate_production_database(database)

    def test_timeout_preserves_id_in_research_and_never_enters_production(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            database, research = export_production([DEMO], folder / "production.json",
                config=CertificationConfig(time_budget=0), research_path=folder / "research.json",
                reports_dir=folder / "reports")
            self.assertEqual(database["puzzles"], [])
            certificate = research["candidates"][0]["certification"]
            self.assertEqual(certificate["puzzle_id"], DEMO["id"])
            self.assertEqual(certificate["status"], "CERTIFICATION_TIMEOUT")
            self.assertEqual(load_candidates(folder / "research.json"), [DEMO])
            self.assertEqual(len(list((folder / "reports").glob("*.json"))), 1)

    def test_metadata_claim_alone_is_not_a_certificate(self):
        database = {"schemaVersion": 1, "generatorVersion": "0.5.0", "generatedAt": "2026-09-30T00:00:00Z",
                    "datasetKind": "production-certified", "puzzles": [{**DEMO, "certification": {
                        "status": "CERTIFIED_EXTREME", "proofValidated": True,
                        "searchConclusive": True, "config": CertificationConfig(time_budget=0).to_dict()}}]}
        with self.assertRaises(ExportValidationError):
            validate_production_database(database)

    def test_atomic_validation_failure_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "result.json"
            path.write_text("old", encoding="utf-8")
            checks = []
            def validate(value):
                checks.append(value)
                if len(checks) == 2:
                    raise ValueError("readback rejected")
            with self.assertRaises(ValueError):
                atomic_json(path, {"valid": True}, validator=validate)
            self.assertEqual(path.read_text(), "old")
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_atomic_readback_accepts_dataclass_proof_tuple_serialization(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "proof.json"
            atomic_json(path, {"proof": {"placements": ((0, 1),), "premises": ((0, (1,)),)}})
            self.assertEqual(read_json(path)["proof"]["placements"], [[0, 1]])

    def test_metadata_identity_preserves_json_types_with_real_fresh_evidence(self):
        # This real easy result is not an accepted certificate. It exercises the
        # exact metadata comparator used after fresh production re-certification.
        result = certify_puzzle(DEMO["solution"], puzzle_id="real-evidence")
        original = {"certification": {"proofValidated": result.proof_valid,
                    "requiredRating": result.minimum_required_rating,
                    "evidence": result.to_dict()}}
        decoded = json.loads(json.dumps(original))
        self.assertEqual(_stable_record(original), _stable_record(decoded))
        timing = deepcopy(decoded)
        timing["certification"]["evidence"]["elapsed_seconds"] += 10
        self.assertEqual(_stable_record(original), _stable_record(timing))
        for field, replacement in (("proofValidated", 1), ("requiredRating", False)):
            tampered = deepcopy(decoded)
            tampered["certification"][field] = replacement
            self.assertNotEqual(_stable_record(original), _stable_record(tampered))
        for field, replacement in (("unique", 1), ("certified_bottlenecks", False)):
            tampered = deepcopy(decoded)
            tampered["certification"]["evidence"][field] = replacement
            self.assertNotEqual(_stable_record(original), _stable_record(tampered))

    def test_empty_production_statistics_reject_boolean_as_integer(self):
        with tempfile.TemporaryDirectory() as folder:
            database, _ = export_production([], Path(folder) / "empty.json")
            validate_production_database(database)
            database["stats"]["total"] = False
            with self.assertRaises(ExportValidationError):
                validate_production_database(database)

    def test_nonfinite_numbers_duplicate_json_keys_and_schema_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            for text in ('{"value":NaN}', '{"puzzles":[],"puzzles":[]}', '{"schemaVersion":2,"puzzles":[]}',
                         '{"schemaVersion":true,"puzzles":[]}'):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_candidates(path)

    def test_cli_rejects_input_output_alias_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.json"
            text = json.dumps({"puzzles": [DEMO]})
            path.write_text(text, encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                code = main(["certify", "--input", str(path), "--output", str(path)])
            self.assertEqual(code, 2)
            self.assertEqual(path.read_text(), text)

    def test_cli_single_string_and_id_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / "source.json"
            source.write_text(json.dumps({"puzzles": [DEMO]}), encoding="utf-8")
            common = ["--time-budget", "0", "--fresh", "--output", str(folder / "production.json"),
                      "--research-output", str(folder / "research.json"), "--reports-dir", str(folder / "reports")]
            for selector in (["--input", str(source), "--puzzle-id", DEMO["id"]],
                             ["--puzzle", DEMO["puzzle"], "--puzzle-id", "stable-direct-id"]):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["certify", *selector, *common]), 1)
                report = read_json(folder / "research.json")
                self.assertEqual(report["stats"]["input"], 1)
                self.assertEqual(report["candidates"][0]["certification"]["puzzle_id"], selector[-1])


if __name__ == "__main__":
    unittest.main()
