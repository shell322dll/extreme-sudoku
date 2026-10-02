# Phase 7.1: code review (performance/search optimization + SSL-v1 wiring)

Role: Reviewer. Read-only for `generator/`. I wrote only this file. Scratch scripts are in the session
scratchpad (`rv_*.py`). The mathematical proofs (`PHASE7_1_STUCK_STATE_PROOFS.md`) were reviewed separately in
`PHASE7_1_SSL_REVIEW.md`. This review covers the code.

Scope: `diff -r` of the pre-7.1 baseline (`scratchpad/phase7_baseline_src/generator`) against the current
`generator/`. Changed files: `certification/{config,enum_chains,enumeration,io,models,pipeline,search}.py`. New
files: `certification/{transitions,stuck_state}.py` and the tests `test_certification_search_opt.py` and
`test_certification_ssl.py`. `proofs.py`, `human_solver.py`, the solver techniques and `exact_solver` are byte-identical
to the baseline. The pinned SHA-256 table in `stuck_state.py` matches the current sources (no mismatch).

## Verdict

**No P0 or P1 findings.** I found no way to get a false certificate or a false `PROVEN_UNSOLVABLE_WITHIN_MODEL`
through production code paths. Every limit and timeout I tried ends as `INCONCLUSIVE`/`TIMEOUT`. The P2 items
are hardening, documentation and budget-efficiency issues. **The code is safe to use for producing the production
dataset.** P2-1 is worth fixing before large runs, because it can turn conclusive exhaustive results into
`NODE_LIMIT` on puzzles where SSL is not applicable (T ≥ 36).

## Checks performed

| # | Check | Result |
|---|---|---|
| 1 | Full suite `python -m unittest discover -s generator/tests` | **407 tests OK** (161 s) |
| 2 | `enumerate_chains` (all 5 chain families) and full `StepEnumerator.enumerate(T=35)`, baseline vs current, on 17 real states (3 puzzles, random walks), default config and a tight config (`max_chain_search_nodes=3000`, `max_chain_length=7`). Compared: SHA-256 of all step JSON, step count, `limit_reasons`, `complete`, `work` (`rv_equiv.py`) | **204/204 identical** (113 entries carried limit reasons) |
| 3 | `threshold_search` on 17 states × T∈{2,8,14,22,32,35}: baseline vs new exhaustive (`use_stuck_state_lemma=False`) vs new with SSL (`rv_search.py`) | No status conflict anywhere. Baseline vs new: 15 PROVEN=PROVEN, 6 new SOLVED where baseline ran out of budget, no regression. New exhaustive vs SSL: 21/21 conclusive verdicts agree. SSL is conclusive in 86/102 cases (exhaustive in 21/102) |
| 4 | Random-DAG fuzz on the abstract provider: 3000 graphs × random T, depth limit and frontier priority; ground truth by DP (`rv_fuzz.py`). Includes 1000 `minimax_descent` runs against the brute-force minimax | 0 false PROVEN, 0 missed reachable-within-depth goals, all witnesses are real ≤T edges within the depth limit, minimax matches whenever the descent is conclusive |
| 5 | The same fuzz in "visited" mode (`depth_bound` = true longest path, `max_path_depth` above it) (`rv_fuzz2.py`) | 3000/3000 correct |
| 6 | SSL attacks: poisoned enumeration cache at the root (`rv_poison.py`); T≥36; tiny chain limits; tampered pins/ratings/technique set; cached fresh enumerator; timeout | All rejected (G4/G5/G6/G7/G0). See P2-2 for runtime monkeypatching |
| 7 | Invalid-step handling in exhaustive mode (`rv_invalid.py`) | See P2-3 |
| 8 | Node accounting, baseline vs new, on PROVEN cases (`rv_nodes.py`) | See P2-1 |

## Contract checklist

- **Limits produce INCONCLUSIVE, never PROVEN.** `search.py:180-273`: every limit goes through `note()` into
  `reasons`, and PROVEN is returned only when `reasons` is empty (`search.py:270-273`). TIME, NODE, STATE,
  MEMORY, PATH_DEPTH and enumerator limits are covered by `test_tiny_budgets_are_inconclusive_never_proven`.
  - A late certificate is not possible. The SSL branch requires `perf_counter() < deadline` after the check
    (`search.py:172`), and G4 also checks the deadline (`stuck_state.py:464-465`).
  - SOLVED is checked against the deadline (`search.py:194`, `search.py:167`).
  - The pipeline checks `timed_out()` again after the descent (`pipeline.py:275`).
- **SSL guards are all wired.** G0–G8 are in `stuck_state.py:421-490`. The G4 enumerator is a fresh
  `StepEnumerator(config, cache=False)`, and a cached factory fails G4.fresh. Other properties:
  - G5.scope uses `0 ≤ T < 36` and requires `type(T)` to be int or float.
  - The dependency table is checked against the enabled set.
  - G6 checks classes, order and flags.
  - G7 checks 16 pinned files.
  - G2 uses the bitwise `dominates` with the correct direction (`stuck_state.py:183-193`).
  - G1 and G3 run on fresh `SudokuState` copies.
  - A G8 replay failure is an ERROR.
  - `audited_enumerator` is required for the closure (`transitions.py:225`).
  - The confluence alarm runs after every descent (`search.py:347-351`) and leads to INVALID_PROOF in the
    pipeline.
- **Effect dedup.** `select_transitions` (`search.py:29-68`) groups by the **successor signature**, so distinct
  states are never merged. Within a group, `representative` takes the minimum of (rating, step_key, full JSON),
  which does not depend on input order. Every frontier-creating edge, and therefore every witness edge, is
  validated (`search.py:242-247`). The witness gets an extra fresh `validate_path` in the descent
  (`search.py:328-333`). `canonical_steps` produces the same output as the baseline: the same representative and
  the same order, so `ALTERNATIVE_STEP_LIMIT` truncation is unchanged (confirmed by check 2).
- **Dominance and transposition.** Within one threshold, feasibility depends only on reachability within the
  depth limit. The record keeps the best depth, and `expanded` keeps componentwise minima, which only discards
  arrivals dominated in depth. The max-rating reopen only adds work. "Visited" mode is used only when
  `depth_bound(root)` (the live candidate count) is below `max_path_depth`. Each step removes at least one live
  candidate (both apply paths require live targets, and a placement zeroes the mask), so the depth limit cannot
  bind then. This is correct and conservative (it is not `candidates − 81`, which would be tighter). Fuzz checks
  4–5 confirm it.
- **Caches.**
  - The enumeration cache key is (full `signature()` = 81 values + 81 masks, technique name). Per-technique
    results do not depend on T, so the absence of T from the key is correct.
  - Results containing `TIME_LIMIT` are not stored (`enumeration.py:104-107`). All three enumerators name the
    deadline reason `TIME_LIMIT`.
  - Deterministic limit reasons are cached and re-emitted with the `name:` prefix on hits.
  - The validation cache is keyed by (signature, full frozen `LogicStep`), per provider and per config.
  - Both caches are created per `certify_puzzle` invocation (`pipeline.py:237`), so no certificate cache is
    persisted.
  - `InferenceGraph` sharing between AIC and Nice Loop uses (grouped, mode), and the graph is pure (it is not
    mutated during enumeration).
- **Fast `apply_step`.** `transitions.py:77-114` matches `human_solver.apply_step` for SudokuState:
  - the same preconditions, in the same order;
  - per-placement availability, so same-unit double placements fail as in the reference;
  - one final validation, whose equivalence follows from the monotonicity argument, which I re-checked.
  It is also covered by `FastApplyTests`. Witnesses are replayed with the reference implementation
  (`validate_path`).
- **Exact solver and anti-cheat.** There is no `exact_solver` or solution use in search, transitions,
  enumeration or stuck_state. `proofs.py` and `human_solver.py` are unchanged.
- **Early REJECTED** (`pipeline.py:253-266`). It applies only for stop_reason other than ERROR or
  INVALID_WITNESS, and only when a validated witness has `upper < extreme_threshold`. This is sound, because the
  true minimum is at most that rating. It leaves `minimum_required_rating=None` and `search_status` not SOLVED,
  so `production_eligible` is False. It cannot produce eligibility.
- **Production export and readback.**
  - `negativeProofKind` is exported and compared.
  - `negative_certificate` holds the closure signature, length, candidates, work at G, fingerprint and guard
    results with deterministic details. It is not excluded from the comparison.
  - Only `search_telemetry` and per-threshold `telemetry` are excluded. Both are diagnostics: timings, cache
    statistics, first-limit indices and SSL outcome mirrors.
  - `cache_hits` and `states_explored` remain compared and are deterministic.
  - `test_production_export_readback_with_ssl_record` round-trips an SSL record.
- **Determinism.** All orderings are total: (rating, step_key, JSON), and the heap tuples carry unique serials.
  Caches return byte-identical results (check 2 and `test_cached_and_uncached_enumeration_identical`). Two fresh
  pipeline runs compare equal (`test_hard_puzzle_minimum_certified_by_ssl`).

## Findings

### P0 (false certification possible)

None.

### P1 (wrong status or contract)

None.

### P2

**P2-1. Max-rating re-expansions consume `node_budget` with no benefit to the verdict, so some exhaustive proofs
become `NODE_LIMIT`.**
- Location: `search.py:229-258` (reopen on `better_max`) and `search.py:199-202` (every expansion counts).
- Problem: within one threshold, SOLVED vs PROVEN depends only on reachability. Re-expanding a state because it
  was reached again with a lower running max rating changes only which witness is found, and the descent lowers
  T anyway.
- Reproduction (`rv_nodes.py`, state #14 of `rv_states.txt`, T=22, exhaustive):
  - The new code needs 360 expansions for 300 unique states (60 `max_rating_repushes`). The baseline needed 300.
  - With `node_budget=320`, the baseline proves and the new code returns `INCONCLUSIVE_BUDGET [NODE_LIMIT]`.
- Impact: this is conservative, never a false result. It matters mainly for T ≥ 36, where SSL cannot apply, and
  under the shared descent node budget.
- Suggestion: drop the max-rating reopen (keep depth reopen), or do not count such re-expansions against
  `node_budget`.

**P2-2. "A custom or patched enumerator never uses SSL" is enforced only for the class and its two methods.**
- Location: `stuck_state.py:31-35`, `transitions.py:225`, and the claim in `CERTIFICATION_SPEC.md:149-150`.
- Problem: runtime patching of module-level functions is not detected. G4's fresh enumerator calls the same
  patched code, and G7 hashes only the files on disk. Examples of undetected patches:
  - `enum_chains.enumerate_chains`
  - `enumeration.canonical_steps`
  - `chains.InferenceGraph`
  - technique `find_steps`
- Reproduction (`rv_patch.py`, HARD puzzle):
  - Unpatched, T=35 is `SOLVED`.
  - With `patch("generator.certification.enum_chains.enumerate_chains", lambda *a, **k: EnumerationResult())`,
    T=35 becomes `PROVEN_UNSOLVABLE_WITHIN_MODEL` with kind `STUCK_STATE_SUPERSET_LEMMA`.
  - Patching `WWing.find_steps`/`EmptyRectangle.find_steps` plus the chains gives PROVEN at T=25.
- Impact: there is no production path, since nothing patches at runtime. Exhaustive mode is equally misled by
  such patches, because the patch changes the model. The SSL-specific risk is that SSL relies on audited
  properties of exactly this code.
- Suggestion: soften the spec wording ("class-level replacement is detected; in-process monkeypatching is out of
  scope"). Optionally, also pin the identity of `enum_chains.enumerate_chains`, `canonical_steps`,
  `InferenceGraph` and each technique's `find_steps` at import.

**P2-3. Exhaustive mode no longer validates every enumerated step, and the spec attributes this change only to
SSL.**
- Location: `search.py:229-247` (the transposition hit `continue`s before `provider.validate`),
  `search.py:51-53` (non-representative steps of a successor group are never validated), and the spec's
  "Semantic note" at `CERTIFICATION_SPEC.md:176-179`.
- Reproduction (`rv_invalid.py`, mock provider):
  - An invalid proof that leads to an already-known state gives `PROVEN_UNSOLVABLE_WITHIN_MODEL` with no error.
  - A higher-rated invalid duplicate of a valid successor is silently dropped.
  - The baseline validated every step before applying it and would return `ERROR` in both cases.
- Impact: this is not a soundness issue. Those steps add no new state, the model includes every emitted step,
  and witness edges are always validated. The defensive "a detector produced an invalid proof" alarm is weaker
  in exhaustive mode too.
- Suggestion: update the spec. Optionally, count unvalidated duplicates in telemetry, or validate them in a
  debug or audit mode.

**P2-4. The pinned-source table (G7) omits `solver/models.py`.**
- Location: `stuck_state.py:121-154`.
- Problem: `solver/models.py` defines `CandidateNode` (equality, hash and order used by `InferenceGraph`'s node
  set and sort), `LogicStep`, `Chain` and `ChainLink`. A change to it can change the audited enumeration without
  failing G7. `algorithm_fingerprint` covers it for reproducibility, but not as an SSL guard.
- Smaller gap: `stuck_state.py` and `search.py`'s SSL branch are trusted code that cannot pin themselves.
  `PHASE7_1_SSL_REVIEW.md` R1 already asks for this to be covered by review, and this review covers it.
- Suggestion: add `solver/models.py` to `PINNED_SOURCE_SHA256`. Optionally also add
  `solver/advanced_config.py`, which is harmless today.

**P2-5. A solved SSL closure is accepted as a witness without the `max_path_depth` and `node_budget` semantics
of the search.**
- Location: `search.py:165-170`.
- Problem: the witness is validated (`validate_path`), so it is a correct upper bound. However, it can be longer
  than `max_path_depth` (closure lengths of 73–84 were seen, compared with 256), and it reports
  `states_explored=0`.
- Impact: none on correctness. Note it for metrics consistency.

**P2-6. `confluence_violation` is not wrapped fail-closed.**
- Location: `stuck_state.py:208-245`, called at `search.py:347`.
- Problem: if `reference_apply` or `parse_signature_text` raised (impossible today, because the witness was
  already validated and the signature was produced by the code), the exception would escape `minimax_descent`
  and `certify_puzzle` uncaught.
- Suggestion: wrap it and turn exceptions into the same ERROR alarm.

**P2-7. Documentation drift.**
- `enumeration.py:63-67`: the `canonical_steps` docstring says `canonical_effects` "is used by the search". The
  search actually groups by successor signature (`select_transitions`), which is a stronger and still sound
  merge. `canonical_effects` is used only in tests.
- `CERTIFICATION_SPEC.md:80-84` still describes only "equivalent effects at the same rating" dedup and depth-only
  merging. It does not mention successor-signature dedup across ratings, the max-rating reopen, or the "visited"
  depth rule.

**P2-8. The cache key does not include the config.**
- Location: `EnumerationCache` keys (`enumeration.py:81-120`).
- Problem: correctness relies on one cache per `StepEnumerator`, and each enumerator has a fixed frozen config.
  The constructor still accepts an external `cache=` object, which a caller could share between enumerators
  with different `advanced_config`/limits. That would cross-contaminate (complete results from a larger limit
  would be reused under a smaller limit).
- Status: production never does this. G4 is unaffected (`cache=False`).
- Suggestion: include `config.fingerprint()` in the key, or reject foreign caches.

### Notes (no action required)

- **N1.** `CERTIFICATION_VERSION` is still "1", although records gained `negativeProofKind` and the config gained
  `use_stuck_state_lemma`. Pre-7.1 production records therefore fail `validate_production_database`, because
  the config dict and record differ. This is fail-closed, but every existing production dataset must be
  regenerated.
- **N2.** Cache poisoning (an externally inserted empty result for the root) is correctly rejected by SSL's G4
  (fresh enumerator). The exhaustive search, however, trusts the poisoned in-process cache and "proves"
  unsolvability. This is invocation-local and not reachable from production inputs (`rv_poison.py`).
- **N3.** At T ≥ 36, the hook still computes a closure. G5.scope then rejects it, but a solved closure is a useful
  validated witness, so this is not wasted. The cost is bounded by the shared enumeration cache.
- **N4.** `negative_proof_possible` is informational. Status decisions use `reasons` directly, and the two are
  consistent.

## Test quality

The new tests test what they claim:
- **Minimax mock graph.** The paths 2→8→2, 4→5→4 and 3→7 must give 5, with PROVEN at 4.
  `test_mock_graph_minimax_is_five_with_conclusive_failure_at_four` asserts upper=5, conclusive, last
  threshold 4 PROVEN, the witness b1–b3, and that every ceiling is strictly below the witness known at that time.
- **Dedup (5 vs 8, same successor).** `test_identical_successor_keeps_only_lowest_rating` checks the result,
  order independence and telemetry.
- **Budgets give INCONCLUSIVE.** Covered by TIME, NODE, STATE, PATH_DEPTH and MEMORY tests.
- **Caches.**
  - Cached vs uncached equality, including limit reasons under a tight config.
  - TIME_LIMIT results are not cached (with a real patched deadline).
  - The cache is bounded.
  - The validation cache is keyed by signature.
- **SSL.**
  - Positive certificate with every guard listed.
  - Rejection for T ≥ 36, a missing dependency, a tampered hash, ratings or set, an incomplete or short-chain G,
    G1/G2/G8, and timeouts.
  - A solved closure becomes a witness.
  - Exhaustive-vs-SSL agreement (11 cases, at least 5 by SSL).
  - Random walks, a whole-lattice unique terminal, random supersets (R6), and the confluence alarm in both unit
    form and pipeline form.

Gaps, all minor:
- No test for module-level monkeypatching (P2-2).
- No test that an invalid duplicate or transposition step is (not) reported (P2-3).
- No test asserting node-budget parity with the baseline (P2-1).
- `test_descent_shares_node_budget` accepts either `NODE_BUDGET` or `INCONCLUSIVE`, which is loose.
- The fuzz checks 4–5 above would be a cheap and valuable addition to the repository.

---

## Re-review (after remediation of P2-1..P2-8 and the cache memory reduction)

Re-checked files: `certification/{search,stuck_state,enumeration,transitions}.py`, both new test modules and
`CERTIFICATION_SPEC.md`.

### Re-checks

| Check | Result |
|---|---|
| Full suite | **413 tests OK** (182 s) |
| Pinned sources | 17 files, 0 mismatches. `solver/models.py` is now pinned. The identity table has 72 objects, and `changed_code_identity()` returns empty |
| Enumeration equivalence vs pre-7.1 baseline (`rv_equiv.py`, same 17 states, 2 configs) | **204/204 identical** (step JSON hashes, counts, limit reasons, `complete`, `work`). The `enumeration.py` diff against my earlier verified version touches only the cache key (`config_key` prefix), the LRU size and docstrings. Dispatch, ordering, canonicalisation and limit handling are unchanged |
| Search comparison (`rv_search.py`, 102 cases): baseline vs new exhaustive vs SSL | No status conflicts. Baseline vs new: 15 PROVEN=PROVEN with **identical expansion counts** (including #14/T=22: 300 = 300). 6 new SOLVED where the baseline ran out of budget. No regression. New exhaustive vs SSL: all 21 conclusive verdicts agree |
| Fuzz (`rv_fuzz.py`, `rv_fuzz2.py`) | 0 failures (3000 + 1000 descents + 3000 visited-mode) |
| Cache poisoning with the new key format (`rv_poison.py`, T=32) | SSL rejected by G4 and falls back. Same in-process caveat as N2 |

### Fix verification

- **P2-1: fixed.** `search.py:117-260`: the record is (best depth, holder serial), reopen happens only for a
  strictly shallower arrival, and only when the depth limit can bind. Otherwise plain visited semantics apply.
  - #14/T=22 now takes 300 expansions with 0 repushes. With `node_budget=320` the result is PROVEN.
  - Regression test: `test_review_state_14_node_budget_not_worse_than_baseline`.
  - Verdict semantics are unchanged (fuzz plus the baseline comparison above).
- **P2-2: largely fixed, residual gap.** `stuck_state.py:24-81`: `audited_enumerator` (used for the closure and in
  G6) now pins the identity of 72 in-process objects:
  - the enumerate/run methods;
  - `enum_*` entry points and `canonical_steps`;
  - both `InferenceGraph` bindings;
  - `default_techniques`, `Technique.step` and `human_solver.apply_step`;
  - `find_steps` and `step` of every technique class, plus per-instance `find_steps` overrides.

  Re-running `rv_patch.py`, patches of `enum_chains.enumerate_chains`, technique `find_steps` and
  `enumeration._grouped` no longer use SSL (INCONCLUSIVE). **Residual:** helpers below the pinned entry points
  are still not covered. Example: `patch("generator.solver.techniques.chains.conflicts", lambda a, b: False)`
  makes HARD at T=35 `PROVEN_UNSOLVABLE_WITHIN_MODEL` via SSL, while the truth is SOLVED. The same holds in
  principle for `step_key`, `PEERS` and `SudokuState` methods. This requires in-process monkeypatching, which no
  production path does. G7 still pins the bytes on disk. **Accepted as a documented limitation (note, not a
  blocker).** Suggested wording in the spec: "identity of the dispatch entry points is pinned; arbitrary
  in-process monkeypatching of deeper helpers is out of scope."
- **P2-3: fixed (documentation).** The "Validation scope" paragraph (`CERTIFICATION_SPEC.md:101-110`, reference at
  :220) states that transposition and duplicate edges are not validated in either mode, and why this does not
  weaken the model. `rv_invalid.py` behaves as documented.
- **P2-4: fixed.** `solver/models.py` is in `PINNED_SOURCE_SHA256` (17 files) and all pins match.
- **P2-5: fixed.** `search.py:166-180`: a solved closure is accepted only if `len(path) <= max_path_depth` and
  `<= node_budget` (the remaining descent budget). It is counted in `states_explored`/`expansions`. Otherwise
  the search falls back to exhaustive.
  - Test: `test_solved_closure_respects_path_depth_and_node_budget`.
  - Observed in `rv_poison.py` with `node_budget=50`: the 84-step closure was declined, giving FALLBACK.
- **P2-6: fixed.** `confluence_violation` wraps `_confluence_violation` and turns any exception into an alarm
  (`stuck_state.py:256-261`). That leads to ERROR and then INVALID_PROOF. Test:
  `test_confluence_check_exception_is_an_alarm`.
- **P2-7: fixed.** The `canonical_steps` docstring and the spec now describe successor-signature dedup and the
  depth rule.
- **P2-8: fixed.** Cache key is `(enumerator.config_key = config.fingerprint(), signature, name)`
  (`enumeration.py:171-185`). Test: `test_shared_cache_is_keyed_by_config`.
- **Memory caps.** The enumeration LRU is 12000 entries and the validation LRU is 4096. Both are purely
  performance settings: a miss recomputes the identical result, as shown by the equivalence check. Determinism
  is unaffected.

### Final verdict

No P0 or P1. All P2 items are fixed except one residual note: P2-2 does not cover monkeypatching of deeper
helpers. That case is not reachable in production and is not a blocker. **The Phase 7.1 code is safe to use for
producing the production dataset.** Pre-7.1 production records must be regenerated (N1).
