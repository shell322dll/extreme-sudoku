# Phase 7.1 — Re-certification of the 9 Phase 6 candidates

Date: 2026-10-02. Launch/analysis run only. No changes to `generator/`, `web/`, `data/`;
**no production export** (that follows code review).

- Input: `docs/PHASE7_EXPERIMENT_INPUT.json` (9 unique candidates, `puzzle_id` and `solution` passed as given).
- Call: fresh `generator.certification.certify_puzzle(puzzle, solution, puzzle_id=…, config=CertificationConfig())`
  (default config, 60 s budget, `use_stuck_state_lemma=True`), one fresh subprocess per candidate, strictly sequential.
- Analysis variant: same call with `use_stuck_state_lemma=False` (isolates the pure search optimizations; not a decision input).
- Algorithm fingerprint: see `PHASE7_1_RECERT_SUMMARY.json` (`algorithm_fingerprint`).
- Raw data: `docs/PHASE7_1_RECERT_SUMMARY.json`; log `docs/PHASE7_1_RECERT.log`.
- Note: a code-review agent ran the test suite once concurrently; timings may be slightly affected.

## 1. Result table (default config, SSL on)

| ID | Clues | Prelim. label | Phase 7 status (states) | **Phase 7.1 status** | Elapsed s | States | TT hit rate | Upper | Min. required | Threshold result |
|---|---:|---|---|---|---:|---:|---:|---:|---:|---|
| 8e2b144cecb50551d96b | 22 | Extreme | TIMEOUT (945) | **CERTIFIED_EXTREME** | 2.0 | 0 | – | 35 | **35 (Grouped AIC tier EXTREME)** | T=32 PROVEN_UNSOLVABLE, kind SSL, 0.32 s |
| f197179f12c6533697b1 | 23 | Extreme | TIMEOUT (522) | CERTIFICATION_TIMEOUT | 60.0 | 1018 | 74.3 % | 35 | null | T=32 INCONCLUSIVE; SSL fallback (G4) |
| bcf460fc20aeeee740c2 | 22 | Ultra Extreme | TIMEOUT (171) | CERTIFICATION_TIMEOUT | 60.0 | 402 | 51.4 % | 39 | null | T=36 INCONCLUSIVE; SSL out of scope |
| ca88d658a18eafb27c24 | 22 | Ultra Extreme | TIMEOUT (105) | CERTIFICATION_TIMEOUT | 60.0 | 144 | 22.7 % | 55 | null | T=50 INCONCLUSIVE; SSL out of scope |
| 03122df59ac468dbf09d | 24 | Ultra Extreme | TIMEOUT (80) | CERTIFICATION_TIMEOUT | 60.0 | 102 | 18.6 % | 55 | null | T=50 INCONCLUSIVE; SSL out of scope |
| 55684dd4bac9cb6a200f | 24 | Ultra Extreme | TIMEOUT (81) | CERTIFICATION_TIMEOUT | 60.0 | 85 | 20.9 % | 55 | null | T=50 INCONCLUSIVE; SSL out of scope |
| 310fab8b8581c087bc8a | 25 | Ultra Extreme | TIMEOUT (91) | CERTIFICATION_TIMEOUT | 60.0 | 90 | 24.4 % | 55 | null | T=50 INCONCLUSIVE; SSL out of scope |
| f23734d386d6cc1e2328 | 25 | Ultra Extreme | TIMEOUT (118) | CERTIFICATION_TIMEOUT | 60.0 | 106 | 46.0 % | 55 | null | T=50 INCONCLUSIVE; SSL out of scope |
| b4d935b1bf18e438b282 | 26 | Ultra Extreme | TIMEOUT (92) | CERTIFICATION_TIMEOUT | 60.0 | 89 | 20.8 % | 50 | null | T=42 INCONCLUSIVE; SSL out of scope |

Totals: **1 CERTIFIED_EXTREME, 8 CERTIFICATION_TIMEOUT** (failure reason `SEARCH_TIMEOUT` for all 8).
Previous Phase 7: 9 × CERTIFICATION_TIMEOUT. All 9: unique, human-solved, proof valid, reproducible
(minimal = true for 8e2b, f197, bcf4, ca88, 0312; false for 5568, 310f, f237, b4d9; `require_minimal` is off).
Each descent stopped at its first threshold (the highest rating below the human upper bound); no cheaper witness was found anywhere.
`negative_proof_possible` = false for every inconclusive threshold (operational limit reasons appeared), true for 8e2b T=32.

TT hit rate = `transposition_hits / transposition_lookups` from the new telemetry (child lookups after
pre-apply dedup; not comparable 1:1 with the Phase 7 numbers, which counted raw children).

### Certified candidate: puzzle-8e2b144cecb50551d96b

- Status CERTIFIED_EXTREME, `production_eligible` = true, minimum_required_rating **35.0** (tier EXTREME), certified path 84 steps.
- Negative evidence below the minimum: T=32 `PROVEN_UNSOLVABLE_WITHIN_MODEL`, `negative_proof_kind` =
  `STUCK_STATE_SUPERSET_LEMMA` (SSL-v1), closure length 28, closure candidates 125 (= the G from the baseline lattice study), all guards PASS.
- Certified bottlenecks **3**, late-game bottlenecks 0, advanced steps **17**, longest chain **13**, distributed bins **2**, max trivial gap 35.
- Not Ultra: minimum 35 < ultra_threshold 36.
- Analysis with SSL off: CERTIFICATION_TIMEOUT, 1684 states, TT hit 76.9 % — the pure search still cannot exhaust
  the ≥2^20-state lattice (see baseline profile); the certificate comes from the lemma alone.

### Why the others stay inconclusive

| ID | T | SSL outcome | Failed guards | Limit reasons in the search (all ⇒ negative proof impossible) |
|---|---:|---|---|---|
| f197 | 32 | FALLBACK (0.23 s) | **G4**: enumeration at the closure G is empty but not complete (`AIC/Nice Loop: CHAIN_LENGTH_LIMIT, CHAIN_NODE_LIMIT`) | AIC/Nice Loop chain length+node, TIME |
| bcf4 | 36 | FALLBACK | G5.scope (T must be < 36), G5.proven (ALS-XZ not covered) | ALS-XZ size, Grouped AIC length+node, TIME |
| ca88 | 50 | FALLBACK (2.4 s) | G5.scope, G5.proven | ALS (size/node/chain length), Forcing depth/node/start, Grouped AIC length/node, TIME |
| 0312 | 50 | FALLBACK (1.5 s) | G5.scope, G5.proven | same + AIC/Nice Loop length/node |
| 5568 | 50 | FALLBACK (1.4 s) | G5.scope, G5.proven | same family set |
| 310f | 50 | FALLBACK (3.8 s) | G5.scope, G5.proven | same family set |
| f237 | 50 | FALLBACK (2.8 s) | G5.scope, G5.proven | ALS, Forcing, Grouped AIC, TIME |
| b4d9 | 42 | FALLBACK (1.9 s) | G5.scope, G5.proven | ALS, Grouped AIC, AIC/Nice Loop, TIME |

For T ≥ 36 every enumeration hits ALS/Forcing/Grouped-AIC work limits, so `PROVEN_UNSOLVABLE_WITHIN_MODEL`
is unreachable by construction (as already found in the baseline profile); more time can only find a cheaper witness, never certify the minimum.
Human replay costs 5–13 s of the 60 s budget for the T=50 candidates.

## 2. SSL on vs SSL off (analysis only)

| ID | Status SSL on | States on | Status SSL off | States off | TT hit off | Phase 7 states |
|---|---|---:|---|---:|---:|---:|
| 8e2b | CERTIFIED_EXTREME | 0 | TIMEOUT | 1684 | 76.9 % | 945 |
| f197 | TIMEOUT | 1018 | TIMEOUT | 848 | 73.3 % | 522 |
| bcf4 | TIMEOUT | 402 | TIMEOUT | 391 | 50.8 % | 171 |
| ca88 | TIMEOUT | 144 | TIMEOUT | 118 | 18.7 % | 105 |
| 0312 | TIMEOUT | 102 | TIMEOUT | 91 | 16.2 % | 80 |
| 5568 | TIMEOUT | 85 | TIMEOUT | 100 | 26.2 % | 81 |
| 310f | TIMEOUT | 90 | TIMEOUT | 102 | 27.5 % | 91 |
| f237 | TIMEOUT | 106 | TIMEOUT | 116 | 46.3 % | 118 |
| b4d9 | TIMEOUT | 89 | TIMEOUT | 95 | 22.4 % | 92 |

Reading: the pure search optimizations raise throughput ~1.6–2.3× for the T ≤ 36 searches (8e2b, f197, bcf4)
but change nothing for the T = 42/50 searches (±15 %, within noise; ALS enumeration dominates and was not sped up).
They change no status. The only status change comes from SSL. The SSL-on/off state differences
for the same candidate are noise (concurrent test suite, SSL closure time 0.2–3.8 s spent before the fallback search).

## 3. Scaling probe (ANALYSIS ONLY — not a decision change)

`puzzle-f197179f12c6533697b1`, default config except `time_budget = 300 s`, SSL on:

| Budget | Status | States explored | Unique states | TT hit | Mean branching | States/s | RSS peak |
|---:|---|---:|---:|---:|---:|---:|---:|
| 60 s | CERTIFICATION_TIMEOUT | 1018 | – | 74.3 % | 5.20 | 17.3 | 48 MB |
| 300 s | CERTIFICATION_TIMEOUT | 5581 | 5910 | 83.3 % | 6.33 | 18.7 | 158 MB |

Linear growth, no saturation; the chain limit reasons appear at expansion 2–6, so even a finished search could not
prove a negative result at T=32. The enumeration LRU (120 000 entries) filled and evicted 14 016 entries; its hit rate was
0.3 % (states are almost all distinct), the validation cache had 0 hits. At 300 s the run is still within the node budget (10 000).
