"""Safe append-only merge of freshly certified puzzles into the production DB.

Guarantees (each enforced in code and covered by tests):

1. The existing database is fully re-validated (fresh re-certification) first;
   nothing is merged into an invalid database.
2. Existing records are kept verbatim (same JSON objects, canonical identity is
   re-checked on the temp file before the atomic replace).
3. Every new record comes from a FRESH ``certify_puzzle`` run in this process with
   the default ``CertificationConfig()``; archive/probe statuses are only used to
   order candidates. Only CERTIFIED_EXTREME / CERTIFIED_ULTRA_EXTREME results
   that are production-eligible are admitted (``certification.io._record``).
4. Duplicates (exact puzzle string, ID, same-solution / clue-mask / symmetry
   near-duplicates) are skipped. IDs use the project's content-hash scheme.
5. A byte copy of the current file is written OUTSIDE the production folder and
   verified by SHA-256 before the write; the write is temp file + ``os.replace``;
   ``validate_production_database`` re-runs on the written file and the backup is
   restored (and hash-verified) if it fails.
"""
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import tempfile

from ..certification import CertificationConfig, certify_puzzle as _certify_puzzle
from ..certification.io import (_canonical_json, _record, atomic_json, read_json,
                                validate_production_database as _validate_production_database)
from ..export import ExportValidationError, validate_database
from .archive import content_id, utc_now
from .diversity import DiversityIndex
from .models import Phase9Reason, reason_for_result

SLOW_FRACTION = 0.25


class MergeError(RuntimeError):
    def __init__(self, message, *, restored=False):
        super().__init__(message)
        self.restored = restored


@dataclass
class MergeOutcome:
    merged: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    backup: str | None = None
    backup_sha256: str | None = None
    written: bool = False
    existing_ids: list = field(default_factory=list)
    existing_format_canonical: bool = False
    total: int = 0

    def to_dict(self):
        return {"merged": self.merged, "skipped": self.skipped, "backup": self.backup,
                "backupSha256": self.backup_sha256, "written": self.written,
                "existingIds": self.existing_ids, "existingFormatCanonical": self.existing_format_canonical,
                "total": self.total}


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _render(database):
    """Exactly the serialization used by certification.io.atomic_json."""
    return json.dumps(database, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _write_bytes_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if temporary.read_bytes() != data:
            raise OSError(f"Temporary readback differs: {temporary}")
        os.replace(temporary, path)
        if path.read_bytes() != data:
            raise OSError(f"Destination readback differs: {path}")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def make_backup(path, backup_dir, original):
    """Byte copy outside the production folder, verified by SHA-256."""
    production_dir = Path(path).resolve().parent
    backup_dir = Path(backup_dir)
    resolved = backup_dir.resolve()
    if resolved == production_dir or production_dir in resolved.parents:
        raise ValueError(f"Backup directory must be outside the production folder {production_dir}")
    digest = _sha256(original)
    stamp = utc_now().replace("-", "").replace(":", "")
    target = backup_dir / f"{Path(path).stem}-{stamp}-{digest[:12]}.json"
    _write_bytes_atomic(target, original)
    if _sha256(target.read_bytes()) != digest:
        raise OSError(f"Backup hash mismatch: {target}")
    return target, digest


def restore_backup(path, backup, digest):
    data = Path(backup).read_bytes()
    if _sha256(data) != digest:
        raise OSError(f"Backup {backup} no longer matches its SHA-256; manual restore needed")
    _write_bytes_atomic(path, data)
    if _sha256(Path(path).read_bytes()) != digest:
        raise OSError(f"Restored {path} does not match the backup hash")


def _sort_key(record):
    # Same key as certification.io.export_production.
    return (record["difficulty"], -record["rating"], record["clues"], record["id"])


def _stats(puzzles):
    counts = Counter(record["difficulty"] for record in puzzles)
    return {"total": len(puzzles), "byDifficulty": dict(sorted(counts.items()))}


def merge_production(path, candidates, *, backup_dir, max_new=None, dry_run=False,
                     certify=_certify_puzzle, validate=_validate_production_database,
                     slow_fraction=SLOW_FRACTION, generated_at=None, log=None):
    """Append freshly certified candidates to the production DB at ``path``.

    ``candidates`` are mappings with ``puzzle`` (+ optional ``id``/``solution``) in
    preference order. Returns a MergeOutcome; raises MergeError on any failure
    (the original file is then unchanged or restored from the verified backup).
    """
    log = log or (lambda message: None)
    path = Path(path)
    config = CertificationConfig()  # production stays uniform: default policy only
    slow_limit = slow_fraction * config.time_budget
    outcome = MergeOutcome()
    original = path.read_bytes()
    existing = read_json(path)
    try:
        validate(existing)
    except (ExportValidationError, ValueError, KeyError, TypeError) as exc:
        raise MergeError(f"Existing production database is invalid; nothing merged: {exc}") from exc
    outcome.existing_ids = [record["id"] for record in existing["puzzles"]]
    outcome.existing_format_canonical = _render(existing).encode("utf-8") == original
    originals = {record["id"]: _canonical_json(record) for record in existing["puzzles"]}
    index = DiversityIndex()
    for record in existing["puzzles"]:
        index.add(record, "production")

    new_records = []
    for candidate in candidates:
        if max_new is not None and len(new_records) >= max_new:
            break
        puzzle = candidate.get("puzzle") if isinstance(candidate, dict) else None
        if not isinstance(puzzle, str) or len(puzzle) != 81 or any(c not in "0123456789" for c in puzzle):
            outcome.skipped.append({"id": candidate.get("id") if isinstance(candidate, dict) else None,
                                    "reason": Phase9Reason.INVALID.value, "detail": "invalid puzzle string"})
            continue
        identifier = content_id(puzzle)
        if candidate.get("id", identifier) != identifier:
            outcome.skipped.append({"id": candidate.get("id"), "reason": Phase9Reason.INVALID.value,
                                    "detail": f"ID does not match content hash {identifier}"})
            continue
        entry = {"id": identifier, "puzzle": puzzle, "solution": candidate.get("solution")}
        duplicate = index.check(entry)
        if duplicate:
            outcome.skipped.append({"id": identifier, "reason": duplicate[0].value, "detail": duplicate[1]})
            continue
        # Never trust archive/probe/batch results: certify here, fresh, default policy.
        result = certify(puzzle, candidate.get("solution"), puzzle_id=identifier, config=config, fresh=True)
        reason = reason_for_result(result)
        if reason is not None:
            outcome.skipped.append({"id": identifier, "reason": reason.value,
                                    "detail": ",".join([result.status.value, *[r.value for r in result.failure_reasons]])})
            log(f"skip {identifier}: {result.status.value}")
            continue
        if result.config_fingerprint != config.fingerprint():
            raise MergeError(f"{identifier}: certification config mismatch")
        if result.elapsed_seconds > slow_limit:
            outcome.skipped.append({"id": identifier, "reason": Phase9Reason.NOT_SELECTED_SLOW_CERTIFICATE.value,
                                    "detail": f"{result.elapsed_seconds:.1f} s > {slow_limit:g} s"})
            continue
        record = _record(result, config)
        new_records.append(record)
        index.add(record, "new")
        outcome.merged.append({"id": identifier, "status": result.status.value, "rating": record["rating"],
                               "clues": record["clues"], "elapsed": round(result.elapsed_seconds, 3)})
        log(f"certified {identifier}: {result.status.value} min {record['rating']} ({result.elapsed_seconds:.1f} s)")

    puzzles = list(existing["puzzles"]) + new_records
    puzzles.sort(key=_sort_key)
    database = dict(existing)  # keeps the root key order and every root field
    database["generatedAt"] = generated_at or utc_now()
    database["puzzles"] = puzzles
    database["stats"] = _stats(puzzles)
    outcome.total = len(puzzles)
    if not new_records or dry_run:
        return outcome
    expected = json.loads(_render(database))

    def validate_merge(value):
        validate_database(value)
        if _canonical_json(value) != _canonical_json(expected):
            raise ExportValidationError("Merged data differs from this invocation's records")
        present = {record["id"]: _canonical_json(record) for record in value["puzzles"]}
        for identifier, text in originals.items():
            if present.get(identifier) != text:
                raise ExportValidationError(f"Existing record {identifier} would change")
        if _canonical_json(value["stats"]) != _canonical_json(_stats(value["puzzles"])):
            raise ExportValidationError("Statistics do not match records")

    backup, digest = make_backup(path, backup_dir, original)
    outcome.backup, outcome.backup_sha256 = str(backup), digest
    if _sha256(path.read_bytes()) != digest:
        raise MergeError("Production file changed while merging; aborted before writing")
    try:
        atomic_json(path, database, validator=validate_merge)
    except Exception as exc:
        restored = _sha256(path.read_bytes()) == digest
        if not restored:
            restore_backup(path, backup, digest)
            restored = True
        raise MergeError(f"Atomic write rejected; production unchanged: {exc}", restored=restored) from exc
    try:
        validate(read_json(path))
    except Exception as exc:
        restore_backup(path, backup, digest)
        raise MergeError(f"Post-write validation failed; backup restored: {exc}", restored=True) from exc
    outcome.written = True
    return outcome


def merge_order(entries):
    """Order archive/report candidates for merging (prioritization, not proof).

    Prefer final default-certified selections, then other default-certified ones,
    then probe-only certified; inside each group the fastest certificates first.
    Ratings are interleaved (highest first) so a merge mixes the 35/32/30 bands.
    """
    from .archive import is_certified_summary

    def group(entry):
        if entry.get("selected") and is_certified_summary(entry.get("certification")):
            return 0
        if is_certified_summary(entry.get("certification")):
            return 1
        if is_certified_summary(entry.get("probe")):
            return 2
        return None

    usable = []
    for entry in entries:
        rank = group(entry)
        if rank is None or (entry.get("production") or {}).get("merged"):
            continue
        evidence = entry.get("certification") if rank < 2 else entry.get("probe")
        usable.append((rank, evidence.get("elapsed", 0.0), entry["id"],
                       evidence.get("minimumRequiredRating") or 0.0, entry))
    usable.sort(key=lambda row: row[:3])
    ordered = []
    for rank in (0, 1, 2):
        buckets = {}
        for row in usable:
            if row[0] == rank:
                buckets.setdefault(row[3], []).append(row[4])
        ratings = sorted(buckets, reverse=True)
        while any(buckets[rating] for rating in ratings):
            for rating in ratings:
                if buckets[rating]:
                    ordered.append(buckets[rating].pop(0))
    return ordered
