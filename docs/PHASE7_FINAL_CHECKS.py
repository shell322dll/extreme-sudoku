"""Reproduce final Phase 7 regressions without installing dependencies."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def main():
    env = os.environ.copy()
    qa = Path(env["TEMP"]) / "extreme-sudoku-qa"
    env["PYTHONPATH"] = str(qa / "packages")
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(qa / "browsers")
    node = qa / "packages" / "playwright" / "driver" / "node.exe"
    if not node.is_file() or not (qa / "browsers").is_dir():
        raise RuntimeError("Existing baseline QA tools are missing")
    inventory = {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest()
                 for folder in ("generator", "web", "data")
                 for p in (ROOT / folder).rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    summary = {"started_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
               "python_executable": sys.executable, "platform": platform.platform(),
               "source_sha256": sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest(),
               "runs": []}
    runs = [("PYTHON", [sys.executable, "-m", "unittest", "discover", "-s", "generator/tests", "-v"]),
            ("FRONTEND", [str(node), "--test", "web/tests/game.test.js", "web/tests/certification.test.js"]),
            ("BROWSER", [sys.executable, "-c", "import runpy;from pathlib import Path;"
               "m=runpy.run_path('web/tests/browser_regression.py');"
               "m['main'].__globals__['ARTIFACTS']=Path('docs/PHASE7_FINAL_BROWSER');m['main']()"])]
    for label, command in runs:
        print("Starting " + label, flush=True)
        started = perf_counter()
        log = DOCS / ("PHASE7_FINAL_" + label + ".log")
        with log.open("w", encoding="utf-8") as output:
            completed = subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
        row = {"label": label, "command": command, "cwd": str(ROOT), "exit_code": completed.returncode,
               "wall_seconds": perf_counter() - started, "log": str(log.relative_to(ROOT))}
        text = log.read_text(encoding="utf-8")
        if label == "PYTHON":
            match = re.search(r"Ran (\d+) tests in ([\d.]+)s", text)
            if match:
                row.update(tests=int(match[1]), unittest_seconds=float(match[2]))
        elif label == "FRONTEND":
            match = re.search(r"# tests (\d+)", text)
            if match:
                row["tests"] = int(match[1])
        else:
            data = json.loads((DOCS / "PHASE7_FINAL_BROWSER/browser-results.json").read_text(encoding="utf-8"))
            row.update(groups=len(data["checks"]), responsive_checks=len(data["layouts"]), browsers=data["browsers"])
        summary["runs"].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    summary["source_files_changed_during_run"] = [name for name, digest in inventory.items()
        if not (ROOT / name).is_file() or sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    summary["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (DOCS / "PHASE7_FINAL_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if any(r["exit_code"] for r in summary["runs"]):
        raise SystemExit(1)
    if summary["source_files_changed_during_run"]:
        raise SystemExit("Source changed during final tests")


if __name__ == "__main__":
    main()
