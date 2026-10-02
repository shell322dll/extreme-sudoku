# Phase 7.1 — Profiling baseline of the certification search

Date: 2026-10-02. Diagnostic only: product code under `generator/`, `web/`, `data/`
was **not** modified. All instrumentation is in-process monkeypatching
(`docs/PHASE7_1_PROFILE_RUN.py`); each job runs in a fresh subprocess.
Raw data: `docs/PHASE7_1_PROFILE_BASELINE.json` (aggregate),
`docs/PHASE7_1_PROFILE_RAW/` (per-job files incl. full time series).
Default `CertificationConfig` (60 s, node/state budget 10 000, chain length 19,
chain work 100 000, ALS size 4 / length 5 / work 30 000, forcing depth 12 /
nodes 2000 / starts 160). Harness overhead measured: 0.06 s / 60 s run.

Reproduce: `python docs/PHASE7_1_PROFILE_RUN.py --all --stage profile,lattice,probe --cap 240`
then `--stage walkprobe --cap 480`.

## 1. Search profile (`threshold_search` called directly)

| Metric | 8e2b T=32, 60 s | 8e2b T=32, 300 s, budget 1e6 | ca88 T=50, 60 s | ca88 T=50, 300 s, budget 1e6 |
|---|---:|---:|---:|---:|
| Status | INCONCLUSIVE (TIME) | INCONCLUSIVE (TIME) | INCONCLUSIVE (TIME + limits) | INCONCLUSIVE (TIME + limits) |
| States explored (expanded) | 958 | 4 689 | 122 | 659 |
| Unique states (= generated) | 1 430 | 5 134 | 933 | 1 459 |
| Children (validate+apply calls) | 9 169 | 56 103 | 2 622 | 9 416 |
| Child transposition hits | 7 740 (84.4 %) | 50 970 (90.9 %) | 1 690 (64.4 %) | 7 958 (84.5 %) |
| Stale pops / re-expansions / depth-improved re-push | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Frontier size (start → end, peak) | 486 → 474 (486) | 486 → 449 (492) | 820 → 805 (820) | 820 → 803 (820) |
| ms per expanded state | 62.6 | 64.0 | 492 | 455 |
| Enumerations with any limit reason | 1 / 958 (TIME) | 1 / 4 689 (TIME) | **122 / 122** | **659 / 659** |
| RSS peak | 36 MB | 58 MB | 54 MB | 54 MB |

Cache hit rate = child-level hits / (hits + misses) = hits / children. Pop-level
stale entries never occurred, so `best_depth` depth dominance is never exercised:
root candidate counts are 248 (8e2b) and 236 (ca88) < `max_path_depth`=256, and
every step removes ≥1 candidate, so `PATH_DEPTH_LIMIT` is unreachable here.

Growth: unique states grow **linearly with expansions** (~1.09 new state per
expansion for 8e2b; ~1.2 for ca88), the frontier is flat (≈470 / ≈805) and
`min_frontier_candidates` oscillates 126–139 (8e2b) / 132–138 (ca88): best-first
by candidate count dives to the bottom of the lattice and then enumerates
interleavings of the same few eliminations near the dead end. No sign of
saturation after 300 s.

### Time breakdown (share of wall time; nested timers overlap)

| Component | 8e2b 60 s | 8e2b 300 s | ca88 60 s | ca88 300 s |
|---|---:|---:|---:|---:|
| `StepEnumerator.enumerate` total | 77.0 % | 72.2 % | 92.4 % | 94.4 % |
| — AIC | 49.6 % | 46.0 % | 5.2 % | 5.9 % |
| — Nice Loop | 12.0 % | 11.3 % | 1.3 % | 1.5 % |
| — X-Chain / XY-Chain | 4.0 / 1.5 % | 3.9 / 1.4 % | 0.7 / 0.2 % | 0.7 / 0.2 % |
| — Grouped AIC | – | – | 17.3 % | 18.2 % |
| — ALS-XZ / ALS-XY-Wing / ALS Chain | – | – | 7.5 / 10.6 / 18.2 % | 8.9 / 13.0 / 21.0 % |
| — Forcing Chain | – | – | 29.7 % | 23.3 % |
| — basic (LC…Jellyfish) / singles | 8.0 / 0.5 % | 7.8 / 0.5 % | 1.0 / 0.1 % | 1.1 / 0.1 % |
| — `canonical_steps` inside detectors (json.dumps(asdict) of every raw proof) | 11.2 % | 10.1 % | 14.0 % | 6.3 % |
| `canonical_steps` outer + search | 2.3 % | 2.3 % | 1.1 % | 0.8 % |
| `validate_step` | 9.4 % | 11.3 % | 3.4 % | 2.5 % |
| `apply_step` | 12.0 % | 14.8 % | 3.6 % | 2.6 % |
| `SudokuState.validate` (nested in copy/place/eliminate/is_solved/proofs) | 20.6 % (66 498 calls) | 25.2 % | 6.0 % | 4.4 % |
| `signature` / heap ops | 0.01 % / 0.005 % | ≈0 | ≈0 | ≈0 |

### Branching and equivalent steps

| Metric | 8e2b 60 s | 8e2b 300 s | ca88 60 s | ca88 300 s |
|---|---:|---:|---:|---:|
| Steps per state after `canonical_steps` avg / max | 9.58 / 62 | 11.97 / 62 | 21.5 / 154 | 14.3 / 154 |
| Distinct effects ignoring rating avg / max | 5.34 / 53 | 6.29 / 53 | 9.43 / 110 | 5.44 / 110 |
| Distinct child states per expansion avg | 5.34 | 6.29 | 9.58 | 5.45 |
| Children whose state equals a sibling's | 4 062 (44 %) | 26 600 (47 %) | 1 472 (56 %) | 5 833 (62 %) |

The outer `canonical_steps` never merges anything (raw = after), because the key
includes the rating: equal effects found by different techniques survive as
separate children, are each validated and applied, and then collapse in the
transposition table. Typical multi-technique effects: `Hidden Single+Naked Single`
(9 220 in 300 s), `Full House+Hidden Single+Naked Single`, `AIC+Locked Candidates+
Nice Loop+Turbot Fish+X-Chain+X-Wing` (one elimination, 6 representations),
`Forcing Chain+Hidden Single+Naked Single`, `AIC+ALS Chain+ALS-XY-Wing+ALS-XZ+
Forcing Chain`, up to 12 techniques for one effect (ca88).

Proof-representation redundancy inside detectors (raw → after inner canonical):
AIC 35 823 → 3 011 (11.9×), Nice Loop 4 284 → 444 (9.6×), X-Chain 2×
(8e2b, 60 s); Forcing Chain 44 862 → 934 (48×), Grouped AIC 3 333 → 52 (64×),
AIC 4 916 → 224 (22×), ALS-XY-Wing 2 394 → 306, ALS Chain 2 752 → 234,
X-Chain 764 → 49 (ca88, 60 s). Sampled states: at the 8e2b root 18 of 39 distinct
effects are strict subsets of another effect (ca88 root: 33 of 110); deeper states
had 0 subset-dominated effects.

### Limit reasons (ca88, T=50, every single enumeration)

`ALS-XZ/ALS-XY-Wing/ALS Chain:ALS_SIZE_LIMIT` 659/659, `Grouped AIC:CHAIN_NODE_LIMIT`
659/659, `Grouped AIC:CHAIN_LENGTH_LIMIT` 658, `Forcing Chain:FORCING_DEPTH_OR_NODE_LIMIT`
659, `ALS Chain:ALS_CHAIN_LENGTH_LIMIT` 658, `ALS Chain:ALS_NODE_LIMIT` 656,
`FORCING_START_LIMIT` 10 (only states with >160 candidates).
Consequence: at T=50 `PROVEN_UNSOLVABLE_WITHIN_MODEL` is **unreachable by
construction** — any completed exploration would still return INCONCLUSIVE.

## 2. Lattice evidence

| | 8e2b T=32 | ca88 T=50 |
|---|---|---|
| Root candidates | 248 | 236 |
| Greedy fixpoint G (apply all validated steps, repeat) | 7 rounds, 32 steps (17 singles, 2 LC, 13 AIC), **not solved**, 125 candidates left | 7 rounds, 32 steps (15 singles, 7 LC, 4 AIC, 2 ALS, 4 Forcing), not solved, 132 left |
| k = candidates eliminated root → G | 123 | 104 |
| Enumeration at G complete? | **yes (no limits)** | no (8 limit reasons) |
| Root distinct effects / pairwise-disjoint / mutually persistent | 39 / 21 / 20 | 110 / 83 / 83 |
| Random subsets of persistent effects realizable in any order | 12 / 12 | 3 / 3 |
| ⇒ lower bound of reachable states | **2^20 ≈ 1.05·10^6** | **2^83 ≈ 9.7·10^24** |
| BFS layers at T (unique new states per depth) | 1, 39, 808, 12 181, … (cap 150 s) | 1, 110, 5 307, … (cap) |
| BFS singles-only (T=1.2), exact | 3 236 states, 16 layers, 1 terminal | 522 states, 12 layers, 1 terminal |
| BFS basic only (T=18), capped | 1, 22, 290, 2 851, 18 163 … | 1, 14, 119, 835, 5 179, 17 694 … |

Random-walk terminals (uniformly random enumerated step until none; distinct walks, duplicated seeds removed):

| Candidate | T | Walks | Distinct terminals (candidates left) | Enumerations with limits |
|---|---:|---:|---|---:|
| 8e2b | 32 | 141 | **1** (125 = G) | 12 / 7 648 (0.16 %) |
| f197 | 32 | 69 | 5 (107, 140, 141, 150, 151) | 63 % |
| bcf460 | 36 | 14 | 1 (109) | 100 % |
| ca88 | 50 | 24 | 2: 132 (23×) and **0 = solved (1×)**, see §3 | 100 % |
| 03122 | 50 | 6 | 2 (133, 138) | 100 % |
| 55684 | 50 | 6 | 1 (146) | 100 % |
| 310fab | 50 | 9 | 1 (148) | 100 % |
| f23734 | 50 | 20 | 1 (171) | 100 % |
| b4d9 | 42 | 15 | 2 (142, 143) | 100 % |

Interpretation. For 8e2b at T=32 the enumerator is (almost always) complete and
the transition system behaves confluently on every probe (one terminal G,
unsolved). A negative proof is then mathematically within reach, but the
exhaustive search must visit ≥2^20 states (provably reachable, all distinct);
at 63 ms/state that is ≥18 h, and the true lattice (k=123 eliminations,
BFS layer 3 alone = 12 181) is far larger. For f197, ca88, 03122, b4d9 the system
is demonstrably **not confluent** (several terminals) — the observed cause is
limit-dependent detectors (node/length/start limits depend on the global state),
so closure-based shortcuts are unsound for this implementation as is.

## 3. Witness probes (positive evidence only, validated)

Greedy "cheapest step first" and "apply-all fixpoint" with the exhaustive
`StepEnumerator`, then the randomized walk probe. Every witness would be
re-validated from the root with `proofs.validate_path`.

| Candidate | Human upper | T probed | Cheapest-first | Fixpoint | Random walks | Witness ≤ T? |
|---|---:|---:|---|---|---|---|
| 8e2b (22) | 35 | 32 | stuck 125, complete enumeration | stuck 125, complete | 141 walks → G | none |
| f197 (23) | 35 | 32 | stuck 151, limits | stuck 150, limits | 5 terminals, none solved | none |
| bcf460 (22) | 39 | 36 | stuck 109, limits | stuck 109, limits | 1 terminal | none |
| ca88 (22) | 55 | 50 | stuck 132, limits | stuck 132, limits | **1 of 24 walks solved** (seed 11, walk 4: 164 steps, max 50, 29 Forcing Chain, 20 ALS-XY-Wing, 14 ALS-XZ, 3 ALS Chain, 3 Grouped AIC …); `validate_path` = valid | **yes, ≤ 50** (upper 55 → 50; still ≥ ultra_threshold 36) |
| 03122 (24) | 55 | 50 | stuck 138, limits | stuck 133, limits | none | none |
| 55684 (24) | 55 | 50 | stuck 146, limits | stuck 126, limits | none | none |
| 310fab (25) | 55 | 50 | stuck 148, limits | stuck 148, limits | none | none |
| f23734 (25) | 55 | 50 | stuck 171, limits | stuck 171, limits | none | none |
| b4d9 (26) | 50 | 42 | stuck 143, limits | stuck 142, limits | none | none |

ca88 shows that a valid ≤ T witness can exist although both deterministic greedy
orders and 23 random walks end in the same unsolved 132-candidate dead end, and
although 300 s of `threshold_search` did not find it (best-first never left the
dead-end region). The positive result lowers ca88's upper bound to 50 (next
search would be T=42); it is not a certificate of the minimum.

No candidate obtained a witness below `extreme_threshold` = 30, so no candidate
can be rejected by a simpler path from this evidence. Probes take 0.2–8.5 s
(greedy) — finding positive evidence is cheap compared to exhausting the lattice.

## 4. Classification

1. **Too many states (dominant, structural).** The reachable lattice at T is
   exponential in the number of commuting deductions (proved lower bounds 2^20
   and 2^83). Unique states grow linearly without saturation; 85–91 % of
   generated children are transpositions of already-known states (same
   eliminations, different order). No per-state speed-up can make full
   exhaustion fit 60 s (would require < 60 µs/state for 8e2b even at the lower bound).
2. **Negative proof structurally impossible at most thresholds.** Limits are
   reported in 100 % of enumerations for T ≥ 36 (ALS_SIZE_LIMIT is always raised
   while any unit has > 5 empty cells; Grouped AIC chain node/length limit) and in
   63 % at T=32 for f197. Only 8e2b at T=32 has (almost) complete enumeration.
3. **Equivalent steps / repeated work (constant factor 2–3×).** 44–62 % of children
   duplicate a sibling's resulting state (rating-in-key), each validated+applied;
   proof representations 10–64× redundant inside chain/forcing detectors and
   serialized to JSON for tie-breaking (6–14 % of wall time).
4. **Per-state enumeration cost.** 63 ms (AIC ≈ 50 %) at T=32, 450–490 ms at T=50
   (Forcing 23–30 %, ALS 37–42 %, Grouped AIC 17–18 %). Important but secondary.
5. **Ordering** — irrelevant for negative proofs; relevant for witnesses
   (best-first by candidate count dives into the dead end and permutes it).
6. Transposition/heap/signature/memory are not bottlenecks (heap+signature < 0.02 %, RSS ≤ 58 MB);
   depth dominance and re-expansion never trigger.

## 5. Recommendations

Sound without extra assumptions (keep TIMEOUT/limits INCONCLUSIVE, keep validators):

- **Fail fast to INCONCLUSIVE when a negative result is already impossible**:
  once any enumeration in a threshold search reports a limit reason, the result
  can no longer be `PROVEN_UNSOLVABLE`; continuing only serves witness finding.
  Make that explicit (switch to a witness-only mode with a bounded budget).
- **Effect-level dedup before validation**: group steps by effect ignoring rating,
  keep the minimum-rating representative (never raises a witness's max rating).
  Removes 44–62 % of validate/apply calls.
- **Transposition check before `validate_step`/`apply_step`**: compute the child
  masks with bit operations, look up `best_depth`, validate+apply only for new
  states (85–91 % of children are hits). Witness edges are still all validated;
  only the defensive "enumerator emitted an invalid step" check on discarded edges
  is lost (keep it in an audit mode).
- **Cheaper canonical tie-break**: dedupe by effect first, serialize only true ties;
  or use a structured tuple key. 6–14 % of time.
- **Batch `apply_step`** (one copy/validate per step instead of per elimination) and
  avoid `is_solved`→`validate` per pop: ~10–20 % at T=32.
- **Memoize pure detector projections** (e.g. X-Chain/fish per digit plane) — sound
  only after verifying the detector output depends solely on that projection.
- **Witness search portfolio** (randomized restarts / diversified best-first):
  any order is sound for `SOLVED`; cheap greedy/walk probes take seconds.
- Replace `best_depth` with a visited set when `root_candidates ≤ max_path_depth`
  (provably equivalent; negligible gain, simpler).

Require a monotonicity / confluence (persistence) theorem for **this**
implementation — not sound otherwise:

- Greedy-closure negative proof ("fixpoint G unsolved ⇒ unsolvable"): valid if every
  step enabled at a reachable S ⊇ G has its effect derivable at G. Would make 8e2b@32
  a 0.4 s proof. **Empirically violated** for f197@32, ca88@50, 03122@50, b4d9@42
  (multiple terminals), most likely because limits (chain work 100 000, forcing
  starts = first 160 candidates, forcing nodes/depth) depend on the global state.
- Partial-order / stubborn-set reduction (deadlock-preserving; "solved" is a
  deadlock): needs proven independence (an elimination never disables another
  enumerated step). Global work/start limits make every pair dependent, so POR
  is unsound with the current limit semantics; a per-technique proof of
  persistence on the no-limit regime would be required.
- Eager singles (apply all singles first): same persistence requirement for all
  other detectors.
- Making limits part of the technique definition (e.g. "ALS ≤ 4 cells", "chain ≤ 19
  links") would turn current limit reasons into model scope and enable negative
  proofs, but it changes certification semantics — a spec decision, not an
  optimization.
