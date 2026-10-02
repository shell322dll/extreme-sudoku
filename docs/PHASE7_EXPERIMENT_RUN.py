"""Reproduce Phase 6 candidate selection and fresh Phase 7 measurements.

Run from repository root: python docs/PHASE7_EXPERIMENT_RUN.py --pilot
Definitive run: python docs/PHASE7_EXPERIMENT_RUN.py --final
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator.certification import CertificationConfig
from generator.certification.io import atomic_json, export_production, read_json
from generator.certification.pipeline import algorithm_fingerprint


def inputs():
    sources = ["docs/PHASE6_CANDIDATES.json", "docs/PHASE6_AUDIT_CANDIDATES.json", "docs/PHASE6_PROFILE.json"]
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    records, source_counts = {}, {}
    def add(record, source):
        key = record["puzzle"]
        if key in records:
            if any(records[key][field] != record[field] for field in ("id", "solution", "difficulty")):
                raise ValueError("Overlapping archives disagree on record identity")
            records[key]["phase7Sources"].append(source)
        else:
            records[key] = {**deepcopy(record), "phase7Sources": [source]}
    for source in sources[:2]:
        values = read_json(ROOT / source)["puzzles"]
        source_counts[source] = len(values)
        for record in values:
            add(record, source)
    profile = read_json(ROOT / sources[2])
    puzzle = "009000001000050008010000640028004000000190000000002030002403000100000206000070003"
    matches = [r for r in profile["population"] if r["puzzle"] == puzzle]
    if len(matches) != 1:
        raise ValueError("Expected one saved minimum-22-clue Extreme population record")
    record = matches[0]
    add({"id": "puzzle-" + hashlib.sha256(puzzle.encode()).hexdigest()[:20],
         "puzzle": puzzle, "solution": record["solution"], "clues": record["clues"],
         "unique": record["unique"], "minimal": record["minimal"], "difficulty": "Extreme",
         "phase6PopulationRecord": record}, sources[2] + "#population")
    source_counts[sources[2] + "#selected_population"] = 1
    values = sorted(records.values(), key=lambda r: (r["difficulty"], r["clues"], r["id"]))
    if len({r["id"] for r in values}) != len(values):
        raise ValueError("Duplicate IDs across independent source puzzles")
    return values, source_counts, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pilot", action="store_true")
    mode.add_argument("--final", action="store_true")
    args = parser.parse_args()
    records, source_counts, hashes = inputs()
    prefix = "PHASE7_PILOT" if args.pilot else "PHASE7_EXPERIMENT"
    if args.pilot:
        selected = {"puzzle-f197179f12c6533697b1", "puzzle-ca88d658a18eafb27c24"}
        records = [r for r in records if r["id"] in selected]
        if len(records) != 2:
            raise ValueError("Pilot requires the representative Extreme and minimum-22-clue Ultra")
    config = CertificationConfig()
    summary_path = ROOT / "docs" / (prefix + "_SUMMARY.json")
    if summary_path.exists():
        raise ValueError("Existing evidence will not be overwritten; archive it explicitly before rerunning")
    start_fingerprint = algorithm_fingerprint()
    input_path = ROOT / "docs" / (prefix + "_INPUT.json")
    atomic_json(input_path, {"schemaVersion": 1, "puzzles": records,
                            "sourceCounts": source_counts, "sourceSHA256": hashes})
    started = time.perf_counter()
    def progress(index, total, entry):
        value = entry.result.to_dict() if entry.result else entry.to_dict()["certification"]
        if args.final and value.get("algorithm_fingerprint") != start_fingerprint:
            raise ValueError("Certification source fingerprint changed during definitive experiment")
        print(json.dumps({"index": index, "total": total, "id": value.get("puzzle_id"),
            "sourceLabel": entry.source.get("difficulty"), "clues": value.get("clues"),
            "status": value["status"], "seconds": value.get("elapsed_seconds"),
            "states": value.get("states_explored"), "reasons": value.get("failure_reasons"),
            "unique": value.get("unique"), "minimal": value.get("minimal"),
            "humanSolved": value.get("human_solved"), "proofValid": value.get("proof_valid"),
            "observedUpperRating": value.get("observed_upper_rating"),
            "stage_seconds": value.get("stage_seconds"), "diagnostics": value.get("diagnostics")}), flush=True)
        atomic_json(ROOT / "docs" / (prefix + "_LATEST.json"), value)
    database, research = export_production(records,
        ROOT / "docs" / (prefix + "_PRODUCTION.json") if args.pilot else ROOT / "data/production/puzzles.json",
        config=config, research_path=ROOT / "docs" / (prefix + "_RESEARCH.json") if args.pilot else ROOT / "data/candidates.json",
        reports_dir=ROOT / "docs" / (prefix + "_REPORTS") if args.pilot else ROOT / "reports/certification",
        progress=progress)
    wall = time.perf_counter() - started
    results = [entry["certification"] for entry in research["candidates"]]
    by_label = defaultdict(Counter)
    for entry in research["candidates"]:
        by_label[entry["source"]["difficulty"]][entry["certification"]["status"]] += 1
    times = [r.get("elapsed_seconds", 0) for r in results]
    final_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in hashes}
    stage_totals = Counter()
    for result in results:
        stage_totals.update(result.get("stage_seconds", {}))
    summary = {"timestampUTC": datetime.now(timezone.utc).isoformat(), "pilot": args.pilot,
        "command": "python docs/PHASE7_EXPERIMENT_RUN.py " + ("--pilot" if args.pilot else "--final"),
        "environment": {"python": sys.version, "platform": platform.platform()},
        "config": config.to_dict(), "sourceCounts": source_counts, "sourceSHA256": hashes,
        "sourcesUnchanged": hashes == final_hashes, "algorithmFingerprintBefore": start_fingerprint,
        "algorithmFingerprintAfter": algorithm_fingerprint(),
        "inputIDs": [r["id"] for r in records], "inputCount": len(records),
        "byPreliminaryLabel": {k: dict(v) for k, v in by_label.items()},
        "byStatus": dict(Counter(r["status"] for r in results)), "wallSeconds": wall,
        "averageSeconds": statistics.mean(times), "worstSeconds": max(times),
        "stageSecondsInclusive": dict(stage_totals),
        "statesExplored": {"total": sum(r.get("states_explored", 0) for r in results),
                           "byID": {r["puzzle_id"]: r.get("states_explored", 0) for r in results}},
        "transpositionCacheHits": {"total": sum(r.get("cache_hits", 0) for r in results),
                           "byID": {r["puzzle_id"]: r.get("cache_hits", 0) for r in results}},
        "productionCount": len(database["puzzles"]), "productionIDs": [r["id"] for r in database["puzzles"]],
        "minimumCertifiedClues": min((r["clues"] for r in database["puzzles"]), default=None),
        "maximumCertifiedRequiredRating": max((r["rating"] for r in database["puzzles"]), default=None),
        "maximumCertifiedBottlenecks": max((r["certification"]["genuineBottlenecks"] for r in database["puzzles"]), default=None)}
    atomic_json(summary_path, summary)
    print(json.dumps(summary, indent=2), flush=True)
    if not summary["sourcesUnchanged"]:
        raise ValueError("Source candidate artifacts changed during the experiment")
    if args.final and summary["algorithmFingerprintBefore"] != summary["algorithmFingerprintAfter"]:
        raise ValueError("Definitive experiment source fingerprint changed")


if __name__ == "__main__":
    main()
