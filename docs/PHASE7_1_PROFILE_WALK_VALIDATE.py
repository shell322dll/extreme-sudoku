"""Phase 7.1: reproduce/validate random-walk witnesses. Usage: python docs/PHASE7_1_PROFILE_WALK_VALIDATE.py PID T N_WALKS SEED CAP_S
ca88 witness: puzzle-ca88d658a18eafb27c24 50 6 11 900 -> walk i=4 solved, validate_path valid."""
import sys, json, random, time
sys.path.insert(0, r"C:\Develop\Extreme Sudoku")
from collections import Counter
from generator.certification.config import CertificationConfig
from generator.certification.enumeration import StepEnumerator
from generator.certification.proofs import validate_path
from generator.solver.human_solver import apply_step
from generator.sudoku.candidates import SudokuState
P = {p["id"]: p for p in json.load(open(r"C:\Develop\Extreme Sudoku\docs\PHASE7_EXPERIMENT_INPUT.json", encoding="utf-8"))["puzzles"]}
pid, T, n, seed, cap = sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])
grid = [int(c) for c in P[pid]["puzzle"]]
cfg = CertificationConfig(); en = StepEnumerator(cfg); rng = random.Random(seed); t0 = time.perf_counter()
out = {"pid": pid, "T": T, "seed": seed, "walks": []}
for i in range(n):
    if time.perf_counter() - t0 > cap: break
    st, path = SudokuState(grid), []
    while True:
        r = en.enumerate(st, T)
        if not r.steps: break
        s = rng.choice(r.steps); st = apply_step(st, s); path.append(s)
    w = {"i": i, "len": len(path), "cands": sum(m.bit_count() for m in st.candidates), "solved": all(st.grid)}
    if w["solved"]:
        w["valid"] = validate_path(grid, path, config=cfg).valid
        w["max_rating"] = max(x.rating for x in path)
        w["techniques"] = dict(Counter(x.technique for x in path))
        w["n_at_max"] = sum(x.rating == w["max_rating"] for x in path)
    out["walks"].append(w)
out["elapsed"] = round(time.perf_counter() - t0, 1)
print(json.dumps(out))
