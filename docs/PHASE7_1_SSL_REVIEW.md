# Phase 7.1: SSL review (independent reviewer, mathematical soundness)

Role: Reviewer. Read-only for `generator/`, `web/` and `data/`. The scratch scripts are outside the
repository (`ssl_stress.py`, `ssl_degen.py`, `ssl_synth.py`, `ssl_lattice.py` in the session scratchpad).

Subject: `docs/PHASE7_1_STUCK_STATE_PROOFS.md` (SSL, theorem in §2, family proofs in §4, guards in §6).

Code basis: SHA-256 of every source listed in `stuck_state.PINNED_SOURCE_SHA256` equals the pinned value at
review time (2026-10-02, checked by script; the list of mismatches is empty). Every proof was re-checked
against the detector code itself, not against the planner's paraphrase.

## 0. Verdict

| Family | Verdict | Comment |
|---|---|---|
| Theorem §2 (order ⊒, induction, solved ⇒ G solved) | **ACCEPT** | Checked against `SudokuState.place/eliminate/validate`, `human_solver.apply_step` and fast `transitions.apply_step` (§1) |
| Full House / Naked Single / Hidden Single | **ACCEPT** | |
| Locked Candidates | **ACCEPT** | |
| Naked Pair/Triple/Quad | **ACCEPT** | Hall lemma correct (eligibility `2..size`, `mask == size`) |
| Hidden Pair/Triple/Quad | **ACCEPT** | |
| X-Wing / Swordfish / Jellyfish | **ACCEPT** | |
| Skyscraper / 2-String Kite / Turbot Fish | **ACCEPT** | CCL. `accepts`, unit indices and `combinations` order are the same at G |
| Empty Rectangle | **ACCEPT** | All 4 cases checked, including the "near" geometry |
| XY-Wing | **ACCEPT** | |
| XYZ-Wing | **ACCEPT** | The "helper fact" (a cell seeing two peers lies in a common unit with them) is proven true |
| W-Wing | **ACCEPT** | |
| X-Chain / XY-Chain / AIC (open) | **ACCEPT** | Includes completeness §4.11 |
| AIC discontinuous loops | **ACCEPT** | |
| Nice Loop | **ACCEPT** | |
| Grouped AIC | **ACCEPT-WITH-CONDITIONS** | Gap in the "walk lemma" (§3.2 below). It can be closed with LC, so it is not a counterexample. The document must be amended. Empirical coverage is modest. |

**Overall:**
- **T = 32: ACCEPT.** SSL may be used for production `PROVEN_UNSOLVABLE_WITHIN_MODEL`, subject to the guards in §5.
- **T = 35: ACCEPT-WITH-CONDITIONS.** The gap is closed below, so mathematically I accept it. Before release, the planner/Coder must add the closure argument to §4.12 of the proofs document (condition C1). The Grouped AIC tests in §5 are recommended.
- T ≥ 36: SSL is **not applicable** (agreed with §5 of the proofs document).

No counterexample was found, either analytically or empirically (§4).

## 1. Theorem and transition model

- **Order ⊒ and O1–O4.** Checked. O2 (X-placed ⇒ G-placed with the same digit) follows from "G-empty ⇒ X-empty" and `L_G ⊆ L_X`. O3 follows from O2 and validity.
- **Induction step.**
  - A placement (c,d) that is P in G: the peers p of c have no d in `L_G(p)` (`validate`: a mask conflicting with a peer's placement is forbidden, and a duplicate in a unit is forbidden).
  - An elimination that is D in G does not touch `L_G`.
  - `apply_step` requires every effect to target a live candidate of the *original* state (`human_solver.py:18-20`), applies placements before eliminations, and raises on an elimination in a cell filled by the same step.
  - None of this breaks the argument: SSL is proven for every emitted step whose application succeeded.
- **Fast `transitions.apply_step`.** Identical preconditions, and one final validation in place of a validation after each effect. The monotonicity argument in its docstring is correct: no validity condition can be "repaired" by a later effect. It is unchanged in the current file.
- **Final step.** X solved and X ⊒ G ⇒ G has no empty cells ⇒ G is solved. Correct.
- **The model M_T.** Every limit in `enumerate_chains` / `StepEnumerator` only removes steps (`CHAIN_*`, `ALTERNATIVE_STEP_LIMIT`, `canonical_steps/effects`). So the production transitions ⊆ M_T, and proving the unbounded model is sufficient.

## 2. Checks per family against the code (what was specifically checked)

- **Early exits / representatives.**
  - Basic detectors iterate over everything. `unique_steps` deduplicates by effect only, and only existence matters.
  - `enumerate_chains` has no `seen` set. Every early return records `CHAIN_NODE_LIMIT` or `TIME_LIMIT`.
  - The legacy `_GraphTechnique.find_steps` (BFS with `seen` and a silent `budget` exit, `chains.py:168-175`) is **not** used by certification, because `_run` sends all chain techniques to `enum_chains`. That is important: it would break §4.11. See guard R3.
- **Exact-count conditions.**
  - Naked: `2 ≤ cnt ≤ size`, `mask == size`. Hidden: `1 ≤ len ≤ size`, `len(cells) == size`. Fish: `2..size`, `len(cover) == size`.
  - ER: `len(pair) == 2`, `target ∉ box ∪ pair`.
  - W-Wing: bridge `len == 2`. XY/XYZ: bivalue/trivalue.
  - Every degenerate case reduces at G to a single, LC, a smaller subset/fish, a Naked Pair or an XY-Wing, as the proofs document says.
  - All ratings of the reduced techniques are ≤ the rating of the original technique (`registry.py`).
- **Filters "no progress / already covered".**
  - `emit` drops steps with empty effects. At G the target is live in the relevant case, so the effects are nonempty.
  - Effect deduplication across ratings exists only in `canonical_effects` (the search), not in `enumerate`.
- **Limits and long chains (§4.11).**
  - In the DFS the check `nxt in path and nxt != start` comes before `length > max_length`. Every attempt to extend a path of length `max` (19) to a neighbour that is not in the path, including a return to start, gives `CHAIN_LENGTH_LIMIT`. The Nice-loop closure has its own check (`enum_chains.py:99-100`).
  - Consequence: if enumeration at G is complete, there is no simple alternating path longer than 19 links, and all shorter ones were traversed.
  - For non-grouped families the G-image of an X-chain is the *same* path, of the same length. So a long chain at X **cannot** be "hidden" at G without a limit reason.
- **Rating classification.** The image at G is emitted by the same technique (or, for grouped, possibly by plain AIC at 30 < 35, or by LC at 2). Nothing is ever promoted to a higher rating. For XYZ → XY-Wing/NP and ER → LC the rating goes down.
- **Bounds on cell/unit iteration.** LC: source box → 18 lines, line → 9 boxes. ER: all row/col pairs of the box. W-Wing: all bridges. Nothing is cut off.

## 3. Comments on the proofs document

### 3.1 Minor inaccuracies (do not affect correctness)

- §4.8 (Nice Loop, "t live and some node not live"): the conclusion is "t is D", which contradicts the case assumption "t live". The case is therefore *impossible*; it is not "harmless". The logic is correct.
- `PROOF_DEPENDENCIES` (in the Coder's code) requires HS for Naked Single. The proof does not need it (F1 only). This is a conservative fail-closed choice at T ∈ [1, 1.2) and is acceptable.

### 3.2 Gap in §4.12 (Grouped AIC): the walk lemma can reduce an open chain to length 1

The even repair (cutting out B_i…B_j with j−i even) preserves the kinds of the end links. For an **open** chain, however, it can leave a *single* strong link B_0 = B_1. Example: A1 (singleton s) = A2 − A3 (a group whose G-image is s) = A4, which reduces to s = B_3. The detector does not emit chains of length < 3 (`enum_chains.py:85`), so §4.12 has no contradiction for this case. **Closing it** (to be added to the document):
- The link is **cell-bivalue**, {(c,a),(c,b)}. A target t that conflicts with both ends is either in cell c with a third digit (not live, since c is bivalue) or would need digit = a and = b at once. So t is not live, which contradicts the case assumption.
- The link is a **partition / conjugate** in unit U (both ends plain-live, so d is not placed in U, and `supports_G(U,d) = a_G ⊔ b_G`):
  - t has digit d and t ∉ U (otherwise t would be a support and would share a cell with a or b, which a conflict excludes).
  - t sees every support of d in U, so all of them lie in U ∩ V, where V is box(t) if U is a line, or the row/column of t if U is a box. (For t outside a box, its row and column cannot both cross the box.)
  - So **Locked Candidates** (source U, target V) eliminates (t,d) at G. That contradicts H3. LC (2) ≤ 35 is already among the Grouped AIC dependencies.

After this addition the Grouped AIC proof is complete. I also checked the remaining parts of §4.12:
- R1/R2 for L* through LC: U is the box or the line of I_b; a cell that sees two cells of I_b lies in the box or the line.
- Uniqueness of group images: two different I's intersect in ≤ 1 cell.
- Odd repetitions give a discontinuous loop at a singleton with length ≥ 3.
- Quirk 2 (the target is the image of an internal group): the loop parities, and length ≥ 3.
- The emit filter `grouped and not groups` routes a chain without groups to AIC, whose graph contains the same singleton links: a partition of 2 singletons is a unit link.

All of these are correct.

## 4. Empirical adversarial testing

Every check: X ⊒ G at every state, and **every** enumerated step at X (production limits, which give a subset of M_T) has its eliminations D in G and its placements P in G. G is computed by a closure with a **random** step order, and its completeness is checked with a fresh `StepEnumerator(cfg, cache=False)`.

| Test | Volume | Violations |
|---|---|---|
| A. Random walks from the root (9 puzzles from `PHASE7_EXPERIMENT_INPUT.json` × T∈{12,18,25,30,32,35}; 8 demo puzzles × T∈{1.2,2,3,5,8,12}); 52 pairs with a complete unsolved G | 275,037 states / 3,642,263 steps; **every** walk terminal equals G (confluence); solution ∈ L_G and root ⊒ G every time | **0** |
| B. Random valid supersets X ⊒ G (not necessarily reachable: unplace some of G's placed cells, add candidates from the root) | 409,528 states / 3,270,715 steps | **0** |
| C. Degenerate G′: random removals of root candidates (true and false), closure, G′ complete → (i) the root terminal G must satisfy G ⊒ G′; (ii) supersets between G′ and the root; (iii) walks from root′ | 7 puzzles, 123 complete G′; 123 dominance checks; ≈ 143,000 steps | **0** |
| C′. Falsification on a demo puzzle solvable at T (if a complete stuck G′ ⊑ root existed, it would refute SSL) | 4,279 attempts at T∈{2,8,18,35} | **0** complete G′ found (consistent with the theorem) |
| D. Synthetic states (possibly unsolvable): the solution grid with 40–64 blank cells and random masks, closure, complete G, supersets X | 6 puzzle seeds; 370 complete G (all with group nodes); ≈ 39,000 steps | **0** |
| D′. Targeted Grouped AIC run at T=35 | 30 complete G at T=35; 1,200 X; 16,361 steps, including **2,371 Grouped AIC**, 2,226 AIC and 770 Nice Loop | **0** |
| E. Exhaustive lattice segments from late states of the closure path (8e2b: T=1.2/2/12/32; 1e2328: T=1.2/8/25/32), up to 3,236 states per segment | 22 fully exhausted segments: in every one, all states ⊒ G, every step satisfies SSL, and there is **exactly one** terminal, equal to G | **0** |

Steps in tests A+B by family (all ≤35 except Grouped AIC; see D′ for that): HS 1.78M, LC 1.09M, NS 1.07M, HP 391k, HQ 328k, Turbot 316k, NQ 281k, HT 265k, NT 198k, AIC 173k, NP 164k, ER 134k, Swordfish 117k, X-Wing 114k, Kite 98k, X-Chain 87k, Jellyfish 73k, FH 68k, XY-Chain 63k, XYZ 51k, XY-Wing 23k, Nice Loop 16k, Skyscraper 7k, W-Wing 4k.

Observations:
- At T=30/32, G is complete for 4 of the 9 experiment puzzles (51d96b, e740c2, b27c24, 1e2328). For the rest the cause is `AIC: CHAIN_LENGTH_LIMIT / CHAIN_NODE_LIMIT`.
- At T=35, G for the real puzzles is never complete, or the puzzle is solved. Grouped AIC is covered only by the synthetic states (D′).
- The production benefit at T=35 is therefore small for now. At T=32 it is real.

Limitation: the X steps were enumerated with production limits, not with the unbounded model. That is acceptable, because a limited enumeration only emits a subset of M_T. The unbounded part is covered by the proof (§4.11).

## 5. Required guards and conditions

Required (checked in `generator/certification/stuck_state.py`, as of the moment of review):

- **C1 (docs, before T=35 is used).** Add the closure of the length-1 case from §3.2 to §4.12 of `PHASE7_1_STUCK_STATE_PROOFS.md`. T=32 does not depend on it.
- **G1–G4.**
  - A fresh, valid G and a fresh root.
  - `dominates(root, G)` computed directly.
  - G is not solved.
  - A **fresh** `StepEnumerator(config, cache=False)`, with `complete is True`, `limit_reasons == []` and `steps == []` taken directly from `enumerate`, and a deadline that was not exceeded.
  - Implemented correctly.
- **G5.** T < 36, the ratings of the instances equal the registry equal the audited table, and the dependencies are enabled. Implemented. LC is in the Grouped AIC dependencies, which closure C1 needs.
- **G6/G7.**
  - The exact set, order and flags of the classes, and SHA-256 pins on the audited sources. Implemented; at review time all hashes match.
  - **R1 (recommended):** add to the pins `certification/models.py` (the `EnumerationResult.complete` default) and `solver/techniques/__init__.py` (it builds the set). Also cover `stuck_state.py` and the SSL branch of `search.py` in code review. They are part of the trusted computing base.
- **R2.** `audited_enumerator` ensures that the provider uses an unmodified `StepEnumerator`. Keep it: SSL is a theorem about `enum_chains`, not about `_GraphTechnique.find_steps`.
- **R3.** Any change to `enum_chains.py` that adds `seen`/memo pruning, a silent early exit, or a change in the order of the `in path` / `max_length` checks voids §4.11. G7 catches this.
- **R4.** If G8 (replaying the closure path) fails → ERROR, not FALLBACK. Implemented.
- **R5 (telemetry).** A complete unsolved dead end Y ≠ G, or a SOLVED witness at the same T as a certificate, refutes the theorem or the code. It must be raised as ERROR (proofs document §8.3).
- **R6.** Add regression tests to the repository (in the spirit of tests B and D′ here): random supersets X ⊒ G for complete G at T ∈ {12, 25, 32, 35}, with the assertion "every step's effects already hold in G".

## 6. Conclusion

The proofs in `PHASE7_1_STUCK_STATE_PROOFS.md` match the actual code of the detectors and the enumerator.
- I found no counterexample or defect, apart from the gap in the Grouped AIC walk lemma, which closes with Locked Candidates.
- **Using SSL at T=32: allowed.**
- **At T=35: allowed after condition C1** (amending the document). Any change to the audited sources requires a re-audit (G7).
