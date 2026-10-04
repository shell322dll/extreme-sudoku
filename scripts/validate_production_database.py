"""Validate data/production/puzzles.json with the generator's own strict validator.

    python scripts/validate_production_database.py [path]

Re-certifies every record (fresh) and compares all metadata. It does not generate or
certify anything new and never writes. Exit code 0 = valid (an empty database is valid),
1 = invalid, 2 = unreadable file.
"""
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from generator.certification.io import read_json  # noqa: E402
from generator.production.verification import validate_production_database  # noqa: E402


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 else ROOT / "data" / "production" / "puzzles.json"
    try:
        database = read_json(path)
    except (OSError, ValueError) as error:
        print(f"ERROR: cannot read {path}: {error}", file=sys.stderr)
        return 2
    started = time.time()
    try:
        validate_production_database(database)
    except Exception as error:  # ExportValidationError and any unexpected failure are invalid
        print(f"INVALID production database {path}: {error}", file=sys.stderr)
        return 1
    count = len(database.get("puzzles", []))
    print(f"OK production database {path}: {count} production puzzle(s) re-validated in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
