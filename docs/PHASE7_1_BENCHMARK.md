# Phase 7.1 — Before/after benchmark of `threshold_search`

Date: 2026-10-02. Analysis only; product code was not modified.
Same candidates/thresholds as `PHASE7_1_PROFILE_BASELINE.md`: `puzzle-8e2b144cecb50551d96b` at **T=32** and
`puzzle-ca88d658a18eafb27c24` at **T=50**, `threshold_search(grid, T, CertificationConfig())` called directly, 60 s.

- **Baseline** = pre-7.1 source copy (`scratchpad/phase7_baseline_src`, put first on `sys.path`, verified via `generator.__file__`).
- **New SSL off / SSL on** = current `generator/` with `use_stuck_state_lemma` False / True.
- Each run in a fresh subprocess, strictly sequential. Worker: `scratchpad/p71_bench.py`; raw: `docs/PHASE7_1_BENCHMARK.json`.
- Two modes: **instrumented** (identical light wrappers on both code bases: per-technique timers, enumerate/apply counters)
  and **plain** (no monkeypatching; new-code numbers from `ThresholdResult.telemetry`).
- **Important:** in instrumented mode the wrapper replaces `StepEnumerator.enumerate`, so `audited_enumerator()` refuses SSL
  (fail-closed, as designed). Instrumented "SSL on" rows are therefore just a second SSL-off run; valid SSL-on numbers are the plain rows.
- A code-review agent ran the test suite once concurrently; timings may be slightly affected.

## 1. Headline (plain runs, 60 s)

| Run | Status | States explored | Unique states | ms/state | Throughput vs baseline | RSS peak |
|---|---|---:|---:|---:|---:|---:|
| 8e2b T=32 baseline | INCONCLUSIVE (TIME) | 990 | 1 458 | 60.6 | 1.00× | 29 MB |
| 8e2b T=32 new, SSL off | INCONCLUSIVE (TIME) | 2 203 | 2 675 | 27.2 | **2.23×** | 75 MB |
| 8e2b T=32 new, SSL on | **PROVEN_UNSOLVABLE_WITHIN_MODEL** (SSL, all guards PASS) | 0 | 1 | – | **0.29 s total** | 25 MB |
| ca88 T=50 baseline | INCONCLUSIVE (TIME + limits) | 123 | 934 | 487.8 | 1.00× | 52 MB |
| ca88 T=50 new, SSL off | INCONCLUSIVE (TIME + limits) | 171 | 971 | 350.9 | **1.39×** | 45 MB |
| ca88 T=50 new, SSL on | INCONCLUSIVE (TIME + limits); SSL FALLBACK after 1.9 s (G5.scope, G5.proven) | 170 | 971 | 353.0 | 1.38× | 46 MB |

Instrumented throughput ratios agree: 8e2b 942 → 2 116 states (2.25×), ca88 109 → 171 (1.57×; baseline instrumentation overhead ≈ 5–12 %).
Earlier baseline profile (heavier harness): 958 / 122 states.

## 2. Detailed metrics (instrumented baseline vs new SSL off)

| Metric | 8e2b baseline | 8e2b new | ca88 baseline | ca88 new |
|---|---:|---:|---:|---:|
| States explored | 942 | 2 116 | 109 | 171 |
| Unique states (records) | 1 412 | 2 585 | 911 | 971 |
| ms / expanded state | 63.7 | 28.4 | 550.5 | 350.9 |
| Raw steps / state (after enumerator canonicalisation) | 9.59 | 10.46 | 22.77 | 17.73 |
| Unique effects (= distinct children) / state | 5.35 / 5.36 | 5.69 / 5.69 | 10.10 / 10.27 | 7.84 / 7.84 |
| Duplicate steps removed before apply | 0 (all applied) | 10 079 (45.6 % of raw) | 0 | 1 690 (55.8 %) |
| Child transposition lookups | 9 035 (every applied step) | 12 038 (after dedup) | 2 474 | 1 339 |
| Transposition hits / hit rate | 7 624 / 84.4 % | 9 454 / 78.5 % | 1 564 / 63.2 % | 369 / 27.6 % |
| Steps resolved without a new state ((dup + hits) / raw) | 84.4 % | 88.3 % | 63.2 % | 67.9 % |
| Proof validation seconds | 5.60 | 1.71 | 2.17 | 0.80 |
| Enumerations with a limit reason | 0 / 942 | 1 / 2 116 (final TIME) | 109 / 109 | 171 / 171 |
| Peak frontier | – | 492 | – | 820 |
| RSS peak | 29 MB | 74 MB | 53 MB | 46 MB |

The hit-rate drop is a denominator effect: equal-effect siblings are now removed *before* the transposition
lookup (`select_transitions`), so they no longer count as hits. Effective branching (distinct children per state) is
essentially unchanged — the gain is cost per state, not pruning of the state space.

### Time per family, ms per expanded state

Baseline = instrumented wrapper around the detector entry points; new = product `family_enumeration_seconds`
(plain run), which also includes the shared inference-graph construction now done once per state in `_run`.

| Family | 8e2b baseline | 8e2b new | ca88 baseline | ca88 new |
|---|---:|---:|---:|---:|
| AIC | 31.5 | **15.0** | 27.6 | **12.0** |
| Grouped AIC | – | – | 92.9 | **47.7** |
| Other chains (X-Chain, XY-Chain, Nice Loop) | 11.2 | **5.5** | 11.4 | **5.6** |
| ALS (XZ, XY-Wing, Chain) | – | – | 188.4 | 181.4 (unchanged) |
| Forcing Chain / Nishio | – | – | 176.2 | **93.0** |
| Basic patterns + singles | 5.5 | 5.3 | 5.6 | 5.2 |

ALS is now the dominant cost at T=50 (≈52 % of wall time) and was not accelerated.

### Caches (new code)

| Run | Enumeration cache lookups / hits | Validation cache lookups / hits |
|---|---|---|
| 8e2b SSL off | 52 858 / 0 | 2 674 / 0 |
| 8e2b SSL on | 2 082 / 1 858 (89 %, inside the SSL closure + guard check) | 0 / 0 |
| ca88 SSL off | 4 957 / 0 | 970 / 0 |
| ca88 SSL on | 8 841 / 3 769 (43 %, SSL closure reused by the fallback search) | 970 / 0 |

Within one exhaustive `threshold_search` both caches have zero hits (every expanded state is new); they pay off only
across the SSL closure/check and across descent thresholds. They are the main reason for the higher RSS on 8e2b
(52 858 cached per-technique results for 2 203 states). In the 300 s f197 probe the 120 000-entry LRU filled (RSS 158 MB).

## 3. Conclusion

- Pure search optimizations: **2.2× (T=32, chain-dominated)** and **1.4–1.6× (T=50, ALS-dominated)** more states per 60 s;
  per-family speedups ≈2× for AIC/Grouped AIC/Nice Loop/X/XY chains and Forcing, none for ALS. No status changes:
  the reachable lattice (≥2^20 states for 8e2b at T=32) is still far beyond the budget.
- SSL: turns 8e2b T=32 from a ≥18 h exhaustive problem into a 0.29 s certificate; for T ≥ 36 it is out of scope and costs 1.4–3.8 s before falling back.
- Fail-closed check observed in practice: any monkeypatching of the enumerator disables SSL.
