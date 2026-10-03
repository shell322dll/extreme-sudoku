"""Phase 9 production batch: generate -> prefilter -> prioritize -> certify -> archive.

Nothing in this module writes production data. Its outputs are the research
archive, per-seed generation checkpoints and a batch report. Certification uses
the unchanged certifier; a short "probe" budget only decides what is worth a
full default-budget run, and production-merge certifies again from scratch.
"""
from dataclasses import asdict, dataclass, field, replace
from collections import Counter
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter

from ..certification import CertificationConfig, certify_puzzle as _certify_puzzle
from ..certification.io import read_json
from ..config import GeneratorConfig
from ..models import GENERATOR_VERSION, RejectionReason
from ..pipeline import PuzzleGenerator
from .archive import (Archive, archive_lock, atomic_write_text, certification_summary, content_id,
                      is_certified_summary, is_terminal, selected_unmerged, utc_now)
from .diversity import DiversityIndex, mask_distance, symmetry_fingerprint
from .models import (GENERATOR_REASON, NOT_ATTEMPTED, REPORT_KIND, Phase9Reason,
                     reason_for_result, rejection)
from .report import compute_counters
from .suitability import (CONCLUSIVE_SCOPE_LIMIT, EXTREME_FLOOR, assess_suitability,
                          features_from_generated, priority_key)

CHECKPOINT_KIND = "phase9-generation-checkpoint"


@dataclass
class BatchOptions:
    seeds: tuple
    archive: Path = Path("data/research/phase9_candidates.json")
    run_dir: Path | None = None
    production: Path | None = Path("data/production/puzzles.json")
    per_seed_count: int = 12
    difficulty: str = "Extreme"
    min_clues: int = 22
    max_clues: int = 30
    minimal: bool = True
    generation_seconds: float | None = 600.0
    max_attempts: int = 100000
    probe_seconds: float = 15.0
    shortlist: int = 20
    target_new: int = 10
    runtime_budget: float | None = 3600.0
    resume: bool = False
    retry_timeouts: bool = False
    include_high: bool = False
    archive_attempt_rejections: bool = True
    slow_fraction: float = 0.25
    run_id: str | None = None
    bands: tuple | None = None          # Deep required ratings to certify (None = all in scope)
    min_per_band: int = 0               # shortlist slots reserved per band (best first)
    reuse_archive: bool = False         # re-evaluate rated, non-final archive candidates
    command: list = field(default_factory=list)

    def validate(self):
        if any(type(seed) is not int for seed in self.seeds):
            raise ValueError("seeds must be integers")
        if not self.seeds and not self.reuse_archive:
            raise ValueError("at least one seed (or --reuse-archive) is required")
        if self.bands is not None:
            if not self.bands or any(type(b) not in (int, float) for b in self.bands):
                raise ValueError("bands must be a nonempty list of Deep required ratings")
            if not self.include_high and any(b >= CONCLUSIVE_SCOPE_LIMIT for b in self.bands):
                raise ValueError("bands >= 36 are outside the conclusive scope (use --include-high for research)")
            if any(b < EXTREME_FLOOR for b in self.bands):
                raise ValueError("bands below 30 cannot be Extreme")
        if type(self.min_per_band) is not int or self.min_per_band < 0:
            raise ValueError("min_per_band must be a nonnegative integer")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be distinct")
        if self.difficulty not in ("Extreme", "Ultra Extreme"):
            raise ValueError("difficulty must be Extreme or Ultra Extreme")
        for name in ("per_seed_count", "max_attempts", "target_new"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.shortlist) is not int or self.shortlist < 0:
            raise ValueError("shortlist must be a nonnegative integer (0 = no cap)")
        if self.probe_seconds < 0 or not 0 < self.slow_fraction <= 1:
            raise ValueError("probe_seconds must be >= 0 and slow_fraction in (0, 1]")
        for name in ("generation_seconds", "runtime_budget"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive")
        GeneratorConfig(seed=self.seeds[0] if self.seeds else None, min_clues=self.min_clues, max_clues=self.max_clues,
                        target_difficulty=self.difficulty, require_minimal=self.minimal,
                        max_attempts=self.max_attempts)
        if self.resume and self.run_dir is None:
            raise ValueError("--resume needs the --run-dir of the interrupted run")
        archive = Path(self.archive).resolve()
        run_dir = Path(self.run_dir).resolve() if self.run_dir is not None else None
        production_dir = (Path(self.production).resolve().parent if self.production is not None
                          else Path("data/production").resolve())
        for label, path in (("archive", archive), ("run directory", run_dir)):
            if path is not None and (path == production_dir or production_dir in path.parents):
                raise ValueError(f"The {label} must not be inside the production folder {production_dir}")
        if self.production is not None and archive == Path(self.production).resolve():
            raise ValueError("archive and production database must be different files")
        if run_dir is not None and archive in (run_dir, run_dir / "batch_report.json"):
            raise ValueError("archive must not be the run directory or its report")


class _RecordingGenerator(PuzzleGenerator):
    """Unchanged generator; additionally remembers rejected attempts' puzzles.

    Only ``_construct``/``_attempt`` are wrapped (results are passed through
    unmodified), so generation stays byte-for-byte the same per (seed, config).
    """

    def __init__(self, config):
        super().__init__(config)
        self.outcomes = []
        self._last = None

    def _construct(self, seed):
        candidate, cache = super()._construct(seed)
        self._last = candidate
        return candidate, cache

    def _attempt(self, run_seed, attempt_seed, seen):
        self._last = None
        record, reason = super()._attempt(run_seed, attempt_seed, seen)
        if record is None:
            puzzle = "".join(map(str, self._last.to_puzzle())) if self._last is not None else None
            self.outcomes.append((self.stats.attempts, attempt_seed, reason, puzzle))
        return record, reason


def _generator_params(options, seed):
    return {"seed": seed, "difficulty": options.difficulty, "minClues": options.min_clues,
            "maxClues": options.max_clues, "minimal": options.minimal,
            "perSeedCount": options.per_seed_count, "maxAttempts": options.max_attempts,
            "ratingMode": "quick_then_deep", **_provenance()}


def _provenance():
    """Code identity behind content verdicts (stale checkpoints/verdicts are redone)."""
    from ..certification.pipeline import algorithm_fingerprint
    return {"algorithmFingerprint": algorithm_fingerprint(), "generatorVersion": GENERATOR_VERSION}


def generate_seed(options, seed, *, timeout=None, run_id=""):
    """Run the existing generator for one seed and return archive-shaped entries.

    Reproducible per (seed, config) as long as the timeout does not cut the run.
    """
    config = GeneratorConfig(seed=seed, min_clues=options.min_clues, max_clues=options.max_clues,
                             target_difficulty=options.difficulty, require_minimal=options.minimal,
                             max_attempts=options.max_attempts, rating_mode="quick_then_deep",
                             timeout_seconds=timeout)
    provenance = _provenance()
    generator = _RecordingGenerator(config)
    started = perf_counter()
    result = generator.generate_many(options.per_seed_count)
    seconds = perf_counter() - started
    rows = []
    for puzzle in (*result.puzzles, *result.preliminary_candidates):
        rows.append((puzzle.attempts, {
            "id": puzzle.id, "puzzle": puzzle.puzzle, "solution": puzzle.solution, "clues": puzzle.clues,
            "minimal": puzzle.minimal,
            "source": {"kind": "generate", "seed": seed, "attemptSeed": puzzle.attempt_seed,
                       "attempt": puzzle.attempts, "runId": run_id,
                       "onTarget": puzzle.difficulty == options.difficulty},
            "deep": {**features_from_generated(puzzle), **provenance}}))
    rejected = Counter()
    for attempt, attempt_seed, reason, puzzle in generator.outcomes:
        mapped = GENERATOR_REASON[RejectionReason(reason)]
        rejected[mapped.value] += 1
        # Generator DUPLICATE rows repeat an earlier row of this seed (same ID).
        if puzzle is None or not options.archive_attempt_rejections or reason == RejectionReason.DUPLICATE:
            continue
        rows.append((attempt, {
            "id": content_id(puzzle), "puzzle": puzzle, "clues": sum(c != "0" for c in puzzle),
            "source": {"kind": "generate", "seed": seed, "attemptSeed": attempt_seed, "attempt": attempt,
                       "runId": run_id},
            "stage": "generation",
            # Solution omitted to keep the archive compact; reproducible with
            # generator.solution_generator.generate_solution(attemptSeed).
            "rejection": rejection(mapped, f"generator: {RejectionReason(reason).value}", **provenance)}))
    rows.sort(key=lambda row: row[0])
    stats = result.stats.to_dict()
    unique = sum(1 for _, _, reason, _ in generator.outcomes
                 if reason not in (RejectionReason.NOT_UNIQUE, RejectionReason.OUTSIDE_CLUE_RANGE))
    unique += len(result.puzzles) + len(result.preliminary_candidates)
    return {"kind": CHECKPOINT_KIND, "params": _generator_params(options, seed), "seed": seed,
            "complete": result.complete, "timedOut": result.stats.timed_out,
            "seconds": round(seconds, 3), "attempts": result.stats.attempts, "unique": unique,
            "deepRated": stats["stageCalls"].get("deep_rating", 0),
            "attemptRejections": dict(sorted(rejected.items())),
            "entries": [entry for _, entry in rows]}


def _git_head():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10,
                              cwd=Path(__file__).resolve().parents[2]).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _fingerprints(probe_config):
    from ..certification.pipeline import algorithm_fingerprint
    return {"certificationConfigFingerprint": CertificationConfig().fingerprint(),
            "probeConfigFingerprint": probe_config.fingerprint() if probe_config else None,
            "algorithmFingerprint": algorithm_fingerprint()}


def _load_production(path):
    if path is None or not Path(path).exists():
        return []
    data = read_json(path)
    puzzles = data.get("puzzles") if isinstance(data, dict) else None
    if not isinstance(puzzles, list):
        raise ValueError(f"{path}: production database has no puzzles array")
    return puzzles


def _archived_inputs(archive, options, terminal_keys):
    """Rated, not-yet-final archive candidates to re-evaluate without regenerating.

    Only the content and preliminary Deep metrics are reused; stage, rejection,
    suitability and diversity are recomputed by this run (probe evidence is kept
    and reused only when its fingerprints match).
    """
    inputs = []
    for old in archive.candidates:
        if "deep" not in old or not old.get("solution") or is_terminal(old, **terminal_keys):
            continue
        if (old.get("production") or {}).get("merged") or old.get("selected"):
            continue
        inputs.append({key: old[key] for key in ("id", "puzzle", "solution", "clues", "minimal", "source", "deep")
                       if key in old})
    return inputs


def _band_order(pool, options):
    """Shortlist order: optional band filter, optional per-band reservation, then score.

    Prioritization only. ``bands`` restricts which Deep required ratings are
    certified in this run; ``min_per_band`` reserves the best N of each band at
    the front of the queue (higher band first), so a strict score preference for
    one band cannot starve the others. Nothing changes how a candidate is certified.
    """
    bands = set(options.bands) if options.bands else None
    wanted = [e for e in pool if bands is None or e["deep"]["requiredRating"] in bands]
    excluded = [e for e in pool if bands is not None and e["deep"]["requiredRating"] not in bands]
    reserved = []
    if options.min_per_band:
        by_band = {}
        for entry in wanted:  # already in priority order
            by_band.setdefault(entry["deep"]["requiredRating"], []).append(entry)
        queues = [by_band[band][:options.min_per_band] for band in sorted(by_band, reverse=True)]
        while any(queues):
            for queue in queues:
                if queue:
                    reserved.append(queue.pop(0))
    chosen = {entry["id"] for entry in reserved}
    return reserved + [e for e in wanted if e["id"] not in chosen], excluded


def run_batch(options, *, certify=_certify_puzzle, log=None, clock=perf_counter):
    """Execute one batch under the archive lock. Returns the report dict."""
    options.validate()
    with archive_lock(options.archive, " ".join(map(str, options.command)) or "production-batch"):
        return _run_batch(options, certify=certify, log=log, clock=clock)


def _run_batch(options, *, certify, log, clock):
    log = log or (lambda message: print(message, file=sys.stderr, flush=True))
    started = clock()
    deadline = None if options.runtime_budget is None else started + options.runtime_budget

    def remaining():
        return None if deadline is None else deadline - clock()

    run_id = options.run_id or utc_now().replace("-", "").replace(":", "")
    run_dir = Path(options.run_dir) if options.run_dir is not None else Path("data/research/phase9/runs") / run_id
    if options.resume and not run_dir.exists():
        raise ValueError(f"--resume: run directory does not exist: {run_dir}")
    default_config = CertificationConfig()
    probe_config = replace(default_config, time_budget=float(options.probe_seconds)) if options.probe_seconds else None
    fingerprints = _fingerprints(probe_config)
    slow_limit = options.slow_fraction * default_config.time_budget
    archive = Archive.load(options.archive)
    production = _load_production(options.production)
    stage_seconds = Counter()
    terminal_keys = dict(default_fingerprint=fingerprints["certificationConfigFingerprint"],
                         probe_fingerprint=fingerprints["probeConfigFingerprint"],
                         algorithm_fingerprint=fingerprints["algorithmFingerprint"],
                         retry_timeouts=options.retry_timeouts)
    seed_info = {}

    def save_archive():
        moment = clock()
        archive.save(fingerprints=fingerprints)
        stage_seconds["archive"] += clock() - moment

    # ---- 1. inputs: generation (checkpointed per seed) and/or archive reuse -------
    sources = []
    for seed in options.seeds:
        info = seed_info.setdefault(seed, {})
        checkpoint_path = run_dir / "checkpoints" / f"generate-{seed}.json"
        checkpoint = None
        if options.resume and checkpoint_path.exists():
            loaded = read_json(checkpoint_path)
            if loaded.get("kind") == CHECKPOINT_KIND and loaded.get("params") == _generator_params(options, seed):
                checkpoint = loaded
                info["fromCheckpoint"] = True
                log(f"[seed {seed}] generation loaded from checkpoint ({len(loaded['entries'])} entries)")
        if checkpoint is None:
            left = remaining()
            if left is not None and left <= 1:
                info["skipped"] = "runtime budget exhausted before generation"
                log(f"[seed {seed}] skipped: runtime budget exhausted")
                sources.append((seed, {"entries": []}))
                continue
            timeout = options.generation_seconds
            if left is not None:
                timeout = left if timeout is None else min(timeout, left)
            log(f"[seed {seed}] generating up to {options.per_seed_count} {options.difficulty} "
                f"(clues {options.min_clues}-{options.max_clues}, timeout {timeout and round(timeout)} s)")
            moment = clock()
            checkpoint = generate_seed(options, seed, timeout=timeout, run_id=run_id)
            stage_seconds["generation"] += clock() - moment
            atomic_write_text(checkpoint_path, json.dumps(checkpoint, ensure_ascii=False, indent=1) + "\n")
            info["fromCheckpoint"] = False
        info.update(timedOut=checkpoint["timedOut"], complete=checkpoint["complete"],
                    generationSeconds=checkpoint["seconds"])
        log(f"[seed {seed}] attempts {checkpoint['attempts']}, records "
            f"{sum('deep' in e for e in checkpoint['entries'])}, timed out {checkpoint['timedOut']}")
        sources.append((seed, checkpoint))
    if options.reuse_archive:
        reused = _archived_inputs(archive, options, terminal_keys)
        sources.append(("archive", {"entries": reused}))
        log(f"Archive reuse: {len(reused)} rated, non-final candidates re-evaluated without regeneration")

    # ---- 2. prefilter: archive/resume, exact duplicates, suitability -------------
    moment = clock()
    reference = DiversityIndex()
    for record in production:
        reference.add(record, "production")
    for old in archive.candidates:
        # Only still-valid selections (current fingerprints) block new content.
        if (selected_unmerged([old]) and is_terminal(old, **terminal_keys)
                and old["id"] not in reference.by_id):
            reference.add({**old, "techniques": old["certification"].get("techniques")}, "archive-selected")
    resumed_selected, skipped_ids = [], set()
    run_seen = DiversityIndex(one_per_solution=False)
    eligible, processed = [], []
    for label, checkpoint in sources:
        for entry in checkpoint["entries"]:
            old = archive.get(entry["id"])
            if old is not None and is_terminal(old, **terminal_keys):
                skipped_ids.add(entry["id"])
                if selected_unmerged([old]) and not any(e["id"] == old["id"] for e in resumed_selected):
                    resumed_selected.append(old)
                continue
            if entry["id"] in run_seen.by_id:
                continue  # produced again by another seed: counted as duplicatesInRun
            if entry.get("rejection"):
                archive.upsert(entry)  # attempt-level generator rejection
                continue
            entry = dict(entry)
            entry["certification"] = {"status": NOT_ATTEMPTED}
            entry["selected"] = False
            entry["production"] = {"merged": False, "mergedAt": None}
            entry["origin"] = "archive-reuse" if label == "archive" else "generated"
            entry["evaluatedRunId"] = run_id
            if old is not None:
                # Keep earlier probe evidence (reused below when its fingerprints match).
                if "probe" in old:
                    entry["probe"] = old["probe"]
                entry["source"] = {**entry["source"], "firstRunId": old.get("source", {}).get(
                    "firstRunId", old.get("source", {}).get("runId"))}
            entry["diversity"] = {"symmetryFingerprint": symmetry_fingerprint(entry["puzzle"])}
            nearest_id, nearest_distance = reference.nearest(entry)
            entry["diversity"].update(nearestReferenceId=nearest_id, nearestMaskDistance=nearest_distance)
            processed.append(entry)
            duplicate = reference.exact_duplicate(entry)
            run_seen.add(entry, f"run {label}")
            if duplicate:
                entry.update(stage="prefilter", rejection=rejection(duplicate[0], duplicate[1]))
                continue
            assessment = assess_suitability(entry["deep"], include_high=options.include_high)
            entry["suitability"] = assessment.to_dict()
            if not assessment.eligible:
                # Deep-based verdict: carries the code identity of the Deep rating run.
                entry.update(stage="prefilter", rejection=rejection(
                    assessment.skip_reason, assessment.detail,
                    algorithmFingerprint=entry["deep"].get("algorithmFingerprint"),
                    generatorVersion=entry["deep"].get("generatorVersion")))
                continue
            eligible.append(entry)
    eligible.sort(key=priority_key)
    accepted_run = DiversityIndex()
    pool = []
    for entry in eligible:
        near = reference.near_duplicate(entry) or accepted_run.near_duplicate(entry)
        if near:
            entry.update(stage="prefilter", rejection=rejection(near[0], near[1]))
            continue
        accepted_run.add(entry, f"run seed {entry['source'].get('seed')}")
        pool.append(entry)
    ordered, excluded = _band_order(pool, options)
    cap = options.shortlist or len(ordered)
    shortlist, rest = ordered[:cap], ordered[cap:]
    for entry in shortlist:
        entry.update(stage="shortlist", rejection=None)
    for entry in rest:
        entry.update(stage="prefilter", rejection=rejection(Phase9Reason.NOT_SHORTLISTED,
                     f"outside top {cap} of the shortlist order"))
    for entry in excluded:
        entry.update(stage="prefilter", rejection=rejection(Phase9Reason.NOT_SHORTLISTED,
                     f"Deep band {entry['deep']['requiredRating']:g} not requested (--bands)"))
    for entry in processed:
        archive.upsert(entry)
    stage_seconds["prefilter"] += clock() - moment
    save_archive()
    bands = dict(sorted(Counter(str(e["deep"]["requiredRating"]) for e in shortlist).items()))
    log(f"Prefilter: {sum(len(c['entries']) for _, c in sources)} entries, {len(processed)} rated candidates "
        f"processed, {len(pool)} eligible, {len(shortlist)} shortlisted (by Deep band {bands}), "
        f"{len(resumed_selected)} already selected")

    # ---- 3. certification of the shortlist (probe -> fresh default) -------------
    selected = list(resumed_selected)
    selection_index = DiversityIndex()
    for record in production:
        selection_index.add(record, "production")
    for old in selected:
        selection_index.add({**old, "techniques": old["certification"].get("techniques")}, "selected")
    calibration = []
    for position, entry in enumerate(shortlist, 1):
        if len(selected) >= options.target_new:
            entry.update(rejection=rejection(Phase9Reason.NOT_SELECTED_TARGET_REACHED,
                                             f"target of {options.target_new} new certified reached"))
            archive.upsert(entry)
            continue
        left = remaining()
        if left is not None and left <= 0:
            entry.update(rejection=rejection(Phase9Reason.NOT_SELECTED_BUDGET, "runtime budget exhausted"))
            archive.upsert(entry)
            continue
        if probe_config is None:
            entry.pop("probe", None)  # probing disabled: never act on an old probe
        probe = entry.get("probe")
        reuse_probe = bool(probe and probe.get("configFingerprint") == fingerprints["probeConfigFingerprint"]
                           and probe.get("algorithmFingerprint") == fingerprints["algorithmFingerprint"])
        if probe_config is not None and not reuse_probe:
            moment = clock()
            result = certify(entry["puzzle"], entry.get("solution"), puzzle_id=entry["id"],
                             config=probe_config, fresh=True)
            stage_seconds["probe"] += clock() - moment
            entry["probe"] = certification_summary(result, probe_config, "probe")
            entry["stage"] = "probe"
            log(f"[{position}/{len(shortlist)}] probe {entry['id']} deep {entry['deep']['requiredRating']:g} "
                f"score {entry['suitability']['score']:.1f} -> {result.status.value} ({result.elapsed_seconds:.1f} s)")
        probe = entry.get("probe")
        if probe is not None and not is_certified_summary(probe):
            retry = options.retry_timeouts and probe["status"] == "CERTIFICATION_TIMEOUT"
            if not retry:
                reason = reason_for_result_summary(probe)
                entry["stage"] = "probe"
                entry["rejection"] = rejection(reason, "probe: " + ",".join([probe["status"], *probe["failureReasons"]]),
                                               budget="probe")
                calibration.append([entry["suitability"]["score"], entry["deep"]["requiredRating"], probe["status"], None])
                archive.upsert(entry)
                save_archive()
                continue
        moment = clock()
        result = certify(entry["puzzle"], entry.get("solution"), puzzle_id=entry["id"],
                         config=default_config, fresh=True)
        stage_seconds["certification"] += clock() - moment
        summary = certification_summary(result, default_config, "default")
        entry["certification"] = summary
        entry["stage"] = "certification"
        calibration.append([entry["suitability"]["score"], entry["deep"]["requiredRating"],
                            (probe or {}).get("status"), summary["status"]])
        reason = reason_for_result(result)
        if reason is not None:
            entry["rejection"] = rejection(reason, ",".join([summary["status"], *summary["failureReasons"]]),
                                           budget="default")
        else:
            near = selection_index.check(entry)
            if result.elapsed_seconds > slow_limit:
                entry["rejection"] = rejection(Phase9Reason.NOT_SELECTED_SLOW_CERTIFICATE,
                    f"certified in {result.elapsed_seconds:.1f} s > {slow_limit:g} s (CI robustness rule)")
            elif near:
                entry["rejection"] = rejection(near[0], near[1])
            else:
                entry["diversity"]["warnings"] = selection_index.technique_warnings(
                    {**entry, "techniques": summary["techniques"]})
                selection_index.add({**entry, "techniques": summary["techniques"]}, "selected")
                entry["selected"] = True
                entry["rejection"] = None
                selected.append(entry)
        log(f"[{position}/{len(shortlist)}] certify {entry['id']} -> {summary['status']} "
            f"min {summary['minimumRequiredRating']} ({summary['elapsed']:.1f} s)"
            + (" SELECTED" if entry["selected"] else ""))
        archive.upsert(entry)
        save_archive()

    save_archive()  # target/budget skips after the last certification

    # ---- 4. report ---------------------------------------------------------------
    per_source, total = compute_counters(sources, {e["id"]: e for e in processed}, skipped_ids=skipped_ids)
    for row in per_source:
        row.update(seed_info.get(row["seed"], {}))
    total_seconds = clock() - started
    total["runtimeSeconds"] = {**{key: round(value, 3) for key, value in sorted(stage_seconds.items())},
                               "total": round(total_seconds, 3)}
    report = build_report(run_id=run_id, options=options, run_dir=run_dir, fingerprints=fingerprints,
                          slow_limit=slow_limit, per_source=per_source, total=total, selected=selected,
                          calibration=calibration)
    atomic_write_text(run_dir / "batch_report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    summary_keys = ("generated", "unique", "rated", "shortlisted", "certificationAttempts", "certified",
                    "inconclusive", "timeouts", "selected")
    log("Batch summary: " + json.dumps({**{k: total[k] for k in summary_keys},
        "rejected": sum(total["rejected"].values()), "runtime": round(total_seconds, 1),
        "certificationYield": round(total["certificationYield"], 3),
        "generationYield": round(total["generationYield"], 4)}))
    return report


def build_report(*, run_id, options, run_dir, fingerprints, slow_limit, per_source, total, selected, calibration,
                 git_head=None, python=None, finished_at=None):
    if isinstance(options, dict):
        options_dict = dict(options)
        command = options_dict.pop("command", None)
    else:
        options_dict = {key: (str(value) if isinstance(value, Path) else list(value) if isinstance(value, tuple)
                              else value) for key, value in asdict(options).items() if key != "command"}
        command = list(options.command)
    same_solution = [mask_distance(a["puzzle"], b["puzzle"]) for i, a in enumerate(selected)
                     for b in selected[i + 1:] if a.get("solution") == b.get("solution")]
    return {
        "kind": REPORT_KIND, "reportVersion": 2, "counterDefinitions": "docs/DATA_FORMAT.md section 57",
        "runId": run_id, "finishedAt": finished_at or utc_now(),
        "command": command, "gitHead": git_head or _git_head(), "python": python or platform.python_version(),
        "options": options_dict, "runDir": str(run_dir), "archive": str(options_dict.get("archive")),
        **fingerprints, "slowCertificateLimitSeconds": slow_limit,
        "perSeed": per_source, "total": total,
        "selected": [{"id": e["id"], "puzzle": e["puzzle"], "solution": e["solution"], "clues": e["clues"],
                      "seed": e["source"].get("seed"),
                      "minimumRequiredRating": e["certification"]["minimumRequiredRating"],
                      "status": e["certification"]["status"], "elapsed": e["certification"]["elapsed"],
                      "warnings": (e.get("diversity") or {}).get("warnings", [])} for e in selected],
        "diversity": {"selectedSameSolutionPairs": len(same_solution),
                      "minSameSolutionMaskDistance": min(same_solution) if same_solution else None,
                      "selectedByRating": dict(sorted(Counter(
                          str(e["certification"]["minimumRequiredRating"]) for e in selected).items()))},
        "suitabilityCalibration": calibration,
        "note": "Research report. Selected candidates still need production-merge (fresh default certification).",
    }


def recompute_report(run_dir, archive_path=None, output=None):
    """Rebuild a run's report counters from its checkpoints + archive into a NEW file.

    The original ``batch_report.json`` is never modified. Runtime, options,
    calibration and fingerprints are copied from the original report. Counters
    reflect the archive's CURRENT state of the run's candidates.
    """
    run_dir = Path(run_dir)
    original_path = run_dir / "batch_report.json"
    original = read_json(original_path)
    if original.get("kind") != REPORT_KIND:
        raise ValueError(f"{original_path}: not a Phase 9 batch report")
    output = Path(output) if output is not None else run_dir / "batch_report.recomputed.json"
    if output.resolve() == original_path.resolve():
        raise ValueError("Refusing to overwrite the original batch_report.json")
    archive = Archive.load(archive_path or original.get("archive"))
    if not archive.path.exists():
        raise ValueError(f"Archive not found: {archive.path}")
    state = {e["id"]: e for e in archive.candidates}
    sources = []
    for row in original.get("perSeed", []):
        label = row["seed"]
        if label == "archive":
            entries = [e for e in archive.candidates if e.get("origin") == "archive-reuse"
                       and e.get("evaluatedRunId") == original["runId"] and "deep" in e]
            sources.append((label, {"entries": entries}))
            continue
        path = run_dir / "checkpoints" / f"generate-{label}.json"
        if not path.exists():
            raise ValueError(f"Missing generation checkpoint: {path}")
        sources.append((label, read_json(path)))
    per_source, total = compute_counters(sources, state)
    for row, old in zip(per_source, original.get("perSeed", [])):
        for key in ("fromCheckpoint", "timedOut", "complete", "generationSeconds", "skipped"):
            if key in old:
                row[key] = old[key]
    total["runtimeSeconds"] = original.get("total", {}).get("runtimeSeconds", {})
    fingerprints = {key: original.get(key) for key in ("certificationConfigFingerprint", "probeConfigFingerprint",
                                                        "algorithmFingerprint")}
    selected = [state[item["id"]] for item in original.get("selected", []) if item["id"] in state]
    options = dict(original.get("options", {}))
    options["command"] = original.get("command")
    report = build_report(run_id=original["runId"], options=options, run_dir=run_dir, fingerprints=fingerprints,
                          slow_limit=original.get("slowCertificateLimitSeconds"), per_source=per_source,
                          total=total, selected=selected, calibration=original.get("suitabilityCalibration", []),
                          git_head=original.get("gitHead"), python=original.get("python"),
                          finished_at=original.get("finishedAt"))
    report["recomputedAt"] = utc_now()
    report["recomputedFrom"] = {"report": str(original_path), "archive": str(archive.path),
                                "note": "Counters recomputed from checkpoints + current archive state; "
                                        "runtime copied from the original report."}
    atomic_write_text(output, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report, output


def reason_for_result_summary(summary):
    from .models import reason_for_status
    if is_certified_summary(summary):
        return None
    return reason_for_status(summary["status"], summary.get("failureReasons", ())) or Phase9Reason.PROOF_INVALID
