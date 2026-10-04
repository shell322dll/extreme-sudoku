"""Phase 9 content production: suitability, diversity, archive, batch and safe merge.

Most tests use fake certifier results (fast, deterministic). The real certifier
is used only where the contract is about real certificates: a multi-puzzle
production merge that must pass ``validate_production_database``.
"""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import fields, replace
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from generator.__main__ import main
from generator.certification import (CertificationConfig, CertificationResult, CertificationStatus,
                                     FailureReason, SearchStatus)
from generator.certification.io import load_candidates, read_json, validate_production_database
from generator.certification.pipeline import algorithm_fingerprint
from generator.export import ExportValidationError, validate_database
from generator.models import RejectionReason
from generator.production import batch as batch_module
from generator.models import GENERATOR_VERSION
from generator.production.archive import Archive, ArchiveLockedError, archive_lock, content_id, is_terminal
from generator.production.batch import BatchOptions, generate_seed, recompute_report, run_batch
from generator.production.cli import batch_main, merge_main
from generator.production.diversity import (DiversityIndex, is_mask_near, mask_distance,
                                            symmetry_fingerprint, technique_similarity)
from generator.production.merge import MergeError, merge_order, merge_production
from generator.production.models import (FAILURE_REASON, GENERATOR_REASON, NOT_ATTEMPTED, Phase9Reason,
                                         reason_for_result, reason_for_status)
from generator.production.suitability import (SuitabilityAssessment, assess_suitability, priority_key)
from generator.production.verification import verify_standard

ROOT = Path(__file__).resolve().parents[2]
# Frozen byte copy of the 1-record production DB at Phase 9 start (HEAD eb1b9b6).
# Merge/batch tests use it so that growing the live database never changes them.
PRODUCTION = Path(__file__).resolve().parent / "fixtures" / "production_baseline.json"
PRODUCTION_SHA256 = "ba44f37a58f4d967f55e52b46bc70dcba268b217e64b68c22215cbfd055e0115"
# The live DB is only inspected by ID (override to rehearse a merged database).
LIVE_PRODUCTION = Path(os.environ.get("EXTREME_SUDOKU_PRODUCTION_DB", ROOT / "data/production/puzzles.json"))
EXISTING_ID = "puzzle-8e2b144cecb50551d96b"
# Real Phase 9 probe hits (certified in < 1 s by the unchanged default certifier).
A_PUZZLE = "000047008000090013090000750050000000300000009008360400080006007004902030103070900"
A_SOLUTION = "631547298745298613892613754457829361316754829928361475289136547574982136163475982"
B_PUZZLE = "509603000200100000000000090050000270020509036806002009000030007040000600003070050"
B_SOLUTION = "519683742274195368368427195951368274427519836836742519195836427742951683683274951"
# Two different puzzles on one solution (evolution near-clones).
C_PUZZLE = "300000500000000070980007040000030006401800003000046090050200060140005030070600900"
D_PUZZLE = "300400589000000070980007040000030006401809003002006000850000160100005030070000900"
CD_SOLUTION = "327461589614598372985327641598732416461859723732146895859273164146985237273614958"
DEFAULT = CertificationConfig()
ALGORITHM = algorithm_fingerprint()


def features(required=30.0, **extra):
    value = {"requiredRating": required, "difficulty": "Extreme", "mode": "deep",
             "requiredLevelVerified": True, "humanSolved": True, "observedHardestRating": required,
             "trueBottlenecks": 4, "advancedSteps": 9, "longestChain": 8, "alsSteps": 0,
             "forcingSteps": 0, "clues": 25, "minimal": True}
    value.update(extra)
    return value


def fake_result(puzzle, solution, *, config=DEFAULT, status=CertificationStatus.CERTIFIED_EXTREME,
                reasons=(), minimum=30.0, elapsed=1.0):
    certified = status in (CertificationStatus.CERTIFIED_EXTREME, CertificationStatus.CERTIFIED_ULTRA_EXTREME)
    return CertificationResult(
        puzzle_id=content_id(puzzle), puzzle=puzzle, solution=solution,
        clues=sum(c != "0" for c in puzzle), status=status, unique=True, minimal=False,
        human_solved=True, proof_valid=certified, reproducible=True,
        search_status=SearchStatus.SOLVED if certified else SearchStatus.INCONCLUSIVE_BUDGET,
        minimum_required_rating=minimum if certified else None, elapsed_seconds=elapsed,
        failure_reasons=list(reasons), config_fingerprint=config.fingerprint(),
        algorithm_fingerprint=ALGORITHM)


def entry(puzzle, solution, seed=1, attempt=1, **deep):
    return {"id": content_id(puzzle), "puzzle": puzzle, "solution": solution,
            "clues": sum(c != "0" for c in puzzle), "minimal": False,
            "source": {"kind": "generate", "seed": seed, "attemptSeed": attempt, "attempt": attempt, "runId": "t"},
            "deep": features(clues=sum(c != "0" for c in puzzle), **deep)}


def checkpoint(options, seed, entries):
    return {"kind": batch_module.CHECKPOINT_KIND, "params": batch_module._generator_params(options, seed),
            "seed": seed, "complete": True, "timedOut": False, "seconds": 0.1, "attempts": 10 + len(entries),
            "unique": 9 + len(entries), "deepRated": len(entries) + 1, "attemptRejections": {"TOO_EASY": 9},
            "entries": entries}


def relabel(puzzle, mapping):
    return "".join(mapping[c] if c != "0" else "0" for c in puzzle)


def transpose(puzzle):
    return "".join(puzzle[c * 9 + r] for r in range(9) for c in range(9))


def swap_bands(puzzle):
    rows = [puzzle[r * 9:r * 9 + 9] for r in range(9)]
    return "".join(rows[3:6] + rows[0:3] + rows[6:9])


class SuitabilityTests(unittest.TestCase):
    def test_band_preference_30_over_32_over_35(self):
        scores = [assess_suitability(features(r)).score for r in (30.0, 32.0, 35.0)]
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[1], scores[2])

    def test_skip_reasons(self):
        high = assess_suitability(features(39.0))
        self.assertFalse(high.eligible)
        self.assertEqual(high.skip_reason, Phase9Reason.OUT_OF_CONCLUSIVE_SCOPE)
        self.assertTrue(assess_suitability(features(36.0), include_high=True).eligible)
        self.assertEqual(assess_suitability(features(25.0)).skip_reason, Phase9Reason.TOO_EASY)
        self.assertEqual(assess_suitability(features(30.0, difficulty="Hard")).skip_reason, Phase9Reason.TOO_EASY)
        self.assertEqual(assess_suitability(features(30.0, requiredLevelVerified=False)).skip_reason,
                         Phase9Reason.HUMAN_UNSOLVED)
        self.assertEqual(assess_suitability(features(30.0, humanSolved=False)).skip_reason,
                         Phase9Reason.HUMAN_UNSOLVED)

    def test_score_never_carries_or_implies_a_certification_status(self):
        names = {f.name for f in fields(SuitabilityAssessment)}
        self.assertFalse(names & {"status", "certified", "certification", "production_eligible"})
        for required in (25.0, 30.0, 35.0, 39.0):
            value = assess_suitability(features(required)).to_dict()
            self.assertFalse(set(value) & {"status", "certified", "certification"})
            self.assertNotIn("CERTIFIED", json.dumps(value))

    def test_deterministic_tie_break_by_id(self):
        items = [{"id": "puzzle-b", "suitability": {"score": 5.0}}, {"id": "puzzle-a", "suitability": {"score": 5.0}},
                 {"id": "puzzle-c", "suitability": {"score": 9.0}}]
        self.assertEqual([i["id"] for i in sorted(items, key=priority_key)], ["puzzle-c", "puzzle-a", "puzzle-b"])


class RejectionMappingTests(unittest.TestCase):
    def test_every_failure_and_generator_reason_is_mapped(self):
        self.assertEqual(set(FAILURE_REASON), set(FailureReason))
        self.assertEqual(set(GENERATOR_REASON), set(RejectionReason))

    def test_statuses_map_without_upgrading_budget_outcomes(self):
        for status in CertificationStatus:
            mapped = reason_for_status(status)
            if status.value.startswith("CERTIFIED_"):
                self.assertIsNone(mapped)
            else:
                self.assertIsInstance(mapped, Phase9Reason)
        self.assertEqual(reason_for_status("CERTIFICATION_TIMEOUT", ["SEARCH_TIMEOUT"]),
                         Phase9Reason.CERTIFICATION_TIMEOUT)
        self.assertEqual(reason_for_status("SEARCH_INCONCLUSIVE", ["SEARCH_INCONCLUSIVE"]),
                         Phase9Reason.CERTIFICATION_INCONCLUSIVE)
        self.assertEqual(reason_for_status("INVALID_PROOF", ["INVALID_LOGIC_PROOF"]), Phase9Reason.PROOF_INVALID)
        self.assertEqual(reason_for_status("REJECTED", ["NOT_UNIQUE"]), Phase9Reason.NOT_UNIQUE)
        self.assertEqual(reason_for_status("REJECTED", ["RATING_BELOW_EXTREME"]), Phase9Reason.TOO_EASY)
        self.assertEqual(reason_for_status("UNRATED", ["HUMAN_UNSOLVED"]), Phase9Reason.HUMAN_UNSOLVED)
        # A certified label carrying a failure reason is never a success.
        self.assertIsNotNone(reason_for_status("CERTIFIED_EXTREME", ["SEARCH_TIMEOUT"]))
        self.assertIsNone(reason_for_result(fake_result(A_PUZZLE, A_SOLUTION)))
        timeout = fake_result(A_PUZZLE, A_SOLUTION, status=CertificationStatus.CERTIFICATION_TIMEOUT,
                              reasons=[FailureReason.SEARCH_TIMEOUT])
        self.assertEqual(reason_for_result(timeout), Phase9Reason.CERTIFICATION_TIMEOUT)


class DiversityTests(unittest.TestCase):
    def test_exact_and_id_duplicates(self):
        index = DiversityIndex()
        index.add({"id": content_id(A_PUZZLE), "puzzle": A_PUZZLE, "solution": A_SOLUTION}, "production")
        self.assertEqual(index.check({"id": content_id(A_PUZZLE), "puzzle": A_PUZZLE, "solution": A_SOLUTION})[0],
                         Phase9Reason.DUPLICATE)
        self.assertEqual(index.exact_duplicate({"id": content_id(A_PUZZLE), "puzzle": B_PUZZLE})[0],
                         Phase9Reason.DUPLICATE)
        self.assertIsNone(index.check({"id": content_id(B_PUZZLE), "puzzle": B_PUZZLE, "solution": B_SOLUTION}))

    def test_mask_distance_boundary_8_vs_9_and_other_solution(self):
        givens = [i for i, c in enumerate(A_PUZZLE) if c != "0"]
        def blank(count):
            cells = set(givens[:count])
            return "".join("0" if i in cells else c for i, c in enumerate(A_PUZZLE))
        base = {"puzzle": A_PUZZLE, "solution": A_SOLUTION}
        self.assertEqual(mask_distance(A_PUZZLE, blank(8)), 8)
        self.assertTrue(is_mask_near(base, {"puzzle": blank(8), "solution": A_SOLUTION}))
        self.assertFalse(is_mask_near(base, {"puzzle": blank(9), "solution": A_SOLUTION}))
        self.assertFalse(is_mask_near(base, {"puzzle": blank(1), "solution": B_SOLUTION}))
        index = DiversityIndex(one_per_solution=False)
        index.add({"id": "x", **base}, "production")
        self.assertEqual(index.near_duplicate({"id": "y", "puzzle": blank(8), "solution": A_SOLUTION})[0],
                         Phase9Reason.NEAR_DUPLICATE)
        policy = DiversityIndex()
        policy.add({"id": "x", "puzzle": C_PUZZLE, "solution": CD_SOLUTION}, "production")
        self.assertGreater(mask_distance(C_PUZZLE, D_PUZZLE), 8)
        self.assertIn("one puzzle per solution",
                      policy.near_duplicate({"id": "y", "puzzle": D_PUZZLE, "solution": CD_SOLUTION})[1])

    def test_symmetry_fingerprint_invariants(self):
        mapping = dict(zip("123456789", "918273645"))
        reference = symmetry_fingerprint(A_PUZZLE)
        for variant in (transpose(A_PUZZLE), swap_bands(A_PUZZLE), relabel(A_PUZZLE, mapping),
                        transpose(swap_bands(relabel(A_PUZZLE, mapping)))):
            self.assertEqual(symmetry_fingerprint(variant), reference)
        self.assertNotEqual(symmetry_fingerprint(B_PUZZLE), reference)
        index = DiversityIndex()
        index.add({"id": "a", "puzzle": A_PUZZLE, "solution": A_SOLUTION}, "production")
        moved = transpose(A_PUZZLE)
        self.assertEqual(index.check({"id": "t", "puzzle": moved, "solution": transpose(A_SOLUTION)})[0],
                         Phase9Reason.NEAR_DUPLICATE)

    def test_technique_similarity_is_only_a_warning(self):
        index = DiversityIndex()
        index.add({"id": "a", "puzzle": A_PUZZLE, "solution": A_SOLUTION, "clues": 27,
                   "techniques": {"AIC": 3, "Naked Single": 30}}, "production")
        other = {"id": "b", "puzzle": B_PUZZLE, "solution": B_SOLUTION, "clues": 27,
                 "techniques": {"AIC": 3, "Naked Single": 30}}
        self.assertAlmostEqual(technique_similarity(other["techniques"], other["techniques"]), 1.0)
        self.assertEqual(len(index.technique_warnings(other)), 1)
        self.assertIsNone(index.check(other))
        self.assertEqual(index.technique_warnings({**other, "clues": 26}), [])


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def test_round_trip_and_separation_from_production_formats(self):
        archive = Archive.load(self.folder / "a.json")
        archive.upsert({**entry(A_PUZZLE, A_SOLUTION), "certification": {"status": NOT_ATTEMPTED}})
        archive.upsert({**entry(A_PUZZLE, A_SOLUTION), "selected": False, "certification": {"status": NOT_ATTEMPTED}})
        archive.save(fingerprints={"algorithmFingerprint": "x"})
        loaded = Archive.load(self.folder / "a.json")
        self.assertEqual(len(loaded.candidates), 1)
        self.assertEqual(loaded.fingerprints, {"algorithmFingerprint": "x"})
        raw = read_json(self.folder / "a.json")
        self.assertNotIn("puzzles", raw)
        self.assertNotIn("datasetKind", raw)
        with self.assertRaises(ValueError):
            load_candidates(self.folder / "a.json")
        with self.assertRaises(ExportValidationError):
            validate_database(raw)
        bad = self.folder / "bad.json"
        bad.write_text(json.dumps({**raw, "candidates": [{**raw["candidates"][0], "puzzle": B_PUZZLE}]}), encoding="utf-8")
        with self.assertRaises(ValueError):
            Archive.load(bad)
        with self.assertRaises(ValueError):
            Archive.load(PRODUCTION)

    def test_terminal_only_with_matching_fingerprints(self):
        keys = dict(default_fingerprint="D", probe_fingerprint="P", algorithm_fingerprint="A")
        final = {"certification": {"status": "CERTIFIED_EXTREME", "configFingerprint": "D", "algorithmFingerprint": "A"}}
        self.assertTrue(is_terminal(final, **keys))
        self.assertFalse(is_terminal(final, **{**keys, "algorithm_fingerprint": "B"}))
        probe = {"probe": {"status": "CERTIFICATION_TIMEOUT", "productionEligible": False,
                           "configFingerprint": "P", "algorithmFingerprint": "A"}}
        self.assertTrue(is_terminal(probe, **keys))
        self.assertFalse(is_terminal(probe, **keys, retry_timeouts=True))
        self.assertFalse(is_terminal(probe, **{**keys, "probe_fingerprint": "Q"}))
        verdict = {"reason": "TOO_EASY", "algorithmFingerprint": "A", "generatorVersion": GENERATOR_VERSION}
        self.assertTrue(is_terminal({"stage": "generation", "rejection": verdict}, **keys))
        # Content verdicts are re-evaluated after any algorithm or generator change.
        self.assertFalse(is_terminal({"stage": "generation", "rejection": {"reason": "TOO_EASY"}}, **keys))
        self.assertFalse(is_terminal({"stage": "generation", "rejection": verdict},
                                     **{**keys, "algorithm_fingerprint": "B"}))
        self.assertFalse(is_terminal({"stage": "generation", "rejection": {**verdict, "generatorVersion": "0.0.1"}},
                                     **keys))
        self.assertFalse(is_terminal({"stage": "generation", "rejection": {**verdict, "reason": "OUTSIDE_CLUE_RANGE"}},
                                     **keys))
        for reason in ("NOT_SELECTED_TARGET_REACHED", "NOT_SELECTED_BUDGET", "OUT_OF_CONCLUSIVE_SCOPE", "DUPLICATE"):
            self.assertFalse(is_terminal({"stage": "prefilter", "rejection": {"reason": reason}}, **keys))


class GenerationReproducibilityTests(unittest.TestCase):
    def test_same_seed_same_candidates_and_seeds_differ(self):
        options = BatchOptions(seeds=(11, 12), per_seed_count=1, max_attempts=3, generation_seconds=None)
        first = [generate_seed(options, seed, run_id="r") for seed in options.seeds]
        second = [generate_seed(options, seed, run_id="r") for seed in options.seeds]
        strip = lambda rows: [{k: v for k, v in row.items() if k != "seconds"} for row in rows]
        self.assertEqual(strip(first), strip(second))
        self.assertEqual([row["attempts"] for row in first], [3, 3])
        ids = [{e["id"] for e in row["entries"]} for row in first]
        self.assertTrue(all(ids))
        self.assertFalse(ids[0] & ids[1])
        for row in first:
            for item in row["entries"]:
                self.assertEqual(item["id"], content_id(item["puzzle"]))
                self.assertTrue("deep" in item or item["rejection"]["reason"] in {r.value for r in Phase9Reason})


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.calls = []

    def options(self, **extra):
        values = dict(seeds=(1, 2), archive=self.folder / "archive.json", run_dir=self.folder / "run",
                      production=PRODUCTION, probe_seconds=15.0, shortlist=10, target_new=10, runtime_budget=None)
        values.update(extra)
        return BatchOptions(**values)

    def certify(self, outcomes):
        def run(puzzle, solution=None, *, puzzle_id=None, config=None, fresh=True):
            self.assertTrue(fresh)
            self.calls.append((puzzle_id, config.time_budget))
            status, elapsed = outcomes.get((puzzle, config.time_budget), (CertificationStatus.CERTIFIED_EXTREME, 1.0))
            reasons = [] if status.value.startswith("CERTIFIED") else [FailureReason.SEARCH_TIMEOUT]
            return fake_result(puzzle, solution, config=config, status=status, reasons=reasons, elapsed=elapsed)
        return run

    def fake_generation(self, by_seed):
        def generate(options, seed, *, timeout=None, run_id=""):
            return checkpoint(options, seed, by_seed.get(seed, []))
        return generate

    def run_batch(self, options, by_seed, outcomes=None):
        with patch.object(batch_module, "generate_seed", self.fake_generation(by_seed)):
            return run_batch(options, certify=self.certify(outcomes or {}), log=lambda m: None)

    def test_full_flow_archive_report_and_separation(self):
        production = read_json(PRODUCTION)["puzzles"][0]
        by_seed = {1: [entry(A_PUZZLE, A_SOLUTION, 1, 1), entry(C_PUZZLE, CD_SOLUTION, 1, 2, requiredRating=35.0),
                       entry(D_PUZZLE, CD_SOLUTION, 1, 3, requiredRating=39.0)],
                   2: [entry(B_PUZZLE, B_SOLUTION, 2, 1),
                       entry(production["puzzle"], production["solution"], 2, 2, requiredRating=35.0),
                       entry(A_PUZZLE, A_SOLUTION, 2, 3)]}
        outcomes = {(C_PUZZLE, 15.0): (CertificationStatus.CERTIFICATION_TIMEOUT, 15.0)}
        report = self.run_batch(self.options(), by_seed, outcomes)
        archive = Archive.load(self.folder / "archive.json")
        status = {e["id"]: e for e in archive.candidates}
        self.assertEqual(status[content_id(production["puzzle"])]["rejection"]["reason"], "DUPLICATE")
        self.assertEqual(status[content_id(D_PUZZLE)]["rejection"]["reason"], "OUT_OF_CONCLUSIVE_SCOPE")
        timeout = status[content_id(C_PUZZLE)]
        self.assertEqual(timeout["rejection"]["reason"], "CERTIFICATION_TIMEOUT")
        self.assertEqual(timeout["certification"]["status"], NOT_ATTEMPTED)
        self.assertEqual(timeout["probe"]["status"], "CERTIFICATION_TIMEOUT")
        self.assertEqual({e["id"] for e in report["selected"]}, {content_id(A_PUZZLE), content_id(B_PUZZLE)})
        # Probe first, then the default budget; never a relaxed final config.
        self.assertEqual(sorted(budget for _, budget in self.calls), [15.0, 15.0, 15.0, 60.0, 60.0])
        self.assertEqual(status[content_id(A_PUZZLE)]["certification"]["configFingerprint"], DEFAULT.fingerprint())
        total = report["total"]
        self.assertGreaterEqual(total["generated"], total["unique"])
        self.assertGreaterEqual(total["unique"], total["extremeCandidates"])
        self.assertGreaterEqual(total["extremeCandidates"], total["shortlisted"])
        self.assertGreaterEqual(total["shortlisted"], total["probed"])
        self.assertGreaterEqual(total["probed"], total["certified"])
        self.assertEqual((total["certified"], total["timeouts"], total["selected"]), (2, 1, 2))
        # Coherent funnel: timeouts are a sub-count of inconclusive; generator TOO_EASY <= rated.
        self.assertEqual(total["inconclusive"], 1)
        self.assertGreaterEqual(total["rated"], total["rejected"]["TOO_EASY"])
        self.assertGreaterEqual(total["rated"], total["extremeCandidates"])
        self.assertGreaterEqual(total["eligible"], total["shortlisted"])
        self.assertGreaterEqual(total["certificationAttempts"], total["certified"])
        self.assertEqual(total["duplicatesInRun"], 1)
        self.assertEqual(sum(total["rejectedByStage"].values()), sum(total["rejected"].values()))
        self.assertEqual(total["rejectedByStage"]["generation"], 18)
        stats = read_json(self.folder / "archive.json")["stats"]
        self.assertEqual(stats["byStatus"].get("PROBE:CERTIFICATION_TIMEOUT"), 1)
        self.assertEqual(stats["byProbeStatus"]["CERTIFICATION_TIMEOUT"], 1)
        # Recomputation reproduces the counters into a NEW file, never the original.
        original = (self.folder / "run" / "batch_report.json").read_bytes()
        recomputed, output = recompute_report(self.folder / "run", self.folder / "archive.json")
        self.assertEqual(output.name, "batch_report.recomputed.json")
        self.assertEqual((self.folder / "run" / "batch_report.json").read_bytes(), original)
        strip = lambda value: {k: v for k, v in value.items() if k != "runtimeSeconds"}
        self.assertEqual(strip(recomputed["total"]), strip(report["total"]))
        with self.assertRaises(ValueError):
            recompute_report(self.folder / "run", output=self.folder / "run" / "batch_report.json")
        self.assertAlmostEqual(total["certificationYield"], 2 / 3)
        self.assertAlmostEqual(total["generationYield"], 2 / total["generated"])
        self.assertIn("DUPLICATE", total["rejected"])
        for key in ("generation", "prefilter", "archive", "probe", "certification", "total"):
            self.assertIn(key, total["runtimeSeconds"])
        self.assertEqual([row["seed"] for row in report["perSeed"]], [1, 2])
        saved = read_json(self.folder / "run" / "batch_report.json")
        self.assertEqual(saved["total"]["selected"], 2)
        self.assertEqual(hashlib.sha256(PRODUCTION.read_bytes()).hexdigest(), PRODUCTION_SHA256)
        self.assertNotIn("evidence", (self.folder / "archive.json").read_text(encoding="utf-8"))

    def test_target_slow_certificate_and_resume(self):
        by_seed = {1: [entry(A_PUZZLE, A_SOLUTION, 1, 1, advancedSteps=20), entry(B_PUZZLE, B_SOLUTION, 1, 2)],
                   2: [entry(C_PUZZLE, CD_SOLUTION, 2, 1, requiredRating=35.0)]}
        outcomes = {(A_PUZZLE, 60.0): (CertificationStatus.CERTIFIED_EXTREME, 20.0)}
        report = self.run_batch(self.options(target_new=1), by_seed, outcomes)
        archive = {e["id"]: e for e in Archive.load(self.folder / "archive.json").candidates}
        self.assertEqual(archive[content_id(A_PUZZLE)]["rejection"]["reason"], "NOT_SELECTED_SLOW_CERTIFICATE")
        self.assertTrue(archive[content_id(B_PUZZLE)]["selected"])
        self.assertEqual(archive[content_id(C_PUZZLE)]["rejection"]["reason"], "NOT_SELECTED_TARGET_REACHED")
        self.assertEqual(len(report["selected"]), 1)
        # Resume: generation comes from checkpoints, terminal IDs are not re-certified,
        # the earlier selection counts toward the target, the rest continues.
        (self.folder / "run" / "checkpoints").mkdir(parents=True, exist_ok=True)
        options = self.options(target_new=2, resume=True)
        for seed, rows in by_seed.items():
            (self.folder / "run" / "checkpoints" / f"generate-{seed}.json").write_text(
                json.dumps(checkpoint(options, seed, rows)), encoding="utf-8")
        self.calls.clear()
        with patch.object(batch_module, "generate_seed", side_effect=AssertionError("regenerated")):
            report = run_batch(options, certify=self.certify({}), log=lambda m: None)
        self.assertEqual([identifier for identifier, _ in self.calls], [content_id(C_PUZZLE)] * 2)
        self.assertEqual({e["id"] for e in report["selected"]}, {content_id(B_PUZZLE), content_id(C_PUZZLE)})
        self.assertEqual(report["total"]["alreadyArchived"], 2)

    def test_bands_quota_and_archive_reuse_without_regeneration(self):
        by_seed = {1: [entry(A_PUZZLE, A_SOLUTION, 1, 1), entry(B_PUZZLE, B_SOLUTION, 1, 2),
                       entry(C_PUZZLE, CD_SOLUTION, 1, 3, requiredRating=35.0)]}
        # Score order alone (30 > 35) would certify A and B first and reach the target.
        self.run_batch(self.options(seeds=(1,), target_new=1), by_seed)
        archive = {e["id"]: e for e in Archive.load(self.folder / "archive.json").candidates}
        self.assertEqual(archive[content_id(C_PUZZLE)]["rejection"]["reason"], "NOT_SELECTED_TARGET_REACHED")
        # Reuse the archive only (no seeds, no generation) and target band 35.
        self.calls.clear()
        options = self.options(seeds=(), reuse_archive=True, bands=(35.0,), target_new=1,
                               run_dir=self.folder / "run2")
        with patch.object(batch_module, "generate_seed", side_effect=AssertionError("regenerated")):
            report = run_batch(options, certify=self.certify({}), log=lambda m: None)
        self.assertEqual([identifier for identifier, _ in self.calls], [content_id(C_PUZZLE)] * 2)
        self.assertEqual([e["id"] for e in report["selected"]], [content_id(C_PUZZLE)])
        self.assertEqual(report["diversity"]["selectedByRating"], {"30.0": 1})  # fake certifier minimum
        archive = {e["id"]: e for e in Archive.load(self.folder / "archive.json").candidates}
        self.assertEqual(archive[content_id(C_PUZZLE)]["origin"], "archive-reuse")
        self.assertTrue(archive[content_id(C_PUZZLE)]["selected"])
        self.assertTrue(archive[content_id(A_PUZZLE)]["selected"] or archive[content_id(B_PUZZLE)]["selected"])
        recomputed, _ = recompute_report(self.folder / "run2", self.folder / "archive.json")
        self.assertEqual(recomputed["total"]["selected"], report["total"]["selected"])

    def test_min_per_band_reserves_the_front_of_the_queue(self):
        by_seed = {1: [entry(A_PUZZLE, A_SOLUTION, 1, 1), entry(B_PUZZLE, B_SOLUTION, 1, 2),
                       entry(C_PUZZLE, CD_SOLUTION, 1, 3, requiredRating=35.0)]}
        report = self.run_batch(self.options(seeds=(1,), target_new=1, min_per_band=1), by_seed)
        self.assertEqual(self.calls[0][0], content_id(C_PUZZLE))  # band 35 reserved first
        self.assertEqual([e["id"] for e in report["selected"]], [content_id(C_PUZZLE)])
        for bad in (dict(bands=(36.0,)), dict(bands=(25.0,)), dict(bands=()), dict(min_per_band=-1),
                    dict(seeds=(), reuse_archive=False)):
            with self.assertRaises(ValueError):
                self.options(**bad).validate()
        self.options(bands=(36.0,), include_high=True).validate()

    def test_runtime_budget_and_path_guards(self):
        by_seed = {1: [entry(A_PUZZLE, A_SOLUTION, 1, 1)]}
        ticks = iter([0.0] + [10.0 ** 6] * 100)
        with patch.object(batch_module, "generate_seed", self.fake_generation(by_seed)):
            report = run_batch(self.options(runtime_budget=5.0, seeds=(1,)), certify=self.certify({}),
                               log=lambda m: None, clock=lambda: next(ticks))
        self.assertEqual(report["selected"], [])
        self.assertIn("skipped", report["perSeed"][0])
        for bad in (dict(archive=PRODUCTION.parent / "x.json"), dict(run_dir=PRODUCTION.parent / "runs"),
                    dict(seeds=(1, 1)), dict(seeds=()), dict(resume=True, run_dir=None)):
            with self.assertRaises(ValueError):
                self.options(**bad).validate()

    def test_cli_exit_codes(self):
        out = io.StringIO()
        fake = lambda options: {"runId": "r", "runDir": str(self.folder), "archive": "a", "selected": [1]}
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(batch_main(["--seeds", "1,2", "3"], run=fake), 0)
            self.assertEqual(batch_main(["--seeds", "1"], run=lambda o: {**fake(o), "selected": []}), 1)
            self.assertEqual(batch_main(["--seeds", "1", "--archive", str(LIVE_PRODUCTION)]), 2)
            self.assertEqual(batch_main(["--seeds", "x"]), 2)
        captured = []
        with redirect_stdout(io.StringIO()):
            batch_main(["--seeds", "5,6", "--seeds", "7"], run=lambda o: captured.append(o) or fake(o))
            batch_main(["--reuse-archive", "--bands", "35", "--min-per-band", "2"],
                       run=lambda o: captured.append(o) or fake(o))
        self.assertEqual(captured[0].seeds, (5, 6, 7))
        self.assertEqual((captured[1].seeds, captured[1].bands, captured[1].min_per_band, captured[1].reuse_archive),
                         ((), (35.0,), 2, True))


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.production = self.folder / "production" / "puzzles.json"
        self.production.parent.mkdir()
        shutil.copyfile(PRODUCTION, self.production)
        self.original = self.production.read_bytes()
        self.backups = self.folder / "backups"
        self.configs = []

    def certify(self, status=CertificationStatus.CERTIFIED_EXTREME, elapsed=1.0):
        def run(puzzle, solution=None, *, puzzle_id=None, config=None, fresh=True):
            self.configs.append((config, fresh))
            reasons = [] if status.value.startswith("CERTIFIED") else [FailureReason.SEARCH_TIMEOUT]
            return fake_result(puzzle, solution, config=config, status=status, reasons=reasons, elapsed=elapsed)
        return run

    def merge(self, candidates, **extra):
        values = dict(backup_dir=self.backups, certify=self.certify(), validate=validate_database)
        values.update(extra)
        return merge_production(self.production, candidates, **values)

    def test_preserves_existing_record_and_uses_fresh_default_certification(self):
        claimed = {"id": content_id(A_PUZZLE), "puzzle": A_PUZZLE, "solution": A_SOLUTION, "selected": True,
                   "probe": {"status": "CERTIFIED_EXTREME", "productionEligible": True}}
        outcome = self.merge([claimed, {"puzzle": B_PUZZLE, "solution": B_SOLUTION}])
        self.assertTrue(outcome.written)
        self.assertTrue(outcome.existing_format_canonical)
        self.assertEqual([c for c, _ in self.configs], [DEFAULT, DEFAULT])
        self.assertTrue(all(fresh for _, fresh in self.configs))
        merged = read_json(self.production)
        before = read_json(PRODUCTION)
        old = next(p for p in merged["puzzles"] if p["id"] == EXISTING_ID)
        self.assertEqual(json.dumps(old, sort_keys=True), json.dumps(before["puzzles"][0], sort_keys=True))
        # Byte identity of the existing record's serialized block.
        block = json.dumps({"x": before["puzzles"]}, ensure_ascii=False, indent=2)
        block = block[block.index("[") + 1:block.rindex("]")].strip("\n").rstrip()
        self.assertIn(block, self.production.read_text(encoding="utf-8"))
        self.assertEqual(merged["stats"], {"total": 3, "byDifficulty": {"Extreme": 3}})
        self.assertEqual([p["id"] for p in merged["puzzles"]][0], EXISTING_ID)
        for key in ("schemaVersion", "generatorVersion", "datasetKind"):
            self.assertEqual(merged[key], before[key])
        for record in merged["puzzles"][1:]:
            self.assertEqual(record["certification"]["config"], DEFAULT.to_dict())
        backup = Path(outcome.backup)
        self.assertNotIn(self.production.parent.resolve(), backup.resolve().parents)
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertEqual(hashlib.sha256(backup.read_bytes()).hexdigest(), outcome.backup_sha256)

    def test_rejects_non_certified_and_slow_and_leaves_file_untouched(self):
        for status in (CertificationStatus.CERTIFICATION_TIMEOUT, CertificationStatus.SEARCH_INCONCLUSIVE,
                       CertificationStatus.REJECTED, CertificationStatus.INVALID_PROOF):
            outcome = self.merge([{"puzzle": A_PUZZLE, "solution": A_SOLUTION}], certify=self.certify(status))
            self.assertEqual(outcome.merged, [])
            self.assertFalse(outcome.written)
        outcome = self.merge([{"puzzle": A_PUZZLE, "solution": A_SOLUTION}], certify=self.certify(elapsed=16.0))
        self.assertEqual(outcome.skipped[0]["reason"], "NOT_SELECTED_SLOW_CERTIFICATE")
        self.assertEqual(self.production.read_bytes(), self.original)
        self.assertFalse(self.backups.exists())

    def test_duplicates_skipped_before_certification(self):
        existing = read_json(PRODUCTION)["puzzles"][0]
        candidates = [{"puzzle": existing["puzzle"], "solution": existing["solution"]},
                      {"puzzle": transpose(existing["puzzle"]), "solution": transpose(existing["solution"])},
                      {"id": "puzzle-00000000000000000000", "puzzle": A_PUZZLE},
                      {"puzzle": C_PUZZLE, "solution": CD_SOLUTION}, {"puzzle": D_PUZZLE, "solution": CD_SOLUTION}]
        outcome = self.merge(candidates)
        self.assertEqual([s["reason"] for s in outcome.skipped], ["DUPLICATE", "NEAR_DUPLICATE", "INVALID", "NEAR_DUPLICATE"])
        self.assertEqual([m["id"] for m in outcome.merged], [content_id(C_PUZZLE)])
        self.assertEqual(len(self.configs), 1)
        outcome = self.merge([{"puzzle": C_PUZZLE, "solution": CD_SOLUTION}])
        self.assertEqual(outcome.skipped[0]["reason"], "DUPLICATE")

    def test_invalid_existing_database_aborts(self):
        def invalid(database):
            raise ExportValidationError("stale certificate")
        with self.assertRaises(MergeError):
            self.merge([{"puzzle": A_PUZZLE, "solution": A_SOLUTION}], validate=invalid)
        self.assertEqual(self.configs, [])
        self.assertEqual(self.production.read_bytes(), self.original)

    def test_atomic_write_failure_keeps_original(self):
        with patch("generator.production.merge.atomic_json", side_effect=ExportValidationError("readback")):
            with self.assertRaises(MergeError) as caught:
                self.merge([{"puzzle": A_PUZZLE, "solution": A_SOLUTION}])
        self.assertTrue(caught.exception.restored)
        self.assertEqual(self.production.read_bytes(), self.original)
        self.assertEqual([p.name for p in self.production.parent.iterdir()], ["puzzles.json"])

    def test_post_validation_failure_restores_backup(self):
        calls = []
        def validate(database):
            calls.append(len(database["puzzles"]))
            validate_database(database)
            if len(calls) == 2:
                raise ExportValidationError("post-write re-certification failed")
        with self.assertRaises(MergeError) as caught:
            self.merge([{"puzzle": A_PUZZLE, "solution": A_SOLUTION}], validate=validate)
        self.assertTrue(caught.exception.restored)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(self.production.read_bytes(), self.original)
        self.assertEqual(next(self.backups.iterdir()).read_bytes(), self.original)

    def test_backup_inside_production_folder_and_dry_run(self):
        with self.assertRaises(ValueError):
            self.merge([{"puzzle": A_PUZZLE, "solution": A_SOLUTION}], backup_dir=self.production.parent / "bk")
        self.assertEqual(self.production.read_bytes(), self.original)
        outcome = self.merge([{"puzzle": A_PUZZLE, "solution": A_SOLUTION}], dry_run=True)
        self.assertEqual(len(outcome.merged), 1)
        self.assertFalse(outcome.written)
        self.assertEqual(self.production.read_bytes(), self.original)

    def test_merge_order_prefers_final_selected_fast_and_mixes_ratings(self):
        def item(name, rank, rating, elapsed):
            puzzle = name
            cert = {"status": "CERTIFIED_EXTREME", "productionEligible": True, "elapsed": elapsed,
                    "minimumRequiredRating": rating}
            value = {"id": name, "puzzle": puzzle}
            if rank == 2:
                value["probe"] = cert
            else:
                value["certification"] = cert
                value["selected"] = rank == 0
            return value
        entries = [item("a", 0, 30.0, 2.0), item("b", 0, 30.0, 1.0), item("c", 0, 35.0, 3.0),
                   item("d", 2, 35.0, 0.1), {"id": "e", "puzzle": "e", "certification": {"status": "CERTIFICATION_TIMEOUT"}},
                   {**item("f", 0, 35.0, 0.1), "production": {"merged": True}}]
        self.assertEqual([e["id"] for e in merge_order(entries)], ["c", "b", "a", "d"])

    def test_cli_merge_updates_archive_and_reports(self):
        archive = Archive.load(self.folder / "research" / "archive.json")
        archive.upsert({**entry(A_PUZZLE, A_SOLUTION), "selected": True, "production": {"merged": False},
                        "certification": {"status": "CERTIFIED_EXTREME", "productionEligible": True, "elapsed": 1.0,
                                          "minimumRequiredRating": 30.0}})
        archive.save(fingerprints={})
        def fake(path, candidates, **kwargs):
            return merge_production(path, candidates, certify=self.certify(), validate=validate_database, **kwargs)
        args = ["--production", str(self.production), "--archive", str(archive.path), "--backup-dir",
                str(self.backups), "--report", str(self.folder / "research" / "merge.json"), "--target-total", "2"]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(merge_main(args, merge=fake), 0)
            self.assertEqual(merge_main(args, merge=fake), 1)  # already at target total
            self.assertEqual(merge_main(["--production", str(self.production), "--archive", str(self.production)]), 2)
        self.assertTrue(Archive.load(archive.path).candidates[0]["production"]["merged"])
        self.assertEqual(read_json(self.folder / "research" / "merge.json")["merged"][0]["id"], content_id(A_PUZZLE))


class LockAndBookkeepingTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.archive = self.folder / "research" / "archive.json"

    def test_lock_is_exclusive_and_released(self):
        with archive_lock(self.archive, "first"):
            with self.assertRaises(ArchiveLockedError) as caught:
                with archive_lock(self.archive):
                    pass
            self.assertIn("first", str(caught.exception))
            self.assertIn("stale", str(caught.exception))
        self.assertFalse(Path(str(self.archive) + ".lock").exists())
        with self.assertRaises(RuntimeError):
            with archive_lock(self.archive):
                raise RuntimeError("boom")
        self.assertFalse(Path(str(self.archive) + ".lock").exists())

    def test_batch_and_merge_refuse_a_held_lock(self):
        options = BatchOptions(seeds=(1,), archive=self.archive, run_dir=self.folder / "run", production=PRODUCTION)
        with archive_lock(self.archive, "other"):
            with patch.object(batch_module, "generate_seed", side_effect=AssertionError("ran under lock")):
                with self.assertRaises(ArchiveLockedError):
                    run_batch(options, log=lambda m: None)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(batch_main(["--seeds", "1", "--archive", str(self.archive), "--run-dir",
                                             str(self.folder / "run"), "--production", str(PRODUCTION)]), 2)
                self.assertEqual(merge_main(["--production", str(PRODUCTION), "--archive", str(self.archive)],
                                            merge=lambda *a, **k: self.fail("merged under lock")), 2)

    def test_archive_failure_after_production_write_is_reported_separately(self):
        production = self.folder / "production" / "puzzles.json"
        production.parent.mkdir()
        shutil.copyfile(PRODUCTION, production)
        archive = Archive.load(self.archive)
        archive.upsert({**entry(A_PUZZLE, A_SOLUTION), "selected": True, "production": {"merged": False},
                        "certification": {"status": "CERTIFIED_EXTREME", "productionEligible": True, "elapsed": 1.0,
                                          "minimumRequiredRating": 30.0}})
        archive.save(fingerprints={})

        def fake(path, candidates, **kwargs):
            certify = lambda puzzle, solution=None, **k: fake_result(puzzle, solution, config=k["config"])
            return merge_production(path, candidates, certify=certify, validate=validate_database, **kwargs)
        report = self.folder / "research" / "merge.json"
        err = io.StringIO()
        with patch.object(Archive, "save", side_effect=OSError("disk full")),                 redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = merge_main(["--production", str(production), "--archive", str(self.archive), "--backup-dir",
                               str(self.folder / "backups"), "--report", str(report)], merge=fake)
        self.assertEqual(code, 3)
        self.assertIn("merged and validated", err.getvalue())
        saved = read_json(report)
        self.assertTrue(saved["written"])
        self.assertTrue(saved["archiveUpdate"].startswith("failed"))
        self.assertEqual(read_json(production)["stats"]["total"], 2)
        self.assertFalse(Path(str(self.archive) + ".lock").exists())


class RealCertificationMergeTests(unittest.TestCase):
    """Real certifier, real validator: multiple certified puzzles in production."""

    def test_baseline_fixture_is_frozen(self):
        self.assertEqual(hashlib.sha256(PRODUCTION.read_bytes()).hexdigest(), PRODUCTION_SHA256)
        self.assertEqual([p["id"] for p in read_json(PRODUCTION)["puzzles"]], [EXISTING_ID])

    def test_live_production_keeps_original_record_and_fingerprint(self):
        # Looks up by ID only: the live DB may hold any number of merged records.
        live = read_json(LIVE_PRODUCTION)
        records = {p["id"]: p for p in live["puzzles"]}
        self.assertIn(EXISTING_ID, records)
        self.assertEqual(live["stats"]["total"], len(live["puzzles"]))
        self.assertEqual(len(records), len(live["puzzles"]))
        for record in live["puzzles"]:
            with self.subTest(puzzle_id=record["id"]):
                if record["difficulty"] in ("Easy", "Medium"):
                    self.assertNotIn("certification", record)
                    expected = verify_standard(record["puzzle"], record["solution"], record["difficulty"],
                                               puzzle_id=record["id"])
                    self.assertEqual({key: record[key] for key in expected}, expected)
                elif record["difficulty"] in ("Extreme", "Ultra Extreme"):
                    self.assertIn(record["certification"]["status"], ("CERTIFIED_EXTREME", "CERTIFIED_ULTRA_EXTREME"))
                    self.assertEqual(record["certification"]["config"], DEFAULT.to_dict())
                else:
                    self.fail(f"Unsupported production difficulty: {record['difficulty']}")
        baseline = read_json(PRODUCTION)["puzzles"][0]
        block = json.dumps({"x": [baseline]}, ensure_ascii=False, indent=2)
        block = block[block.index("[") + 1:block.rindex("]")].strip("\n").rstrip()
        self.assertIn(block, LIVE_PRODUCTION.read_text(encoding="utf-8"))
        evidence = records[EXISTING_ID]["certification"]["evidence"]
        self.assertEqual(evidence["algorithm_fingerprint"], algorithm_fingerprint())

    def test_merge_real_certified_puzzles_and_revalidate(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            production = folder / "production" / "puzzles.json"
            production.parent.mkdir()
            shutil.copyfile(PRODUCTION, production)
            outcome = merge_production(production, [{"puzzle": A_PUZZLE, "solution": A_SOLUTION},
                                                    {"puzzle": B_PUZZLE, "solution": B_SOLUTION}],
                                       backup_dir=folder / "backups")
            self.assertTrue(outcome.written)
            self.assertEqual(len(outcome.merged), 2)
            database = read_json(production)
            self.assertEqual(database["stats"]["total"], 3)
            self.assertEqual({p["certification"]["status"] for p in database["puzzles"]}, {"CERTIFIED_EXTREME"})
            validate_production_database(database)
            self.assertEqual(PRODUCTION.read_bytes(), (Path(outcome.backup)).read_bytes())


class DispatchTests(unittest.TestCase):
    def test_main_dispatches_production_commands(self):
        with patch("generator.production.cli.batch_main", return_value=7) as batch_cli, \
                patch("generator.production.cli.merge_main", return_value=8) as merge_cli:
            self.assertEqual(main(["production-batch", "--seeds", "1"]), 7)
            self.assertEqual(main(["production-merge", "--dry-run"]), 8)
        batch_cli.assert_called_once_with(["--seeds", "1"])
        merge_cli.assert_called_once_with(["--dry-run"])


if __name__ == "__main__":
    unittest.main()
