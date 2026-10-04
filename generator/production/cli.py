"""Command lines: ``python -m generator production-batch`` and ``production-merge``."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys

from ..certification.io import read_json
from .archive import Archive, ArchiveLockedError, archive_lock, atomic_write_text, utc_now
from .batch import BatchOptions, recompute_report, run_batch
from .merge import MergeError, merge_order, merge_production


def _seeds(values):
    seeds = []
    for value in values:
        for part in str(value).split(","):
            if part.strip():
                seeds.append(int(part))
    return tuple(seeds)


def batch_main(argv=None, *, run=run_batch):
    parser = argparse.ArgumentParser(prog="python -m generator production-batch",
        description="Generate and verify Easy/Medium or certify Extreme candidates in research storage. "
                    "Never writes production data (use production-merge).")
    parser.add_argument("--seeds", nargs="+", action="extend", default=[],
                        help="Seeds, e.g. 9101,9102 or 9101 9102 (optional with --reuse-archive)")
    parser.add_argument("--per-seed-count", "--target-count", dest="per_seed_count", type=int, default=12,
                        help="Accepted puzzles requested from the generator per seed")
    parser.add_argument("--difficulty", choices=("Easy", "Medium", "Extreme", "Ultra Extreme"), default="Extreme")
    parser.add_argument("--min-clues", type=int, default=22)
    parser.add_argument("--max-clues", type=int, default=30)
    parser.add_argument("--minimal", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--generation-seconds", type=float, default=600.0, help="Generator timeout per seed")
    parser.add_argument("--max-attempts", type=int, default=100000, help="Generator attempt cap per seed")
    parser.add_argument("--probe-seconds", type=float, default=15.0,
                        help="Short research certification budget before the default run (0 disables)")
    parser.add_argument("--shortlist", type=int, default=20, help="Top-K by suitability to certify (0 = all)")
    parser.add_argument("--target-new", type=int, default=10, help="Stop once this many new certified are selected")
    parser.add_argument("--runtime-budget", type=float, default=3600.0, help="Global wall-clock budget (s)")
    parser.add_argument("--run-dir", type=Path, help="Run folder (default data/research/phase9/runs/<run-id>)")
    parser.add_argument("--archive", type=Path, default=Path("data/research/phase9_candidates.json"))
    parser.add_argument("--production", type=Path, default=Path("data/production/puzzles.json"),
                        help="Read-only: used for duplicate checks")
    parser.add_argument("--resume", action="store_true", help="Reuse generation checkpoints of --run-dir")
    parser.add_argument("--retry-timeouts", action="store_true",
                        help="Re-certify archived probe timeouts with the default budget")
    parser.add_argument("--include-high", action="store_true",
                        help="Also certify Deep >= 36 candidates (research; normally out of conclusive scope)")
    parser.add_argument("--bands", help="Only certify these Deep required ratings, e.g. 35 or 32,35 "
                        "(prioritization only; default: all bands in conclusive scope)")
    parser.add_argument("--min-per-band", type=int, default=0,
                        help="Reserve the best N shortlist slots per Deep band (ahead of the score order)")
    parser.add_argument("--reuse-archive", action="store_true",
                        help="Re-evaluate rated, non-final archive candidates (e.g. NOT_SHORTLISTED) without regenerating")
    parser.add_argument("--no-archive-attempt-rejections", dest="archive_attempt_rejections",
                        action="store_false", help="Do not archive generator-rejected attempts individually")
    args = parser.parse_args(argv)
    try:
        options = BatchOptions(seeds=_seeds(args.seeds), archive=args.archive, run_dir=args.run_dir,
            production=args.production, per_seed_count=args.per_seed_count, difficulty=args.difficulty,
            min_clues=args.min_clues, max_clues=args.max_clues, minimal=args.minimal,
            generation_seconds=args.generation_seconds, max_attempts=args.max_attempts,
            probe_seconds=args.probe_seconds, shortlist=args.shortlist, target_new=args.target_new,
            runtime_budget=args.runtime_budget, resume=args.resume, retry_timeouts=args.retry_timeouts,
            include_high=args.include_high, archive_attempt_rejections=args.archive_attempt_rejections,
            bands=tuple(float(b) for b in args.bands.split(",") if b.strip()) if args.bands else None,
            min_per_band=args.min_per_band, reuse_archive=args.reuse_archive,
            command=["python", "-m", "generator", "production-batch", *(argv if argv is not None else sys.argv[2:])])
        report = run(options)
        print(f"Run {report['runId']}: selected {len(report['selected'])} production candidates | "
              f"report {Path(report['runDir']) / 'batch_report.json'} | archive {report['archive']}")
        return 0 if report.get("complete", bool(report["selected"])) else 1
    except (ValueError, TypeError, OSError) as exc:
        print(f"Production batch failed: {exc}", file=sys.stderr)
        return 2


def report_main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m generator production-report",
        description="Recompute a production-batch report from its checkpoints and the archive into a NEW file "
                    "(the original batch_report.json is never modified).")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, help="Default: the archive named in the original report")
    parser.add_argument("--output", type=Path, help="Default: <run-dir>/batch_report.recomputed.json")
    args = parser.parse_args(argv)
    try:
        report, output = recompute_report(args.run_dir, args.archive, args.output)
        total = report["total"]
        print(f"Recomputed report: {output} | generated {total['generated']} unique {total['unique']} "
              f"rated {total['rated']} shortlisted {total['shortlisted']} certified {total['certified']} "
              f"inconclusive {total['inconclusive']} (timeouts {total['timeouts']}) selected {total['selected']}")
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"Report recomputation failed: {exc}", file=sys.stderr)
        return 2


def _candidates_from_run(run_dir):
    report = read_json(Path(run_dir) / "batch_report.json")
    if report.get("kind") == "standard-batch-report":
        return [dict(item, selected=True) for item in report["selected"]], None
    if report.get("kind") != "phase9-batch-report":
        raise ValueError(f"{run_dir}: not a Phase 9 batch report")
    entries = []
    for item in report.get("selected", []):
        entries.append({"id": item["id"], "puzzle": item["puzzle"], "solution": item["solution"],
                        "selected": True, "certification": {"status": item["status"], "productionEligible": True,
                        "elapsed": item["elapsed"], "minimumRequiredRating": item["minimumRequiredRating"]}})
    return entries, report.get("archive")


def merge_main(argv=None, *, merge=merge_production):
    parser = argparse.ArgumentParser(prog="python -m generator production-merge",
        description="Append freshly re-certified (default config) candidates to the production DB, "
                    "keeping existing records verbatim, with verified backup and post-validation.")
    parser.add_argument("--production", type=Path, default=Path("data/production/puzzles.json"))
    parser.add_argument("--archive", type=Path, action="append", default=[],
                        help="Phase 9 archive(s) to take certified candidates from (repeatable)")
    parser.add_argument("--from-run", type=Path, action="append", default=[],
                        help="Run folder(s) whose batch_report.json lists selected candidates")
    parser.add_argument("--ids", nargs="+", help="Only these IDs, in this order")
    limit = parser.add_mutually_exclusive_group()
    limit.add_argument("--target-total", type=int, help="Stop when the DB holds this many puzzles")
    limit.add_argument("--max-new", type=int, help="Add at most this many new puzzles")
    parser.add_argument("--backup-dir", type=Path, default=Path("data/research/phase9/backups"))
    parser.add_argument("--report", type=Path, help="Merge report JSON (default data/research/phase9/merges/)")
    parser.add_argument("--dry-run", action="store_true", help="Certify and dedupe, but do not write anything")
    args = parser.parse_args(argv)
    try:
        archives = list(args.archive)
        if not archives and not args.from_run:
            archives = [Path("data/research/phase9_candidates.json")]
        archives = list({path.resolve(): path for path in reversed(archives)}.values())[::-1]
        production = args.production.resolve()
        for path in (*archives, args.backup_dir, *(p for p in (args.report,) if p is not None)):
            if path.resolve() == production:
                raise ValueError("Archive, backup and report paths must differ from the production file")
        entries, seen = [], set()
        for run_dir in args.from_run:
            run_entries, archive_path = _candidates_from_run(run_dir)
            if (archive_path and Path(archive_path).exists()
                    and Path(archive_path).resolve() not in {p.resolve() for p in archives}):
                archives.append(Path(archive_path))
            for entry in run_entries:
                if entry["id"] not in seen:
                    seen.add(entry["id"])
                    entries.append(entry)
        with ExitStack() as locks:
            # Same lock as production-batch: no concurrent archive bookkeeping.
            for path in archives:
                locks.enter_context(archive_lock(path, "production-merge"))
            return _merge_locked(args, archives, entries, seen, merge)
    except ArchiveLockedError as exc:
        print(f"Production merge refused: {exc}", file=sys.stderr)
        return 2
    except MergeError as exc:
        print(f"Production merge failed{' (backup restored)' if exc.restored else ''}: {exc}", file=sys.stderr)
        return 2
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"Production merge failed: {exc}", file=sys.stderr)
        return 2


ARCHIVE_UPDATE_FAILED = 3


def _merge_locked(args, archives, entries, seen, merge):
    loaded = [Archive.load(path) for path in archives]
    for archive in loaded:
        if not archive.path.exists():
            raise ValueError(f"Archive not found: {archive.path}")
        for entry in archive.candidates:
            if entry["id"] not in seen:
                seen.add(entry["id"])
                entries.append(entry)
    if args.ids:
        by_id = {entry["id"]: entry for entry in entries}
        missing = [identifier for identifier in args.ids if identifier not in by_id]
        if missing:
            raise ValueError(f"IDs not found in archive/run reports: {', '.join(missing)}")
        ordered = [by_id[identifier] for identifier in args.ids]
    else:
        ordered = merge_order(entries)
    max_new = args.max_new
    if args.target_total is not None:
        existing = read_json(args.production)["puzzles"]
        max_new = max(0, args.target_total - len(existing))
    if max_new is not None and max_new < 1:
        print("Nothing to do: the production DB already has the requested size.")
        return 1
    print(f"Merge: {len(ordered)} candidate(s) in order, max new {max_new}; validating production first...",
          file=sys.stderr, flush=True)
    outcome = merge(args.production, ordered, backup_dir=args.backup_dir, max_new=max_new,
                    dry_run=args.dry_run, log=lambda m: print(m, file=sys.stderr, flush=True))
    stamp = utc_now()
    report = {"kind": "phase9-merge-report", "finishedAt": stamp, "production": str(args.production),
              "dryRun": args.dry_run, "archives": [str(p) for p in archives],
              "runs": [str(p) for p in args.from_run], **outcome.to_dict(),
              "archiveUpdate": "pending" if outcome.written else "not-needed"}
    report_path = args.report or Path("data/research/phase9/merges") / (
        "merge-" + stamp.replace("-", "").replace(":", "") + (".dry-run" if args.dry_run else "") + ".json")
    # The production write is final and validated at this point: record it FIRST.
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Merged {len(outcome.merged)} new | skipped {len(outcome.skipped)} | total {outcome.total} | "
          f"written {outcome.written} | backup {outcome.backup} | report {report_path}")
    if outcome.written:
        merged_ids = {item["id"] for item in outcome.merged}
        try:
            for archive in loaded:
                changed = False
                for entry in archive.candidates:
                    if entry["id"] in merged_ids:
                        entry["production"] = {"merged": True, "mergedAt": stamp}
                        changed = True
                if changed:
                    archive.save()
            report["archiveUpdate"] = "done"
        except (ValueError, OSError) as exc:
            report["archiveUpdate"] = f"failed: {exc}"
            atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(f"Production DB was merged and validated, but marking the archive failed: {exc}. "
                  f"Merged IDs are listed in {report_path}; production-merge skips them as DUPLICATE, "
                  "so the archive flags can be fixed later without risk.", file=sys.stderr)
            return ARCHIVE_UPDATE_FAILED
        atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0 if outcome.merged else 1
