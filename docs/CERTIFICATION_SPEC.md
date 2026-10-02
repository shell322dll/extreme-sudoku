# Phase 7: independent certification contract

Certification version: `1`. Python API: `generator.certification`.
This document defines the production boundary; the Phase 1–6 reports describe
historical preliminary rating. Existing numeric ratings remain unchanged:
AIC=30, ALS-XZ=36, Forcing Chain=50, Nishio=55. These are internal ratings,
not Sudoku Explainer ratings.

## Status and evidence

`REJECTED` means a concrete acceptance requirement failed. `UNRATED` and
`PRELIMINARY` cannot enter production. `SEARCH_INCONCLUSIVE` means the required
negative evidence is incomplete; `CERTIFICATION_TIMEOUT` identifies an expired
deadline. `INVALID_PROOF` rejects a logical witness. Only `CERTIFIED_EXTREME`
and `CERTIFIED_ULTRA_EXTREME`, with all validation gates satisfied, are eligible.

Each threshold has a separate result:

| Status | Meaning |
|---|---|
| `SOLVED` | A independently validated logical witness reaches a completed grid. |
| `PROVEN_UNSOLVABLE_WITHIN_MODEL` | Either the entire reachable transition graph at this ceiling was exhausted without a solution and without omitted work (`negative_proof_kind = "EXHAUSTIVE_SEARCH"`), or an independently checked Stuck-State Superset Lemma certificate holds (`negative_proof_kind = "STUCK_STATE_SUPERSET_LEMMA"`, see below). |
| `INCONCLUSIVE_BUDGET` | A time, node, state, depth, alternative-step, chain, ALS or forcing limit omitted work. |
| `ERROR` | A malformed or invalid deduction or other search error occurred. |

An unfinished negative search is never converted into proof of difficulty.
A solved witness remains a valid upper bound even when other transitions have
not been enumerated. A certified minimum requires conclusive failure immediately
below a solved witness: fixed nested transition sets then exclude every smaller
threshold too. The result certifies a difficulty level;
it does not establish that a specific named technique is mandatory.

## Fresh mathematical validation and human replay

Each invocation starts with new states and caches. The pipeline checks the
81-digit puzzle and optional solution, Sudoku consistency, givens agreement,
fresh `count_solutions(limit=2) == 1`, and actual clue count. It tests removal
of every remaining clue to establish minimality. Minimality means no individual
clue can be removed while preserving uniqueness; it does not mean minimum clues.

The Human Solver runs from scratch, with deterministic replay and independent
step checking. Exact Solver is confined to mathematical validation. It is not
called by logical search or proof verification, and the known solution does
not choose logical deductions. Legacy saved labels, fitness, uniqueness flags,
minimality flags and certification metadata are never trusted as fresh evidence.

## Independent proof validation

`certification/proofs.py` checks the supplied premises and effects directly.
It never calls a detector to reconstruct a matching step. Every placement and
elimination must refer to a live legal candidate, avoid givens, make progress,
and leave a locally consistent state. Technique names and ratings must agree
with the registry.

Independent validators cover the implemented singles, intersections, subsets,
fish, wings and single-digit patterns, plus:

- Candidate chains: live nodes, legal strong/weak links, alternation, node
  repetition rules, endpoint visibility, continuous and discontinuous loops.
- Grouped AIC: legal intersection groups, OR-node membership, exhaustive unit
  partitions for strong links and pairwise conflicts for weak links.
- ALS-XZ, ALS-XY-Wing and ALS Chain: N cells with N+1 candidates, unit membership,
  disjointness, RCC visibility, differing adjacent RCCs and endpoint exclusions.
- Forcing Chain and Nishio: one candidate assumption per branch, explicit
  exactly-one-clause propagation, dependency structure and valid shared
  conclusion or contradiction. Recursive digit guessing is not permitted.

Unsupported proof forms fail closed. Passing a witness check establishes its
local logical validity; it does not establish that all cheaper moves were found.
That separate obligation belongs to search completeness tracking.

## Alternative-path algorithm and scope

Starting with the independently validated Human Solver path as an upper bound,
the search tries the next lower registry rating ceiling. A cheaper solution
becomes the new upper witness; conclusive failure proves the current witness
minimum. Inconclusive failure does not establish that minimum. The search
explores legal LogicStep transitions. States include both all placed values
and all candidate masks.
Deduplication happens at two levels. The enumerator keeps one canonical proof
per (effects, rating) (`canonical_steps`), so equal effects of techniques with
different ratings both survive enumeration (bottleneck evidence and
`ALTERNATIVE_STEP_LIMIT` depend on this). The search then groups steps by the
**signature of the successor state**, across ratings, and keeps only the
cheapest proof (rating, step key, full JSON) per distinct successor; distinct
successor states are never merged.

Within one ceiling the verdict depends only on reachability, so each state
signature is expanded at most once (plain visited semantics); a lower max rating
so far never re-opens a state, because the descent lowers the ceiling itself.
The single exception is the depth rule: when the depth limit can bind
(`depth_bound(root) ≥ max_path_depth`), a strictly shallower arrival re-opens a
state, since it leaves more remaining depth. For Sudoku states every step
removes at least one live candidate, so when the live-candidate count is below
`max_path_depth` the depth limit cannot bind and visited semantics is exact.
Candidate-count progress and secondary path costs order the frontier
deterministically (the first arrival of a state supplies its witness prefix);
they do not discard distinct alternative states. Secondary costs are not claimed
to be optimal. The primary objective is the minimum maximum step rating.

**Validation scope.** Every step that creates or re-opens a frontier entry, and
therefore every witness edge, is validated independently; witnesses are also
replayed with `validate_path`. Steps that lead to an already known state (a
transposition) or that are a non-representative duplicate of the same successor
are **not** validated in either mode, exhaustive or SSL: they add no new state,
the model includes every emitted step whose application succeeds, so this does
not weaken the result. It does weaken the purely defensive "a detector produced
an invalid proof" alarm compared with the pre-7.1 search, which validated every
step. Their counts are reported as telemetry (`transposition_hits`,
`duplicate_children_removed`). Validating them would add work proportional to
all raw steps (about twice the validations) for no change in any verdict.

Certification enumeration replaces the legacy representative advanced-detector
search with explicit chain/ALS/forcing enumeration and exhaustion telemetry.
The model covers the currently implemented pattern families, simple candidate
chains, disjoint ALS chains and single-assumption clause propagation. It is not
all possible human Sudoku logic. Missing techniques, overlapping ALS variants,
arbitrary grouped nodes and unrestricted dynamic forcing are outside this model.

Operational limits do not define missing branches as impossible. If a chain
could extend beyond a length limit, ALS enumeration omitted larger sets, or
propagation stopped early, the negative search is inconclusive. A nonempty
limit-reason list prevents `PROVEN_UNSOLVABLE_WITHIN_MODEL` even if the retained
frontier becomes empty.

## Negative certificate: Stuck-State Superset Lemma (SSL-v1, Phase 7.1)

Mathematical basis: `docs/PHASE7_1_STUCK_STATE_PROOFS.md` (theorem §2, family
proofs §4, guards §6). Implementation: `certification/stuck_state.py`, wired
through `SudokuTransitions.negative_certificate` / `check_negative_certificate`
and tried once at the root of every `threshold_search` when
`CertificationConfig.use_stuck_state_lemma` is true (default). Setting it to
false reproduces the pure exhaustive search; the flag is part of the
configuration fingerprint and of the JSON round-trip.

**Order.** `X ⊒ G` iff for every cell `L_G(c) ⊆ L_X(c)` (candidates plus the
placed digit) and every cell empty in G is empty in X. It is checked directly
with bit operations, never inferred from a path.

**Closure.** From the root, the certifier applies, deterministically and
cheapest-first (lowest rating level, then canonical step order), one enumerated
step at or below T at a time. Every applied step is validated by
`proofs.validate_step` (a failure is a search `ERROR`). It stops at a state G
without steps, at a solved state, or at the deadline. The path to G is logically
irrelevant; operational limits met on the way do not matter.

**Theorem (scope).** If G is valid, `root ⊒ G`, G is unsolved, and a fresh
uncached `StepEnumerator` at G and T returns `complete`, no limit reasons and
zero steps, then no transition path at ceiling T reaches a solved state. It is
proven for every family rated ≤ 35 (singles, Locked Candidates, naked/hidden
subsets, fish, Skyscraper/Kite/Turbot, Empty Rectangle, XY-/XYZ-/W-Wing,
X-Chain, XY-Chain, AIC incl. discontinuous loops, Nice Loop, Grouped AIC), hence
only for `T < 36`. ALS (≥ 36), Forcing Chain and Nishio are not covered. The
certificate is a proof for the **unbounded-length model** M_T: chain length
and work limits are not part of the model, and completeness at G (no
`CHAIN_LENGTH_LIMIT`/`CHAIN_NODE_LIMIT`) shows that no chain instance of any
length is hidden there. A certificate at T covers every T' ≤ T.

**Guards (all must pass; otherwise no certificate and unchanged fallback to the
exhaustive search):**

| Guard | Check |
|---|---|
| G0 | closure finished without timeout or error |
| G1 | G is a valid `SudokuState` (fresh object) |
| G2 | `root ⊒ G` by the direct bitwise test |
| G3 | G is not solved (a solved G is instead a positive witness, validated with `validate_path`, and the threshold is `SOLVED`) |
| G4 | fresh `StepEnumerator(config, cache=False)`, unmodified class and methods, at G and T: `complete is True`, `limit_reasons == []`, `steps == []`, deadline not passed |
| G5 | `0 ≤ T < 36`; every instance difficulty equals the registry rating equals the audited table; every enabled family is proven; every proof dependency is enabled (e.g. NS and HS for singles; LC for Empty Rectangle and Grouped AIC; NS, Naked Pair and XY-Wing for XYZ-Wing; AIC for Grouped AIC; smaller subsets/fish for larger ones) |
| G6 | technique classes, order and structural flags (subset/fish size, chain mode/grouped/loops-only) equal `default_techniques` |
| G7 | SHA-256 of the audited sources equals the pinned table in `stuck_state.py`: `sudoku/{candidates,grid}.py`, `solver/techniques/{__init__,base,singles,locked_candidates,subsets,fish,single_digit_patterns,wings,chains}.py`, `solver/{human_solver,models}.py`, `certification/{enumeration,enum_chains,transitions,models}.py`. Any change fails closed until a re-audit updates the pins |
| G8 | (diagnostic) the closure path replays from the root with `validate_path` to exactly G; a failure is an `ERROR` |

A timeout during the closure or the guard check never yields a certificate; the
fallback search then reports `TIME_LIMIT` as usual. A custom or patched
enumerator defines a different model and never uses SSL: besides the class and
its methods, the identities of the in-process objects the enumerator dispatches
to are pinned at import (`enumerate_chains`, `enumerate_als_steps`,
`enumerate_forcing`, `canonical_steps` in both modules, `InferenceGraph` in both
modules, `default_techniques`, `Technique.step`, `human_solver.apply_step`, and
every technique class's `find_steps`/`step`); any monkeypatched replacement of
these objects disables SSL. The identity of the dispatch entry points is pinned;
arbitrary in-process monkeypatching of deeper helpers is out of scope (for
example `solver.techniques.chains.conflicts`, `step_key`, `PEERS` or `SudokuState`
methods: patching such a helper can make SSL issue a false certificate, but no
production path patches code at runtime). On-disk integrity of all audited
sources is enforced by the G7 SHA-256 pins.

**Solved closure.** A solved closure is a witness with the same semantics as a
search witness: it must be no longer than `max_path_depth` and the node budget,
its `len(path)` applications count as states explored, and it is replayed with
`validate_path`; otherwise the search falls back to exhaustive exploration. A
proven certificate explores no search states (`states_explored = 0`); the
closure length is reported in its evidence.

**Confluence alarm (fail closed).** After the descent, every threshold T certified
by SSL in the invocation is cross-checked cheaply (`stuck_state.confluence_violation`):
a `SOLVED` result at any T' ≤ T, an accepted witness rated ≤ T, a state on the
witness prefix whose steps are all rated ≤ T (states reachable at T) that is not
`⊒ G`, or a prefix step violating SSL w.r.t. G refutes the theorem or the code.
The certified threshold result then becomes `ERROR` and the puzzle
`INVALID_PROOF`. Any exception inside the check is itself an alarm (fail
closed). A second complete dead end Y ≠ G is not searched for actively
(that would need extra enumerations); the exhaustive search never runs after an
accepted certificate at the same T.

**Evidence and telemetry.** A certified threshold result carries
`negative_proof_kind = "STUCK_STATE_SUPERSET_LEMMA"` and a deterministic,
JSON-native `negative_certificate`: lemma version `SSL-v1`, threshold, G's full
signature (81 digits, `/`, 81 masks in hex), closure length, G's candidate
count, enumeration work at G, the source fingerprint and every guard result.
Exhaustively proven thresholds carry `negative_proof_kind = "EXHAUSTIVE_SEARCH"`.
Timings (closure and check seconds, enumerations, failed guards, outcome
`PROVEN`/`SOLVED`/`FALLBACK`/`TIMEOUT`/`ERROR`) are in the threshold
`telemetry["stuck_state_lemma"]` and are excluded from reproducibility
comparisons. `CertificationResult.negative_proof_kind` names the evidence
immediately below the certified minimum, and production metadata exports it as
`certification.negativeProofKind`; the strict fresh re-certification compares it
like every other certified field.

**Semantic note.** The exhaustive search visits every reachable state and
raises `ERROR` when a frontier-creating step fails independent validation (see
"Validation scope" above: transposition and duplicate edges are not validated
in either mode). SSL does not visit those states at all, so that defensive
check is no longer performed for unvisited states (no defensive `ERROR` there).
This is not part of the model: the theorem covers every emitted step whose
application succeeds, valid or not, so the model is not weakened. Steps on the
closure path and any solved witness are still validated.

## Centralized budgets

All parameters live in immutable `CertificationConfig` and round-trip through
JSON. Default limits are:

| Parameter | Default |
|---|---:|
| time_budget | 60 seconds per candidate |
| node_budget / state_budget | 10000 / 10000 |
| max_path_depth | 256 |
| max_alternative_steps_per_state | 512 |
| max_chain_length / max_chain_search_nodes | 19 / 100000 |
| max_als_size / max_als_chain_length / max_als_search_nodes | 4 / 5 / 30000 |
| max_forcing_depth / max_forcing_nodes / max_forcing_starts | 12 / 2000 / 160 |
| use_stuck_state_lemma | true |

Timeouts are cooperative, so an individual validation or detector call can
finish beyond the deadline; this never permits a late production promotion.
Changing a budget changes the configuration fingerprint. Certification v1
does not reuse persistent final-result certificates: `fresh=True` is always
used before production output. Search transpositions are invocation-local.
The enumeration cache (bounded LRU, 12 000 per-technique results, key =
enumerator config fingerprint + full state signature + technique) and the proof
validation cache (4 096 entries) are invocation-local; results cut by a deadline
are never cached. They pay off across stages (SSL closure, fallback search,
bottleneck stage), not within one exhaustive search.
Reports retain algorithm/config fingerprints, version, limit reasons, visited
state counts and elapsed/stage timings. Reproducibility excludes wall-clock
durations and the unstable frontier reached exactly at a time cutoff.

## Bottlenecks and official classification

Genuine bottlenecks are recomputed on the certified path from independently
validated available steps. A high-level event requires complete exclusion of
cheaper alternatives in that state. Repeated related proof evidence and adjacent
high steps are grouped rather than counting every elimination as a new crisis.
Reports include event positions, late-game crises and gaps of trivial steps.
These are properties of the selected certified path, not a proof that every
possible path has the same crisis count.

Extreme requires uniqueness, human logical solvability, deterministic valid
proof replay, conclusive minimum required rating at least 30, at least two
certified crises and at least three advanced steps. Ultra additionally requires
required rating at least 36, at least three crises, five advanced steps,
chain length at least eight and advanced work in at least two of four path bins.
Advanced steps use rating >=12; bottleneck threshold is 12, extreme steps >=22.
Thresholds and acceptance minima cannot be weakened below the existing official
DifficultyConfig policy to manufacture production labels.

Clue count does not increase rating. Twenty-two or twenty-five clues do not
invalidate a strong certificate. `require_minimal=False` is the default;
the factual minimality result is always retained. Monster/17–21-clue generation
is not a Phase 7 requirement.

## CLI, research and production files

```console
python -m generator certify --input docs/PHASE6_CANDIDATES.json --fresh --output data/production/puzzles.json --research-output data/candidates.json --reports-dir reports/certification
python -m generator certify --input docs/PHASE6_CANDIDATES.json --puzzle-id puzzle-ca88d658a18eafb27c24 --fresh
python -m generator certify --puzzle 050000000000028000090600000601000009000004006003010200200940010000007005700050030 --fresh
```

`--config` loads complete or partial CertificationConfig JSON; budget options
override corresponding values. `--solution` is optional with `--puzzle`.
`--puzzle-id` preserves an existing ID; absent IDs use the existing stable
`puzzle-` plus first 20 SHA-256 hex digits of the puzzle string.

Duplicate IDs and exact puzzle strings cause structured `DUPLICATE` rejection
of all colliding entries before expensive certification. Research retains every
input record and its result, including failures. An experiment combining
overlapping archives must explicitly deduplicate its inputs and preserve their
source provenance; symmetry deduplication is not implemented.

Production output contains only fresh eligible records. No saved result object
can be passed as authorization for publication. JSON uses schemaVersion=1 plus
optional `certification` metadata containing complete proof evidence and policy.
Each field is compared against this invocation's fresh result during JSON
readback. Writes validate in memory, write/fsync a temporary file, parse and
validate that file, atomically replace the destination and verify its bytes.
The public `validate_production_database` independently re-certifies each puzzle
and compares the certified metadata, excluding measured runtimes.

An accepted count of zero produces an explicit empty production dataset and
exit code 1. A nonempty accepted set returns 0 even if other inputs were rejected;
CLI/config/I/O errors return 2. Outputs replace the selected dataset; this is
not an append command. Input/config and output paths must be separate. Detailed
per-candidate diagnostic JSON goes to `--reports-dir`; research and production
files use separate formats and destinations.

The current `data/puzzles.json` remains the independent Phase 5 demo collection.
`generate` and `evolve` retain their legacy preliminary exporters; they do not
provide Phase 7 certificates. The strict production file is
`data/production/puzzles.json`. An empty production file is structurally valid,
but cannot supply a playable frontend collection. Phase 7 does not switch the
frontend loader or publish/deploy a website.
