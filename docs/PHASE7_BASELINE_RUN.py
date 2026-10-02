"""Capture a fresh Phase 7 baseline without modifying historical evidence."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PREFIX = DOCS / "PHASE7_BASELINE"
SUMMARY = Path(str(PREFIX) + "_SUMMARY.json")
if SUMMARY.exists():
    raise SystemExit("Refusing to overwrite existing baseline")
files = {}
for folder in ("generator", "web", "data"):
    for path in sorted((ROOT / folder).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and "artifacts" not in path.parts:
            files[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
Path(str(PREFIX) + "_SOURCE_SHA256.json").write_text(json.dumps({"algorithm": "sha256", "aggregate": fingerprint, "files": files}, indent=2), encoding="utf-8")
qa = Path(os.environ["TEMP"]) / "extreme-sudoku-qa"
env = os.environ.copy()
env["PYTHONPATH"] = str(qa / "packages")
env["PLAYWRIGHT_BROWSERS_PATH"] = str(qa / "browsers")
node = qa / "packages/playwright/driver/node.exe"
summary = {"started_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version, "python_executable": sys.executable, "platform": platform.platform(), "source_sha256": fingerprint, "git_directory_present": (ROOT / ".git").exists(), "environment_overrides": {key: env[key] for key in ("PYTHONPATH", "PLAYWRIGHT_BROWSERS_PATH")}, "runs": []}
commands = [
    ("PYTHON", [sys.executable, "-m", "unittest", "discover", "-s", "generator/tests", "-v"]),
    ("FRONTEND", [str(node), "--test", "web/tests/game.test.js"]),
    ("BROWSER", [sys.executable, "-c", "import runpy; from pathlib import Path; m = runpy.run_path('web/tests/browser_regression.py'); m['main'].__globals__['ARTIFACTS'] = Path('docs/PHASE7_BASELINE_BROWSER'); m['main']()"]),
]
for label, command in commands:
    log = Path(str(PREFIX) + "_" + label + ".log")
    if log.exists():
        raise SystemExit(f"Refusing to overwrite {log}")
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    record = {"label": label, "command": command, "cwd": str(ROOT), "exit_code": result.returncode, "wall_seconds": time.perf_counter() - started, "log": log.relative_to(ROOT).as_posix()}
    summary["runs"].append(record)
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(record), flush=True)
changed = [name for name, digest in files.items() if not (ROOT / name).exists() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
summary["baseline_files_changed_during_run"] = changed
summary["finished_utc"] = datetime.now(timezone.utc).isoformat()
SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
raise SystemExit(1 if changed or any(run["exit_code"] for run in summary["runs"]) else 0)
