# Phase 7.1: Stuck-State Superset Lemma (SSL), proofs and guards

Role: Technical Planner (mathematical soundness). Status: analysis only. No product code under
`generator/`, `web/` or `data/` was changed. The scratch scripts used for the empirical check are
outside the repository.

**Revision 2 (2026-10-02, Phase 7.1 remediation after `docs/PHASE7_1_SSL_REVIEW.md`):**
- C1: §4.12 now closes the case where the walk-lemma contraction leaves an open chain
  with a single strong link (detector emits nothing for length < 3); closed via a
  bivalue-cell argument and Locked Candidates.
- §4.8: the case "t live and some node not live" is *impossible*, not merely harmless.
- §0: note that the Naked Single proof needs only NS; the implementation's extra HS
  dependency is a conservative fail-closed choice.
- §6: the pinned source set also includes `certification/models.py` and
  `solver/techniques/__init__.py` (review R1); §8.3 confluence alarm is implemented (R5).

Code basis: the snapshot of 2026-10-02 ~14:20. The detectors in `generator/solver/techniques/*.py`
are unchanged since 2026-09-27. `certification/enum_chains.py` and `certification/enumeration.py`
are the Phase 7.1 refactored versions; this document re-checks them and refers to their
line numbers. **Every proof below is about this code.** If any listed file changes, the proof
is void until someone re-audits it (guard G7).

## 0. Verdict

| Family (rating) | SSL proven? | Needs at G (all must be ≤ T) | Proof |
|---|---|---|---|
| Full House .5, Naked Single 1, Hidden Single 1.2 | **yes** | NS, HS (FH self-contained; the NS proof itself needs only NS, see note) | §4.1 |
| Locked Candidates 2 | **yes** | HS, LC | §4.2 |
| Naked Pair/Triple/Quad 3/5/7 | **yes** | NS, smaller naked subsets | §4.3 |
| Hidden Pair/Triple/Quad 3.2/5.2/7.2 | **yes** | HS, smaller hidden subsets | §4.4 |
| X-Wing/Swordfish/Jellyfish 8/12/18 | **yes** | HS, smaller fish | §4.5 |
| Skyscraper 9, 2-String Kite 9.2, Turbot Fish 10 | **yes** | HS, same family | §4.6 (CCL) |
| Empty Rectangle 11 | **yes** | HS, LC, ER | §4.9 |
| XY-Wing 14 | **yes** | NS, XY-Wing | §4.6 |
| XYZ-Wing 16 | **yes** | NS, Naked Pair, XY-Wing, XYZ-Wing | §4.10 |
| W-Wing 17 | **yes** | NS, HS, W-Wing | §4.6 |
| X-Chain 22, XY-Chain 25, AIC 30 (open) | **yes** | NS, HS, same family, *complete* enumeration at G | §4.6, §4.11 |
| AIC discontinuous loops (placement / elimination) | **yes** | NS, HS, AIC | §4.7 |
| Nice Loop 32 | **yes** | NS, HS, Nice Loop | §4.8 |
| Grouped AIC 35 (open + discontinuous loops) | **yes, only for T ≥ 35** (it requires AIC and LC at G) | NS, HS, LC, AIC, Grouped AIC | §4.12 |
| ALS-XZ 36, ALS-XY-Wing 39, ALS Chain 42 | **not proven** (not analysed). Moot in practice: `ALS_SIZE_LIMIT` fires whenever any unit has >5 empty cells (`enum_als.py:16-19`), so G is never complete | – | §5 |
| Forcing Chain 50 | **no**: a plausible counterexample mechanism, see §5 | – | §5 |
| Nishio 55 | not analysed | – | – |

Note (rev. 2): the Naked Single proof (§4.1) uses only F1/NS at G. The implementation
(`stuck_state.PROOF_DEPENDENCIES`) nevertheless requires HS whenever NS is enabled. This is a
deliberately conservative, fail-closed choice: SSL is simply not used for T ∈ [1, 1.2).

Result:
- **T = 32: SSL holds for every family with rating ≤ 32.**
- **T = 35: SSL holds for every family with rating ≤ 35**, including Grouped AIC.
- In general SSL holds for every T < 36 with the current registry ratings. For T ≥ 36 it is not available.

None of the proofs uses step soundness, the unique solution, or the exact solver. They are purely
combinatorial facts about the transition system that the code defines. The theorem is therefore
at least as strong as the current exhaustive-search claim.

## 1. Model and notation

A state S is a valid `SudokuState`: `grid[81]` and `candidates[81]`. A filled cell has mask 0.
`validate()` (`sudoku/candidates.py:46-65`) checks four things:
- no duplicate digit in a unit;
- every empty cell has a nonempty mask;
- the mask contains no digit placed in a peer;
- every unit, for every digit, has a placed cell or a candidate.

`place()` (`candidates.py:79-90`) has these side effects: it sets the cell, sets its mask to 0 and
clears the digit from all peers. `eliminate()` (`:92-100`) clears one bit. `apply_step`
(`solver/human_solver.py:12-27`) applies the placements, then the eliminations, then validates.
A transition exists only if this succeeds.

Possibility set: `L_S(c) = cand_S(c) ∪ {grid_S(c)}`. Each candidate (c,d) has one status in S:
- **P**: placed, `grid(c) = d`;
- **live**: d ∈ cand(c);
- **D**: dead, (c,d) ∉ L_S.

**Model at threshold T.** M_T(X) is the set of steps that `StepEnumerator.enumerate`
(`certification/enumeration.py:153-186`) would return at X with every operational limit removed.
That is the union of three sources:
- basic `find_steps` for every technique with `difficulty ≤ T` (`:158`, `:136-137`);
- `enumerate_chains` (`enum_chains.py:19-119`) with no length or work limit;
- ALS/forcing (not needed for T < 36).

Any step the limited production enumerator emits is in M_T. Proving "no M_T-path reaches a solved
state" therefore implies the current `PROVEN_UNSOLVABLE_WITHIN_MODEL` semantics. The proofs need
**no** validity of the step: they cover every emitted step whose application succeeds.

**Order.** `X ⊒ G` means that for every cell c:
- if `grid_G(c) = 0`, then `grid_X(c) = 0` and `cand_G(c) ⊆ cand_X(c)`;
- if `grid_G(c) = d`, then `grid_X(c) = d`, or `grid_X(c) = 0` and `d ∈ cand_X(c)`.

Equivalently: `L_G(c) ⊆ L_X(c)` for every c, and every cell empty in G is empty in X.

Check (bit operations, O(81)):
```
for c in 0..80:
    lg = G.cand[c] | (bit(G.grid[c]) if G.grid[c] else 0)
    lx = X.cand[c] | (bit(X.grid[c]) if X.grid[c] else 0)
    require lg & ~lx == 0
    require not (G.grid[c] == 0 and X.grid[c] != 0)
```

Basic consequences for valid X ⊒ G:
- **O1** `supports_G(U,d) ⊆ supports_X(U,d)`. Here `supports(U,d)` means the cells of U where d is a candidate.
- **O2** If X has d placed at c, G has d placed at c (G-empty ⇒ X-empty, and `L_X(c) = {d}`).
- **O3** If d is not placed in U in X and G places d in U at p, then p ∈ supports_X(U,d).
- **O4** A conflict relation is purely geometric: "same cell, different digit" or "peer, same digit". It holds in G whenever it holds in X.

**G is stuck and complete at T**: `enumerate(G,T)` returns `steps == []` and `limit_reasons == []`.
This gives:
- **F1** Every empty cell of G has ≥ 2 candidates (else `NakedSingle.find_steps`, `singles.py:32-36`, emits).
- **F2** For every unit U and digit d not placed in U, `|supports_G(U,d)| ≥ 2`. Validity gives ≥ 1; `HiddenSingle`, `singles.py:43-54`, excludes exactly 1.
- **F3** (T ≥ 2) No Locked Candidates elimination exists.
- **SL (strong-link status).** Take a strong link between singletons A=B in X. Two kinds exist:
  - a bivalue cell: `cand_X(c) = {a,b}`;
  - a unit conjugate: `supports_X(U,d) = {A,B}`.

  In G, exactly one of these holds:
  - both A and B are live, and the link still exists in G;
  - one is P and the other is D.

  *Proof.* Cell link: `L_G(c) ⊆ {a,b}` and is nonempty. If only one is in `L_G` and the cell is empty, that is a naked single (F1). If the cell is placed, the other digit is D.
  Unit link: by O3 a placement of d in U is at A or B, and it kills the other (peer). Otherwise `supports_G ⊆ {A,B}`, which is nonempty (validity) and not of size 1 (F2), so it equals {A,B} and the conjugate persists. ∎
- **WL (weak link).** If A, B conflict and A is P, then B is D. This follows directly from validity.

Rule summary: across a strong link, D ⇒ P, P ⇒ D, and "not both D". Across a weak link, P ⇒ D.

## 2. Theorem (SSL ⇒ unsolvability)

**Hypotheses.**
- H1: G is a valid `SudokuState`.
- H2: root ⊒ G, checked directly.
- H3: `enumerate(G,T)` returns complete with zero steps.
- H4: G is not solved.
- H5: every technique with `difficulty ≤ T` has SSL proven, and its G-dependencies are ≤ T. This holds for T < 36 with the registry ratings (`rating/registry.py:57-70`).

**SSL(F)**: for every valid X ⊒ G and every step s ∈ M_T(X) of family F:
- every elimination (c,d) of s is D in G;
- every placement (c,d) of s is P in G.

**Claim.** No M_T-path from the root reaches a solved state.

*Proof.* By induction on path length, every reachable state X is valid and X ⊒ G.

Base case: H2.

Step: let X ⊒ G, let s ∈ M_T(X), and let X' = apply_step(X,s) succeed (X' is valid). Take any cell c.
1. **Placement (c,d) of s.** G has d placed at c (SSL). Then `grid_X'(c) = d` satisfies the order at c.
   - Side effect on the cell's own candidates: `cand_X'(c) = 0`. This is harmless because `L_G(c) = {d}`.
   - Side effect on peers: X' clears d at every peer p. G has no d at any peer p, because a placed d excludes d from peers' masks and grids (`validate`). So `L_G(p) ⊆ L_X'(p)` is preserved.
   - Empty cells of G stay empty in X', because placements only hit cells placed in G.
2. **Elimination (c,d) of s.** (c,d) ∉ L_G, so removing it from `L_X` keeps `L_G(c) ⊆ L_X'(c)`.
   - `apply_step` applies placements before eliminations. An elimination already cleared by a placement is a no-op bit-clear.
   - Validation forbids an elimination on a cell placed by the same step (`proofs.py:456`). That check is not even needed here.
3. All other cells are unchanged.

So X' ⊒ G.

Finally, if X is solved, every cell is placed. X ⊒ G forbids X-placed cells that are empty in G, so G would be solved, contradicting H4. ∎

**Notes.**
- The path from the root to G is logically irrelevant. Only H2 matters, so intermediate limit hits while computing G are harmless.
- **Corollary (confluence).** Let Y be any reachable state that is stuck and complete. Then every reachable state satisfies X ⊒ Y, and also G ⊒ Y. If G is also stuck and complete, the same argument gives Y ⊒ G, so Y = G (⊒ is antisymmetric). So at a threshold where enumeration is complete, the terminal state is unique and independent of order. **Any** dead end the search hits with a complete enumeration is already a certificate of unsolvability.
- **Monotonicity in T.** M_{T'} ⊆ M_T for T' ≤ T. A certificate at T therefore covers every lower T.

## 3. Proof schema for every family

Fix a valid X ⊒ G with G stuck and complete, and a step s ∈ M_T(X). Suppose an effect violates SSL:
- an elimination (t,d) that is not D in G (so it is P or live in G); or
- a placement (c,d) that is not P in G.

Each proof derives one of two outcomes:
- (i) G is invalid, which contradicts H1; or
- (ii) some detector with rating ≤ T emits a step at G (valid or not, since the enumerator does not validate), which contradicts H3.

## 4. Proofs per family

### 4.1 Singles (`singles.py`)

**Naked Single at X**, `cand_X(c) = {d}`.
- If c is empty in G: `∅ ≠ cand_G(c) ⊆ {d}` is a naked single at G. Contradiction (ii).
- So c is placed in G with e ∈ `L_X(c) = {d}`, i.e. P. ✓

**Hidden Single at X**, `supports_X(U,d) = {c}` and d is not placed in U in X.
- If G places d in U, then by O3 it does so at c (P ✓).
- Otherwise `supports_G(U,d) = {c}` (validity), which is a hidden single at G. Contradiction.

**Full House at X.** This is a special case of a hidden single in X: the other cells of U are placed and keep their values in G (O2), so G either has c placed with d or a Full House or Hidden Single at c.

### 4.2 Locked Candidates (`locked_candidates.py:13-36`)

At X: source S, digit d, `cells = supports_X(S,d)`, `|cells| ≥ 2` (`:20`), cells ⊆ V; targets (x,d) with x ∈ V∖S.

Suppose (x,d) ∈ L_G.
- If d is placed in S in G at p: then p ∈ cells ⊆ V (O3), and x ∈ V is a peer of p. So x is neither P nor live. Contradiction.
- Otherwise `supports_G(S,d) ⊆ cells ⊆ V`.
  - If x is P: every support is a peer of x in V, so it dies; S then has no d, which is invalid.
  - If x is live: by F2 `|supports_G(S,d)| ≥ 2`, all in V. The same LC (same source and target) eliminates (x,d) at G. Contradiction (ii).

### 4.3 Naked subsets (`subsets.py:11-34`)

**Hall lemma (naked).** In a stuck G, no set Q of ≤ 4 empty cells in one unit has `|∪cand(Q)| < |Q|`.

*Proof.* Take a minimal violator Q. By F1, |Q| ≥ 3. For q ∈ Q, minimality gives `∪cand(Q∖q) = ∪cand(Q)` of size |Q|−1. So Q∖q is a naked (|Q|−1)-subset: eligibility `2 ≤ cnt ≤ size` (`:17`) and `mask == size` (`:22`) both hold. It eliminates its digits from q, a nonempty set. So the Naked Pair or Triple detector emits. ∎

**The step.** At X: unit U, cells C with |C| = k and `|M| = k` where `M = ∪cand_X(C)`. Targets are (x,e) with x ∈ U∖C and e ∈ M.

In G, split C:
- C_P = cells of C that are placed in G. Their digits are in M (O2/O3) and distinct, forming M_P.
- C_E = the other cells. They have `cand_G ⊆ M∖M_P`, and `|M∖M_P| = |C_E| = j`. By the Hall lemma the union is exactly M∖M_P. By F1, j ≠ 1.

Suppose (x,e) ∈ L_G.
- e ∈ M_P: d=e is placed in U and x ∈ U, so x cannot hold e. Contradiction.
- e ∈ M∖M_P and x is P with e: C_E loses e, a Hall violation. Contradiction.
- e ∈ M∖M_P and x is live with e: C_E is a naked j-subset at G with j ≤ k. It eliminates (x,e) (ii).

The rating of a naked j-subset is ≤ the rating of a naked k-subset.

### 4.4 Hidden subsets (`subsets.py:37-59`)

This is dual to §4.3, with the roles of cells and digits swapped.

**Hall lemma (hidden).** Take a minimal set Q of unplaced digits in U with `|∪supports(Q)| < |Q|`. By F2, |Q| ≥ 3. Then Q∖q is a hidden (|Q|−1)-subset: eligibility `1 ≤ len ≤ size` (`:45`) and `len(cells) == size` (`:48`). Digit q lives in its cells and is eliminated (ii).

**The step.** At X: digits D_k and cells C = ∪supports_X(D_k), |C| = k. Targets are (c,e) with c ∈ C and e ∉ D_k.

In G, split the digits:
- D_P = digits placed in U. Each is at a cell of C (O3), giving C_P.
- D_E = the others. Their supports lie in C∖C_P, which has size j. By the Hall lemma the supports equal C∖C_P.

Suppose (c,e) ∈ L_G.
- c ∈ C_P: `L_G(c)` is a digit of D_k, so e ∉ L_G(c). Contradiction.
- c ∈ C∖C_P and c is P with e: D_E loses c, a Hall violation. Contradiction.
- c ∈ C∖C_P and e is live at c: D_E is a hidden j-subset at G that eliminates (c,e) (ii). It has j ≥ 2.

### 4.5 Fish (`fish.py:13-40`)

At X: digit d and base lines B with |B| = k. Each base has 2..k supports (`:21`). The covers K are the union of positions, |K| = k (`:24`). Targets are (x,d) with x in a cover line outside the bases.

In G, split the bases:
- B_P = bases where d is placed (at cells in cover lines, by O3). They give distinct cover lines K_P.
- B_E = the rest. Their supports lie in covers K∖K_P (cover lines in K_P are killed). Each has ≥ 2 supports (F2), and j = |B_E| = |K∖K_P|.

**Hall lemma (fish).** A minimal violator Q ⊆ B_E has |Q| ≥ 3. Q∖q is a smaller fish whose covers contain line q's supports, so it eliminates them (ii). Therefore the positions of B_E are exactly K∖K_P.

Suppose (x,d) ∈ L_G, with x in cover line κ.
- κ ∈ K_P: x is a peer of the placed d in κ (x is not in a base). Contradiction.
- κ ∉ K_P and x is P: cover κ dies for B_E, a Hall violation. Contradiction.
- κ ∉ K_P and x is live: the fish (B_E, K∖K_P) of size j ≤ k eliminates (x,d) at G (ii).

### 4.6 Chain Collapse Lemma (CCL): singleton alternating chains

**Lemma.** Let A1..An be distinct singleton candidates in X:
- n is even;
- the link (A_i, A_{i+1}) is strong (cell- or unit-type, as in SL) for odd i and weak (conflict) for even i;
- t is a singleton target that conflicts with A1 and An and is not on the chain.

Then in G:
- (a) t is not P;
- (b) if t is live, every A_i is live and every link persists in G with the same type.

*Proof.*
(a) If t is P, then A1 and An are D (WL). Propagation then runs: A1 D ⇒ A2 P ⇒ A3 D ⇒ … ⇒ An P. This contradicts An being D.

(b) Let t be live.
- A1 is not P (else t would be D by WL). If A1 is D, propagation gives An P, so t would be D. So A1 is live, and symmetrically An is live.
- Suppose an internal A_i is P.
  - If i is even: going forward (weak, then strong, …) gives A_{i+1} D, A_{i+2} P, …, An P. Contradiction.
  - If i is odd: going backward gives A_{i−1} D, A_{i−2} P, …, A1 P. Contradiction.
- An internal D node has a P strong partner (SL), which the previous point excludes.

So all nodes are live. SL then gives persistence of the strong links, and O4 gives persistence of the weak links. ∎

**Applications.** In each case the pattern is the same chain at G, the target is still live, and the same detector emits it at G.

| Family | Chain | Why the detector emits at G |
|---|---|---|
| Skyscraper / Kite / Turbot (`single_digit_patterns.py:11-75`) | outer_a = inner_a – inner_b = outer_b, with unit conjugates | `_links` finds the same conjugate pairs (same unit indices). `accepts` is purely geometric (`:22,60,72`). The 4-cell (`:30`) and peer (`:35`) checks are unchanged. |
| XY-Wing (`wings.py:12-45`) | (w1,z)=(w1,x)−(p,x)=(p,y)−(w2,y)=(w2,z), cell links | All three cells have the same bivalue masks in G, so every mask condition (`:19,22,28`) is identical. |
| W-Wing (`wings.py:79-130`) | (f,b)=(f,a)−(s1,a)=(s2,a)−(s,a)=(s,b) | Same bivalue mask pair. The bridge still has exactly two supports (`:94`). Non-peer (`:98`) and `first in supports` (`:108`) are geometric. |
| X-Chain / XY-Chain / open AIC | the chain itself | See §4.11 for completeness. The xy-mode graph keeps the nodes because the cells stay bivalue (`chains.py:54-55`). XY targets are computed from geometry and the live target (`enum_chains.py:92-96`). |

### 4.7 AIC discontinuous loops (`enum_chains.py:77-83`)

The loop starts and ends at a singleton A1. Its first and last links have the same kind, it has m links (m odd, m ≥ 3), and every internal node has exactly one strong and one weak link.

**Strong case (placement of A1).**
- If A1 is P in G: ✓ (allowed).
- If A1 is D: the run is A2 P, A3 D, …, A_m D. Then the closing strong link A_m = A1 has both ends D, which contradicts SL.
- If A1 is live and some internal node is not live: there is a P internal node (a D node has a P strong partner). From it, propagate along its weak link: D, then via strong P, and so on. A1 is entered via a strong link from a D node, so A1 is P. Contradiction.
- If all nodes are live: the same loop exists at G and is emitted (ii).

**Weak case (elimination of A1).**
- If A1 is P: its neighbours are D, then P, …. The run ends with A_m P, which contradicts A_m being D.
- If A1 is live and an internal node is P: the propagation enters A1 via a weak link from a P node, so A1 is D. Contradiction.
- If all nodes are live: the loop is emitted at G.
- If A1 is D: ✓.

### 4.8 Nice Loop (`enum_chains.py:98-117`)

The cycle is S W … S W, of even length; every node has exactly one S and one W link. The targets are the singletons that conflict with both ends of some weak edge (x,y) (`:108-114`).

- **t is P:** x and y are D. From x, propagation along its strong link alternates D, P, … around the cycle. Because the cycle length is even, y would come out P. Contradiction.
- **t is live and all nodes are live:** the same loop exists at G and is emitted (ii).
- **t is live and some node is not live:** there is a P node. Propagating from it along its weak edge covers the **whole** cycle with an alternating P/D pattern; this is consistent for an even S/W cycle. So every weak edge has a P end, and t, which conflicts with it, is D. This contradicts the case assumption "t is live", so the case is **impossible** (rev. 2; earlier text said "harmless").

### 4.9 Empty Rectangle (`single_digit_patterns.py:87-136`)

At X: box β; positions ⊆ row R ∪ column Cc; near n (in row R, outside β); conjugate pair {n,f} in column(n); target t = (row(f), Cc). This is the row orientation; the column orientation is symmetric.

Geometry:
- f is outside β and is not n.
- t ≠ f, and t is outside β (`:125`).
- t and f share a row.

Cases:
- **t is P:**
  - f is D, so n is P (SL).
  - β's cells in row R die (peers of n) and β's cells in column Cc die (peers of t).
  - A d placed in β is impossible: it would sit in row R or column Cc, next to n or t.
  - So β has no d, and G is invalid.
- **t is live, f is P:** t is D (same row). Contradiction.
- **t is live, f is D, n is P:**
  - A placement in β is impossible: in row R it conflicts with n; in column Cc it kills t.
  - So `supports_G(β,d) ⊆ (cells of column Cc in β)`, with ≥ 2 cells (F2).
  - Then LC pointing (β → column Cc) eliminates (t,d) (ii).
- **t is live, n and f are live:**
  - The conjugate {n,f} persists.
  - There is no placement in β (it would kill n or t).
  - `positions_G` has ≥ 2 cells (F2), all in R ∪ Cc.
  - If all positions are in R: LC eliminates (n,d).
  - If all positions are in Cc: LC eliminates (t,d).
  - Otherwise the ER conditions at G are satisfied for the same (R, Cc, n). The checks at `:104`, `:110`, `:121` and `:125` all hold, so ER eliminates (t,d) (ii).

### 4.10 XYZ-Wing (`wings.py:47-76`)

At X: pivot p = {x,y,z}, wings w1 = {x,z} and w2 = {y,z} (peers of p). Targets are (t,z) with t a peer of p, w1 and w2.

**Helper fact.** If two cells a and b are peers, every cell that sees both lies in a unit containing both a and b.

**In G:** each wing is either the same bivalue cell or placed. Placing z in a wing is impossible because it kills t.

Cases:
- **t is P:** w1 is placed with x and w2 with y, so p has `L_G(p) ⊆ {x,y,z}` minus x, y, z. That is empty, so G is invalid.
- **t is live, both wings placed:** p is left with ⊆ {z}. This is either a naked single or p placed with z, which kills t. Contradiction.
- **t is live, w1 placed with x, w2 live:**
  - p ⊆ {y,z}, and p has ≥ 2 candidates or is placed.
  - Placed with y makes w2 a naked single; placed with z kills t.
  - So p = {y,z}, which forms a Naked Pair with w2 in a unit that contains t (helper fact). It eliminates (t,z) (ii).
  - The case with w2 placed is symmetric.
- **t is live, both wings live:**
  - p is placed: with z, t dies; with x or y, a wing becomes a naked single.
  - `cand_G(p) = {x,y,z}`: the same XYZ-Wing.
  - `cand_G(p) = {x,z}` or `{y,z}`: a Naked Pair with a wing in a unit containing t.
  - `cand_G(p) = {x,y}`: an XY-Wing (pivot p; the checks at `wings.py:19,22,28` hold) eliminates (t,z), since t ≠ p and t sees both wings.

  So this family needs NS, NP and XY-Wing ≤ T (T ≥ 16 ✓).

### 4.11 Completeness of chain enumeration at G (all chain families)

`enum_chains.py` in its current version (re-checked after the Coder's refactor):
- The DFS has no `seen` pruning. It covers every simple path for each start and each allowed first kind: `("strong","weak")` for open-AIC mode, `("strong",)` otherwise (`:51-56`).
- `nxt in path and nxt != start` (`:71`) is the only pruning.
- Every attempt to go beyond `max_chain_length`, including a return to the start, records `CHAIN_LENGTH_LIMIT` (`:73-75`).
- A Nice-loop closure is checked separately (`:99-100`).
- The work limit records `CHAIN_NODE_LIMIT` (`:68-70`).
- Time records `TIME_LIMIT` (`:58-60`, enumeration `:160-162`, `:182-183`).

**Consequence.** If the enumeration at G is complete, then:
- every alternating simple path in G's graph has length ≤ max_chain_length; otherwise its prefix of length max would have been explored and the extension attempt flagged;
- every path that can be emitted was explored.

So a chain from X, of any length (the model is unbounded), whose G-image is a valid chain, is **emitted** at G. The operational limits therefore cannot hide an instance at G, and they never need to be part of the model.

### 4.12 Grouped AIC (T ≥ 35)

**Nodes** (`chains.py:43-53`). A group node is the set of **all** supports of a digit in a box∩line intersection I with ≥ 2 cells. Weak links are all-to-all conflicts (`:23-28`, `:70-73`). Strong partition links split all supports of a unit into a ⊔ b, where b must be an existing node (`:88-93`).

**Status of a node N = (C, d) in G:**
- P: some cell of C has d placed;
- D: no cell of C has d in L_G;
- live: otherwise. A live node may additionally be L*: its live cells are **all** G-supports of d in some unit, and there are ≥ 2 of them. A singleton cannot be L* (that would be a hidden single).

Let T* mean "P or L*".

**Rules.**
- **R1 (strong).** Not both ends D. If one end is D, the other is T*. (This uses validity and F2; for a partition, a placement in U lies in a or b by O3.)
- **R2 (weak / conflict).** If a node is T*, every node or target that conflicts with it is D.
  - For P this is WL.
  - For L*: live(b) = supports_G(U,d) ⊆ I_b, and U is the box or the line of I_b. A conflicting node c has the same digit and lies in the other unit V of I_b, outside U. If it lay in U, it would be one of b's supports, which contradicts disjointness. So **LC** (source U, target V) eliminates every live cell of c (ii); and c cannot be P either.

The arguments of §4.6 and §4.7 only use "D ⇒ T* across strong", "T* ⇒ D across weak or conflict", "not both D" and "T* and D are exclusive". So they apply unchanged:
- either SSL holds;
- or G is contradictory;
- or **all nodes are plain-live**.

**Projection when all nodes are plain-live.** Map N to N_G = (live cells, d). For a group this equals supports_G(I,d), so N_G is a valid G-node (single or group). Strong partitions persist: `supports_G(U,d) = a_G ⊔ b_G`, `a_G ⊊ support`, and b_G is in the index. Weak links persist by O4.

Two quirks remain:
1. **Distinct X-nodes can have the same G-image.** This only happens for singletons. Two G-groups would both lie in I1 ∩ I2, which has at most 1 cell. Adjacent nodes always have different images.
   **Walk lemma.** Choose a repetition (i,j) with minimal j−i.
   - If j−i is odd, there is a simple discontinuous loop of length ≥ 3 at a singleton. AIC (no group) or Grouped AIC emits it (`:77-83`, `start_single`) (ii).
   - If j−i is even, cut out the segment. Alternation, endpoints and the kinds of the first and last links are preserved. Repeat until no repetition is left.
2. **The target t can be the image of an internal group** (the X-target was not on the path, but its G-image now is: t = A_k).
   - If k is even: the loop t = A_k … An − t has weak links at both ends.
   - If k is odd: the loop t − A1 = … A_{k−1} − t has weak links at both ends.

   Either way this is a discontinuous loop of length ≥ 3 that eliminates t at G (ii). Note that k ≠ 1 and k ≠ n, because a conflict excludes sharing a cell.

**After both repairs** the result is either a simple Grouped AIC chain or loop at G with t as a target, or, if no groups remain, a simple **AIC** chain or loop at G. The emit filter is `grouped and not groups` (`enum_chains.py:41-42`). By §4.11 the right enumerator emits it.

**Contraction to a single link (rev. 2, closes review gap §3.2).** The even repair preserves the
kinds of the end links, but for an **open** chain it can leave a single strong link B_0 = B_1
(example: A1 (singleton s) = A2 − A3 (a group whose G-image is s) = A4 reduces to s = B_3). The
enumerator emits no chain with fewer than 3 nodes (`enum_chains.py:85`), so this case needs its own
argument. Both ends are plain-live singletons (or group images), t is live and conflicts with both.
- **Cell-bivalue link** {(c,a),(c,b)}: a target conflicting with both ends would be either in cell c
  with a third digit (not live, because c is bivalue in G) or would need digit = a and digit = b at once.
  So no live target exists, contradicting the case assumption.
- **Partition / conjugate link in unit U** for digit d (both ends plain-live, so d is not placed in U,
  and `supports_G(U,d) = a_G ⊔ b_G`):
  - t has digit d and t ∉ U (otherwise t would be a support and would share a cell with a or b, which a
    conflict excludes);
  - t sees every support of d in U, so all of them lie in U ∩ V, where V is box(t) if U is a line, or the
    row/column of t if U is a box (for t outside a box, its row and column cannot both cross the box);
  - therefore **Locked Candidates** (source U, target V; ≥ 2 supports by F2) eliminates (t,d) at G (ii).
    LC (2) ≤ 35 is already a Grouped AIC dependency.

With this case the Grouped AIC proof is complete.

**Requirements:** Grouped AIC needs AIC (30) and LC (2) at G, i.e. T ≥ 35. That is the only T at which it occurs.

## 5. Families ≥ 36 (not proven)

**ALS-XZ / ALS-XY-Wing / ALS Chain.** Not analysed. Two problems:
- An ALS in which one cell is placed in G has degenerate forms whose RCC conditions change.
- Practically, `enumerate_als(state, 8)` against `max_als_size = 4` sets `ALS_SIZE_LIMIT` in almost every state (profile: 100% of enumerations at T ≥ 36). So H3 never holds anyway.

**Forcing Chain.** Plausibly **false**. `enum_forcing.py` emits only when **neither** branch contradicts (`not any(p.contradiction ...)`). G has fewer candidates, so propagation from the same assumption derives more facts and can reach a contradiction. A step at X (both branches consistent) then has no Forcing-Chain counterpart at the same start in G; only Nishio (55 > 50) would cover it. This emission condition is not monotone, so SSL is not available at T = 50 without a new proof.

There are also the start limit (`FORCING_START_LIMIT` above 160 candidates) and the depth limit.

**Guard:** use SSL only for T < 36.

## 6. Runtime guards for an implementation (e.g. `transitions.negative_certificate`)

Each guard must hold, otherwise **no** SSL claim is made and the search falls back to the exhaustive search.

- **G1** `G.validate()` passes (fresh object).
- **G2** root ⊒ G, checked directly with the bitmask test in §1. Do not rely on the path to G.
- **G3** G is not solved. If it is solved, it is a positive witness: validate the path with `validate_path`.
- **G4** Run a **fresh** `StepEnumerator(config, cache=False)` (no cross-state cache) for the same T. Check that the result has `complete is True`, `limit_reasons == []` and `steps == []`, read directly from `enumerate`. Do not use filtered or validated or `canonical_effects` transitions. The Hall arguments rely on the raw detectors emitting even inapplicable steps; a provider that drops inapplicable steps could hide them. Any `TIME_LIMIT` makes the check fail.
- **G5** Technique set: `{t : t.difficulty ≤ T} ⊆ PROVEN = {Full House … Grouped AIC}`, i.e. T < 36.
  - The ratings must equal the audited table (`rating/registry.py:57-70`), with no custom weights. The `difficulty` of each instance must equal the registry rating.
  - Assert the dependencies explicitly: rating(NS), rating(HS) ≤ every family; rating(LC) ≤ ER and Grouped AIC; NP and XY-Wing ≤ XYZ-Wing; AIC ≤ Grouped AIC; smaller subsets and fish ≤ larger ones.
- **G6** The technique classes are exactly `default_techniques` (`solver/techniques/__init__.py`), with the same modes and flags.
- **G7** Code fingerprint: a SHA-256 of the audited sources must match. A change means fail closed. The sources are:
  - `sudoku/candidates.py`, `sudoku/grid.py`;
  - `solver/techniques/{singles,locked_candidates,subsets,fish,single_digit_patterns,wings,chains,base}.py`;
  - `certification/{enumeration,enum_chains}.py`;
  - `solver/human_solver.py` (`apply_step`), plus the fast `child()` in `transitions.py` if the search uses it.
- **G8** (diagnostic only, recommended) Replay the path from the root to G with `validate_step`. Also check that the fresh solution S lies in L_G. A failure points to an unsound detector and should give ERROR. Neither check is a premise of the proof.
- **G9** Report it as a distinct form of evidence: `PROVEN_UNSOLVABLE_WITHIN_MODEL` with `negativeEvidence = "SSL-v1"`, the signature of G, the enumeration work at G, the fingerprint, and the T it applies to (it also covers every T' ≤ T).

**Semantic note.** The exhaustive search raises ERROR when an *unvisited* state produces a step that fails validation. SSL does not visit those states, so that defensive check is lost. It is not part of the model (the theorem covers all emitted steps), but you should state it explicitly in CERTIFICATION_SPEC. The model is not weakened: M_T is the unbounded model, a superset of the limited transitions.

**Consequence for the search (from the corollary).** The search can apply the SSL check at every dead end with a complete enumeration. One such dead end is enough for the negative proof.

## 7. Detector quirks checked

- **Representative or early exits:** basic `find_steps` loop over all combinations, with no early exit. `unique_steps` deduplicates only by effect, which is harmless because existence is all that matters. The legacy `_GraphTechnique.find_steps` (BFS with `seen` and budget early exit) is **not** used by certification. That matters, because it would break §4.11.
- **Exact-count conditions** (naked `2 ≤ cnt ≤ size`, `mask == size`; hidden `1 ≤ len ≤ size`; fish `2..size`; ER `len(pair) == 2`; XY/XYZ/W bivalue and trivalue): all handled. In G the degenerate cases always become a single, an LC, a smaller subset or fish, a Naked Pair, or an XY-Wing.
- **Suppression by a cheaper technique with the same effect:** not present in `enumerate` (`canonical_steps` keys on the rating).
- **Cache** (`EnumerationCache`, `enumeration.py:81-120`): it is keyed by the full signature and the technique, and results that hit TIME_LIMIT are not stored. It is correct, but for the certificate use `cache=False` (G4).
- **The Coder's refactor of `enum_chains.py`** (link objects only on emit, shared graph): it visits the same edges in the same order with the same flags. I re-checked against §4.11 and found no change relevant to the proof.
- **The Coder's `transitions.py`** contains the hook `negative_certificate` (currently always None). That is the natural place for SSL.

## 8. Empirical cross-check

### Done (scratch scripts, no repository changes)

| Run | Checked | Result |
|---|---|---|
| 8e2b at T=32 | G computed by greedy closure; 6 random walks; 342 states | G has 125 candidates, complete, unsolved, root ⊒ G, solution ∈ L_G. Over 13,008 enumerated steps: every state ⊒ G, **0 SSL violations**, every walk ends exactly at G. |
| Sweep: 9 puzzles from `PHASE7_EXPERIMENT_INPUT.json` × T ∈ {8, 12, 18, 25, 30, 32, 35} × 4 walks | 44 (puzzle, T) pairs with complete and unsolved G | **0 violations; 176/176 walk terminals equal G.** Families covered: all basic ones, X-Chain, XY-Chain, AIC, Nice Loop. |

The sweep skipped 18 pairs because G was incomplete, and 1 pair because G was solved.

In the sweep:
- At T = 30/32, G was complete for 4 puzzles (8e2b and bcf460 among them). For **bcf460 at T=32**, SSL would immediately give PROVEN_UNSOLVABLE.
- At T = 35, G was incomplete or solved in every case, so **Grouped AIC is not covered empirically.**

### Proposed for implementation and review

1. **SSL invariant in tests.**
   - Random walks from the root over many puzzles and every T < 36 where G is complete.
   - At every state, assert X ⊒ G and that every enumerated step satisfies SSL.
   - Also use raised limits (chain length 40, work 10^7) to approximate the unbounded model.
2. **SSL vs. exhaustive search on small lattices.**
   - Choose T and starting states where `threshold_search` exhausts the whole graph: T ≤ 1.2 (singles, 3,236 states for 8e2b), T = 2/3, and mid-path states with few candidates.
   - The verdicts must agree.
   - Every reachable state must be ⊒ G.
   - There must be exactly one terminal state with a complete enumeration.
3. **Confluence alarm in production telemetry.** Seeing a complete dead end Y ≠ G, or a complete unsolved dead end together with a SOLVED path at the same T, refutes the theorem or the code. Treat it as a hard ERROR.
4. **Hand-built tests for the degenerate cases.** Construct pairs (X, G) by hand:
   - XYZ → XY-Wing;
   - ER → LC;
   - Nice Loop with a P/D cycle;
   - Grouped AIC whose group collapses to the target or to a repeated singleton;
   - Hall violations for subsets and fish.

   For each, assert the local lemma: "if the step at X violates SSL with respect to G, then enumerate(G) is nonempty or G is invalid". This lemma does not need G to be stuck, so it can also be checked in bulk on random pairs (X, G' = X after k random steps).
5. **Grouped AIC coverage.** Search for puzzles or states where G at T=35 is complete. For example, start from late states on the human path, where `CHAIN_NODE_LIMIT` does not fire. Run tests 1 and 4 there.
