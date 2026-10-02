"""Command line for fresh, conservative production certification."""
import argparse
from dataclasses import fields
import json
from pathlib import Path
import sys

from . import CertificationConfig
from .io import export_production, load_candidates, read_json


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m generator certify",
        description="Fresh logical certification; inconclusive candidates never enter production")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input", type=Path, help="Schema-v1 candidate database or research bundle")
    inputs.add_argument("--puzzle", help="Direct 81-digit puzzle string")
    parser.add_argument("--solution", help="Optional known solution, used only in mathematical validation")
    parser.add_argument("--puzzle-id", help="Select this ID from --input, or assign it to --puzzle")
    parser.add_argument("--output", type=Path, default=Path("data/production/puzzles.json"))
    parser.add_argument("--research-output", type=Path, default=Path("data/candidates.json"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports/certification"))
    parser.add_argument("--config", type=Path, help="CertificationConfig JSON")
    parser.add_argument("--fresh", action="store_true", help="Explicit fresh mode (always enabled before production export)")
    parser.add_argument("--time-budget", type=float)
    parser.add_argument("--node-budget", type=int)
    parser.add_argument("--state-budget", type=int)
    parser.add_argument("--max-path-depth", type=int)
    parser.add_argument("--max-alternative-steps-per-state", type=int)
    parser.add_argument("--max-chain-length", type=int)
    parser.add_argument("--max-als-size", type=int)
    parser.add_argument("--require-minimal", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args(argv)

    def progress(index, total, entry):
        result = entry.result
        if result is None:
            print(f"[{index}/{total}] REJECTED: {entry.reason.value}: {entry.detail}", flush=True)
            return
        print(f"[{index}/{total}] Puzzle: {result.puzzle_id}\n"
              f"Unique: {result.unique} | Minimal: {result.minimal} | Proof validation: {result.proof_valid}\n"
              f"Alternative path search: {result.search_status.value}\n"
              f"Minimum required rating: {result.minimum_required_rating}\n"
              f"Certified bottlenecks: {result.certified_bottlenecks}\n"
              f"Certification: {result.status.value}", flush=True)

    try:
        outputs = [args.output.resolve(), args.research_output.resolve()]
        sources = [path.resolve() for path in (args.input, args.config) if path is not None]
        if len(set(outputs)) != len(outputs) or any(path in sources for path in outputs):
            raise ValueError("Input/config, production output and research output must use separate paths")
        if args.reports_dir.resolve() in (*sources, *outputs):
            raise ValueError("Reports directory must be separate from input/output files")
        if args.input and args.solution is not None:
            raise ValueError("--solution is supported only with --puzzle")
        values = read_json(args.config) if args.config else {}
        if not isinstance(values, dict):
            raise ValueError("Certification config must be a JSON object")
        for field in fields(CertificationConfig):
            value = getattr(args, field.name, None)
            if value is not None:
                values[field.name] = value
        config = CertificationConfig.from_dict(values)
        if args.input:
            records = load_candidates(args.input)
            if args.puzzle_id:
                records = [record for record in records if isinstance(record, dict) and record.get("id") == args.puzzle_id]
                if not records:
                    raise ValueError(f"Puzzle ID not found: {args.puzzle_id}")
        else:
            records = [{"puzzle": args.puzzle}]
            if args.solution is not None:
                records[0]["solution"] = args.solution
            if args.puzzle_id is not None:
                records[0]["id"] = args.puzzle_id
        database, research = export_production(records, args.output, config=config,
            research_path=args.research_output, reports_dir=args.reports_dir, progress=progress)
        print("Certification summary: " + json.dumps(research["stats"], sort_keys=True))
        print(f"Production: {args.output} | Research: {args.research_output} | Reports: {args.reports_dir}")
        return 0 if database["puzzles"] else 1
    except (ValueError, TypeError, OSError) as exc:
        print(f"Certification failed: {exc}", file=sys.stderr)
        return 2
