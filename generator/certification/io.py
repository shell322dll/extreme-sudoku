"""Fresh certification, research evidence and strict production export.

Legacy generator.export is a research/demo exporter. This module never accepts a
saved certification flag as permission to publish a puzzle.
"""
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from ..export import ExportValidationError, validate_database
from ..models import GENERATOR_VERSION
from . import CertificationConfig, certify_puzzle


class BatchFailureReason(str, Enum):
    INVALID_FORMAT = "INVALID_FORMAT"
    DUPLICATE = "DUPLICATE"


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_json(value):
    """JSON identity preserves Boolean/number types (Python equality does not)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      parse_constant=_reject_constant, object_pairs_hook=_unique_keys)


def load_candidates(path):
    """Read schema-v1 databases, plain arrays, or our research evidence bundle."""
    value = read_json(path)
    if isinstance(value, list):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("Candidate input must be an object or array")
    if isinstance(value.get("puzzles"), list):
        if type(value.get("schemaVersion", 1)) is not int or value.get("schemaVersion", 1) != 1:
            raise ValueError("Unsupported input schemaVersion")
        return value["puzzles"]
    if value.get("researchVersion") == 1 and isinstance(value.get("candidates"), list):
        return [entry.get("source") for entry in value["candidates"]]
    raise ValueError("Input must contain a puzzles array")


def _identifier(record):
    value = record.get("id")
    if value is None and isinstance(record.get("puzzle"), str):
        value = "puzzle-" + hashlib.sha256(record["puzzle"].encode("utf-8")).hexdigest()[:20]
    return value


@dataclass
class BatchEntry:
    source: object
    result: object = None
    reason: BatchFailureReason | None = None
    detail: str = ""

    def to_dict(self):
        return {"source": self.source,
                "certification": self.result.to_dict() if self.result else {
                    "status": "REJECTED", "failure_reasons": [self.reason.value],
                    "detail": self.detail, "production_eligible": False}}


def certify_batch(records, config=None, *, progress=None):
    """Certify raw records freshly; reject all colliding IDs/puzzles cheaply."""
    config = config or CertificationConfig()
    records = list(records)
    ids = Counter(_identifier(record) for record in records if isinstance(record, Mapping)
                  and isinstance(_identifier(record), str))
    puzzles = Counter(record.get("puzzle") for record in records if isinstance(record, Mapping)
                      and isinstance(record.get("puzzle"), str))
    entries = []
    for index, record in enumerate(records):
        entry = BatchEntry(record)
        identifier = _identifier(record) if isinstance(record, Mapping) else None
        if not isinstance(record, Mapping) or not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier):
            entry.reason, entry.detail = BatchFailureReason.INVALID_FORMAT, "Invalid candidate object or ID"
        elif ("clues" in record and (type(record["clues"]) is not int or
              not isinstance(record.get("puzzle"), str) or record["clues"] != sum(c != "0" for c in record["puzzle"]))):
            entry.reason, entry.detail = BatchFailureReason.INVALID_FORMAT, "Declared clue count does not match puzzle"
        elif ids[identifier] > 1 or (isinstance(record.get("puzzle"), str) and puzzles[record["puzzle"]] > 1):
            entry.reason, entry.detail = BatchFailureReason.DUPLICATE, "Duplicate ID or exact puzzle string in this batch"
        else:
            # Saved uniqueness, difficulty, minimality and certification are deliberately
            # not passed to the certifier. It creates new caches and a new state.
            entry.result = certify_puzzle(record.get("puzzle"), record.get("solution"),
                                         puzzle_id=identifier, config=config, fresh=True)
        entries.append(entry)
        if progress:
            progress(index + 1, len(records), entry)
    return entries


def _record(result, config):
    if not result.production_eligible:
        raise ExportValidationError("Only conclusive certified results may enter production")
    status = result.status.value
    if status not in ("CERTIFIED_EXTREME", "CERTIFIED_ULTRA_EXTREME"):
        raise ExportValidationError("Unsupported production certification status")
    evidence = result.to_dict()
    counts = Counter(step.technique for step in result.certified_path)
    record = {
        "id": result.puzzle_id, "puzzle": result.puzzle, "solution": result.solution,
        "clues": result.clues, "difficulty": "Ultra Extreme" if status == "CERTIFIED_ULTRA_EXTREME" else "Extreme",
        "rating": result.minimum_required_rating, "unique": result.unique, "minimal": result.minimal,
        "techniques": dict(sorted(counts.items())), "techniquesUsed": sorted(counts),
        "certification": {
            "status": status, "version": result.certification_version,
            "requiredRating": result.minimum_required_rating, "requiredTier": result.minimum_required_tier,
            "searchConclusive": True, "negativeProofKind": result.negative_proof_kind,
            "proofValidated": result.proof_valid,
            "humanSolved": result.human_solved, "reproducible": result.reproducible,
            "genuineBottlenecks": result.certified_bottlenecks,
            "configFingerprint": result.config_fingerprint, "config": config.to_dict(),
            "evidence": evidence,
        },
    }
    # Dataclass proofs contain tuples; the public production record is JSON-native.
    return json.loads(json.dumps(record, allow_nan=False))


def _stable_record(record):
    """Remove runtime counters only when comparing independent fresh reruns."""
    value = json.loads(json.dumps(record))
    evidence = value.get("certification", {}).get("evidence", {})
    for key in ("elapsed_seconds", "stage_seconds", "search_telemetry"):
        evidence.pop(key, None)
    for threshold in evidence.get("threshold_results", []):
        for key in ("elapsed_seconds", "proof_seconds", "telemetry"):
            threshold.pop(key, None)
    return _canonical_json(value)


def validate_production_database(database):
    """Independently re-certify every record and compare all certified metadata.

This is intentionally stronger than schema validation. Callers cannot validate
an invented certificate merely by setting several booleans to true.
"""
    validate_database(database)
    if database.get("datasetKind") != "production-certified":
        raise ExportValidationError("Missing production dataset marker")
    for record in database["puzzles"]:
        certification = record.get("certification")
        if not isinstance(certification, Mapping):
            raise ExportValidationError("Missing certification metadata")
        try:
            config = CertificationConfig.from_dict(certification["config"])
            result = certify_puzzle(record["puzzle"], record["solution"],
                                    puzzle_id=record["id"], config=config, fresh=True)
            expected = _record(result, config)
        except (KeyError, TypeError, ValueError) as exc:
            raise ExportValidationError(f"{record['id']}: invalid or unrepeatable certificate: {exc}") from exc
        if _stable_record(record) != _stable_record(expected):
            raise ExportValidationError(f"{record['id']}: metadata differs from fresh certification")
    counts = Counter(record["difficulty"] for record in database["puzzles"])
    if _canonical_json(database.get("stats")) != _canonical_json({"total": len(database["puzzles"]), "byDifficulty": dict(sorted(counts.items()))}):
        raise ExportValidationError("Production statistics do not match records")


def atomic_json(path, value, *, validator=None):
    """Validate in memory and after temp-file JSON readback, then atomic replace."""
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    normalized = json.loads(text)
    if validator:
        validator(normalized)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        decoded = read_json(temporary)
        if _canonical_json(decoded) != _canonical_json(normalized):
            raise ExportValidationError("JSON readback differs from original data")
        if validator:
            validator(decoded)
        os.replace(temporary, path)
        # Verify the actual destination was replaced with the validated bytes.
        if path.read_text(encoding="utf-8") != text:
            raise ExportValidationError("Destination readback differs from validated JSON")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def export_production(records, path="data/production/puzzles.json", *, config=None,
                      research_path=None, reports_dir=None, generated_at=None, progress=None):
    """Freshly certify raw candidates and export eligible records only.

An empty accepted batch creates an explicit empty production database. The
caller must select a separate output path from input and legacy demo data.
"""
    config = config or CertificationConfig()
    destinations = [Path(path).resolve()]
    if research_path is not None:
        destinations.append(Path(research_path).resolve())
    if len(destinations) != len(set(destinations)):
        raise ValueError("Production and research outputs must be separate")
    if reports_dir is not None and Path(reports_dir).resolve() in destinations:
        raise ValueError("Report directory and output files must be separate")
    entries = certify_batch(records, config, progress=progress)
    accepted = [_record(entry.result, config) for entry in entries if entry.result and entry.result.production_eligible]
    accepted.sort(key=lambda p: (p["difficulty"], -p["rating"], p["clues"], p["id"]))
    counts = Counter(record["difficulty"] for record in accepted)
    database = {"schemaVersion": 1, "generatedAt": generated_at or _utc(),
                "generatorVersion": GENERATOR_VERSION, "datasetKind": "production-certified",
                "puzzles": accepted, "stats": {"total": len(accepted), "byDifficulty": dict(sorted(counts.items()))}}
    # Bind readback to full records made from THIS invocation's fresh results.
    # No externally supplied certificate or result object enters this mapping.
    expected = json.loads(json.dumps(database))
    def validate_current(value):
        validate_database(value)
        if _canonical_json(value) != _canonical_json(expected):
            raise ExportValidationError("Production data differs from fresh evidence")
    diagnostics = [entry.to_dict() for entry in entries]
    status_counts = Counter(entry["certification"]["status"] for entry in diagnostics)
    research = {"researchVersion": 1, "generatedAt": database["generatedAt"],
                "config": config.to_dict(), "candidates": diagnostics,
                "stats": {"input": len(entries), "certified": len(accepted), "byStatus": dict(sorted(status_counts.items()))}}
    if research_path is not None:
        atomic_json(research_path, research)
    if reports_dir is not None:
        directory = Path(reports_dir)
        for index, entry in enumerate(entries):
            identifier = entry.result.puzzle_id if entry.result else f"rejected-{index + 1:06d}"
            # Hash avoids unsafe path characters in any future ID convention.
            filename = f"{index + 1:06d}-{hashlib.sha256(identifier.encode()).hexdigest()[:20]}.json"
            atomic_json(directory / filename, entry.to_dict())
    atomic_json(path, database, validator=validate_current)
    return database, research
