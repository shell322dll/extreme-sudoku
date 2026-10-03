"""Compact Phase 9 research archive (``data/research/phase9_candidates.json``).

The archive keeps EVERY candidate a batch looked at (rejected, skipped,
inconclusive, timed out and certified) with compact certification summaries
only. It is research data: it has no ``puzzles`` array and no ``datasetKind``,
so neither the production loaders nor ``load_candidates`` accept it, and nothing
in it can be published without a fresh certification in ``production-merge``.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile

from ..certification.models import CertificationStatus
from ..models import GENERATOR_VERSION
from ..certification.io import read_json
from .models import (ARCHIVE_KIND, ARCHIVE_VERSION, CONTENT_TERMINAL_REASONS, NOT_ATTEMPTED,
                     PRODUCTION_STATUSES, Phase9Reason)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def content_id(puzzle):
    """The project's deterministic ID scheme (same as generator/certifier/exporter)."""
    return "puzzle-" + hashlib.sha256(puzzle.encode("utf-8")).hexdigest()[:20]


def atomic_write_text(path, text, *, check=None):
    """Temp file in the destination folder, fsync, readback, os.replace, verify."""
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
        if temporary.read_text(encoding="utf-8") != text:
            raise OSError(f"Temporary readback differs: {temporary}")
        if check is not None:
            check(temporary)
        os.replace(temporary, path)
        if path.read_text(encoding="utf-8") != text:
            raise OSError(f"Destination readback differs: {path}")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=False, separators=(",", ":"), allow_nan=False)


def certification_summary(result, config, budget):
    """Compact, JSON-native summary of a CertificationResult (no full evidence)."""
    ssl_failed, ssl_g4 = [], None
    for threshold in result.threshold_results:
        ssl = (threshold.telemetry or {}).get("stuck_state_lemma") or {}
        for guard in ssl.get("failed_guards") or ():
            if guard not in ssl_failed:
                ssl_failed.append(guard)
        for guard in ssl.get("guards") or ():
            if guard.get("guard") == "G4" and ssl_g4 is None and ssl.get("outcome") != "PROVEN":
                ssl_g4 = guard.get("detail")
    counts = Counter(step.technique for step in result.certified_path)
    return {
        "budget": budget, "timeBudget": config.time_budget,
        "configFingerprint": result.config_fingerprint,
        "algorithmFingerprint": result.algorithm_fingerprint,
        "status": result.status.value,
        "failureReasons": [reason.value for reason in result.failure_reasons],
        "productionEligible": bool(result.production_eligible),
        "minimumRequiredRating": result.minimum_required_rating,
        "observedUpperRating": result.observed_upper_rating,
        "negativeProofKind": result.negative_proof_kind,
        "thresholds": [[t.threshold, t.status.value, t.states_explored, list(t.limit_reasons[:4])]
                       for t in result.threshold_results],
        "sslFailedGuards": ssl_failed, "sslG4Detail": ssl_g4,
        "certifiedBottlenecks": result.certified_bottlenecks,
        "advancedSteps": result.advanced_steps,
        "techniques": dict(sorted(counts.items())),
        "elapsed": round(result.elapsed_seconds, 3),
    }


def is_certified_summary(summary):
    return bool(summary) and summary.get("status") in PRODUCTION_STATUSES and summary.get("productionEligible") is True


def is_terminal(entry, *, default_fingerprint, probe_fingerprint, algorithm_fingerprint, retry_timeouts=False):
    """True when re-processing this archived candidate cannot change its outcome."""
    rejection = entry.get("rejection") or {}
    # Content verdicts (NOT_UNIQUE, TOO_EASY, ...) are final only for the same
    # rating/certification algorithms and the same generator version that made them.
    if (rejection.get("reason") in {reason.value for reason in CONTENT_TERMINAL_REASONS}
            and entry.get("stage") in ("generation", "prefilter")
            and rejection.get("algorithmFingerprint") == algorithm_fingerprint
            and rejection.get("generatorVersion") == GENERATOR_VERSION):
        return True
    certification = entry.get("certification") or {}
    if (certification.get("status", NOT_ATTEMPTED) != NOT_ATTEMPTED
            and certification.get("configFingerprint") == default_fingerprint
            and certification.get("algorithmFingerprint") == algorithm_fingerprint):
        return True
    probe = entry.get("probe") or {}
    if (probe and not is_certified_summary(probe)
            and probe.get("configFingerprint") == probe_fingerprint
            and probe.get("algorithmFingerprint") == algorithm_fingerprint):
        return not (retry_timeouts and probe.get("status") == CertificationStatus.CERTIFICATION_TIMEOUT.value)
    return False


FINGERPRINT_KEYS = ("certificationConfigFingerprint", "probeConfigFingerprint", "algorithmFingerprint")


class Archive:
    def __init__(self, path, data=None):
        self.path = Path(path)
        data = data or {}
        self.created_at = data.get("createdAt")
        self.fingerprints = {key: data[key] for key in FINGERPRINT_KEYS if key in data}
        self.candidates = list(data.get("candidates", []))
        self.index = {}
        for position, entry in enumerate(self.candidates):
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not isinstance(entry.get("puzzle"), str):
                raise ValueError(f"{self.path}: invalid archive candidate at position {position}")
            if entry["id"] in self.index:
                raise ValueError(f"{self.path}: duplicate archive ID {entry['id']}")
            if content_id(entry["puzzle"]) != entry["id"]:
                raise ValueError(f"{self.path}: ID does not match puzzle content for {entry['id']}")
            self.index[entry["id"]] = position

    @classmethod
    def load(cls, path):
        path = Path(path)
        if not path.exists():
            return cls(path)
        data = read_json(path)
        if not isinstance(data, dict) or data.get("kind") != ARCHIVE_KIND:
            raise ValueError(f"{path}: not a Phase 9 candidate archive")
        if data.get("archiveVersion") != ARCHIVE_VERSION or not isinstance(data.get("candidates"), list):
            raise ValueError(f"{path}: unsupported archive version")
        return cls(path, data)

    def get(self, identifier):
        position = self.index.get(identifier)
        return None if position is None else self.candidates[position]

    def __contains__(self, identifier):
        return identifier in self.index

    def upsert(self, entry):
        if content_id(entry["puzzle"]) != entry["id"]:
            raise ValueError(f"ID does not match puzzle content: {entry['id']}")
        position = self.index.get(entry["id"])
        if position is None:
            self.index[entry["id"]] = len(self.candidates)
            self.candidates.append(entry)
        else:
            self.candidates[position] = entry

    def stats(self):
        """``byStatus`` = latest certifier outcome per candidate: the default-budget status,
        else ``PROBE:<status>`` (short research budget, never a production status), else
        NOT_ATTEMPTED. ``byFinalStatus``/``byProbeStatus`` keep both dimensions separate."""
        def latest(entry):
            final = (entry.get("certification") or {}).get("status", NOT_ATTEMPTED)
            if final != NOT_ATTEMPTED:
                return final
            probe = entry.get("probe")
            return f"PROBE:{probe['status']}" if probe else NOT_ATTEMPTED
        statuses = Counter(latest(entry) for entry in self.candidates)
        finals = Counter((entry.get("certification") or {}).get("status", NOT_ATTEMPTED) for entry in self.candidates)
        probes = Counter(entry["probe"]["status"] for entry in self.candidates if entry.get("probe"))
        reasons = Counter((entry.get("rejection") or {}).get("reason") for entry in self.candidates
                          if entry.get("rejection"))
        return {"total": len(self.candidates), "selected": sum(bool(e.get("selected")) for e in self.candidates),
                "merged": sum(bool((e.get("production") or {}).get("merged")) for e in self.candidates),
                "byStatus": dict(sorted(statuses.items())), "byFinalStatus": dict(sorted(finals.items())),
                "byProbeStatus": dict(sorted(probes.items())), "byRejection": dict(sorted(reasons.items()))}

    def render(self, *, fingerprints):
        header = {"kind": ARCHIVE_KIND, "archiveVersion": ARCHIVE_VERSION,
                  "createdAt": self.created_at or utc_now(), "updatedAt": utc_now(),
                  "note": "Research archive. Not production data; statuses here are never "
                          "trusted by production-merge (fresh default certification only).",
                  **fingerprints, "stats": self.stats()}
        lines = ["{"]
        for key, value in header.items():
            lines.append(f"  {json.dumps(key)}: {compact_json(value)},")
        lines.append('  "candidates": [')
        lines.append(",\n".join("    " + compact_json(entry) for entry in self.candidates))
        lines.append("  ]")
        lines.append("}")
        return "\n".join(line for line in lines if line != "") + "\n"

    def save(self, *, fingerprints=None):
        fingerprints = dict(fingerprints if fingerprints is not None else self.fingerprints)
        self.fingerprints = fingerprints
        if self.created_at is None:
            self.created_at = utc_now()
        text = self.render(fingerprints=fingerprints)
        json.loads(text)  # must be valid JSON before touching the destination

        def check(temporary):
            loaded = Archive.load(temporary)
            if len(loaded.candidates) != len(self.candidates):
                raise OSError("Archive readback lost candidates")
        atomic_write_text(self.path, text, check=check)


def selected_unmerged(entries):
    return [e for e in entries if e.get("selected") and is_certified_summary(e.get("certification"))
            and not (e.get("production") or {}).get("merged")]


def rejection_reason(entry):
    value = (entry.get("rejection") or {}).get("reason")
    return Phase9Reason(value) if value else None


class ArchiveLockedError(ValueError):
    pass


class archive_lock:
    """Exclusive ``<archive>.lock`` shared by production-batch and production-merge.

    Created with O_CREAT|O_EXCL and removed on exit (also after errors). A lock
    left behind by a killed process is stale: when no batch/merge is running,
    delete the ``.lock`` file by hand (it names the PID, host, time and command).
    """

    def __init__(self, archive_path, command=""):
        self.path = Path(str(archive_path) + ".lock")
        self.command = command
        self.acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                holder = self.path.read_text(encoding="utf-8").strip()
            except OSError:
                holder = "unknown holder"
            raise ArchiveLockedError(
                f"Archive is locked by another production-batch/production-merge: {self.path} ({holder}). "
                "If no such process is running the lock is stale: delete the file and retry.") from None
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": os.getpid(), "host": platform.node(), "since": utc_now(),
                                     "command": self.command}) + "\n")
        self.acquired = True
        return self

    def __exit__(self, *exc):
        if self.acquired:
            self.acquired = False
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        return False
