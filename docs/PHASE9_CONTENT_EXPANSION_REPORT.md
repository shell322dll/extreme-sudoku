# Phase 9 — Content Expansion: 1 → 10 certified production puzzles

Date: 2026-10-02/03. Scope: new package `generator/production/` (batch orchestration, suitability heuristic, diversity
checks, research archive, safe merge, report recomputation), CLI dispatch in `generator/__main__.py`, Python tests,
`data/production/puzzles.json` (append-only merge), research data under `data/research/`, frontend multi-puzzle
support (`web/`, frontend version 0.2.0), README/docs. The fingerprinted folders `generator/certification`, `solver`,
`sudoku` and `rating` were **not changed** (`git diff --stat` on them is empty). The certifier was not weakened, the
Stuck-State Lemma was not extended, and no Monster 17–21-clue search was run.

## Baseline (before any change, HEAD `eb1b9b6`)

| Check | Result |
| --- | --- |
| Python tests (`unittest discover -s generator/tests`) | 413 OK, 156.0 s |
| Frontend unit tests (`node --test tests/*.test.js`) | 31 / 31 pass |
| Browser regression (Chromium + WebKit) | 26 check groups (13 per engine) pass |
| Responsive layouts | 56 / 56 pass |
| `scripts/validate_production_database.py` | OK, 1 puzzle, 1.8 s |

The task specification mentioned 24 browser groups; Phase 8 had in fact shipped 26 (13 per engine), which is
the number measured here.

## Final test results (10-puzzle production DB)

| Check | Result |
| --- | --- |
| Python tests | **448 OK**, 177 s (413 original + 35 in `generator/tests/test_production_phase9.py`) |
| Frontend unit tests | **43 / 43** pass |
| Browser regression | **28 / 28 check groups** (14 per engine), 92 s |
| Responsive layouts | **56 / 56** pass |
| Production DB validator | **OK, 10 puzzles, 12.3 s** (fresh re-certification of every record) |
| Pages build | `dist/data/production/puzzles.json` 10,813 bytes; cache-busting `app.js?v=605a430835a8f766`, DB `?v=441c6e8efb465801` |

Honest caveat: the browser suite's multi-puzzle group runs on the fixture `web/tests/fixtures/production_multi.json`
(4 IDs, of which 3 — `puzzle-3f3131ea81afc72af5a7`, `puzzle-16042cbcb8633fea9323`, `puzzle-3d691a3d3f12081348df` —
are merge-rehearsal puzzles that are not in production). The real 10-puzzle flow was verified by an additional
Playwright check on the built `dist/`: New Game ×10 produced 10 distinct IDs before any repeat, never an immediate
repeat, and per-ID progress stayed isolated after a reload.

## Generation strategy

* **Source: ordinary random generation, not evolution.** `production-batch` calls the unchanged
  `PuzzleGenerator.generate_many` (random solution per attempt, random clue removal, minimalization, Quick then Deep
  rating) with `target_difficulty="Extreme"`. The planner's measurements showed evolution drifts to Deep 50/55
  (not certifiable) and produces near-clones from 2–3 solution grids, whereas `generate` gives every attempt a new
  solution.
* Rejected attempts are recorded by a thin subclass that only wraps `_construct`/`_attempt` (results pass through
  unchanged, so generation is still reproducible per seed; tested).
* **Seeds:** 9101, 9102, 9103, 9104 (one deterministic generator run each). Seeds 9105/9106 were prepared as a fallback
  for band 35 but not needed.
* **Batch sizes:** `--per-seed-count 12` accepted Extreme puzzles per seed, `--max-attempts 100000`,
  `--generation-seconds 600` per seed (no seed hit the timeout; all four completed), `--runtime-budget 3600`,
  `--shortlist 20`, `--target-new 9`, `--probe-seconds 15`.
* **Clue range:** 22–30, minimal puzzles only (`--minimal`). Clue count is not an objective; the range matches the
  measured certified range. Production clues are 22–27.
* **Generation runtime (run 1):** 405.8 s in total (9101: 108.4 s, 9102: 123.9 s, 9103: 100.6 s, 9104: 72.8 s);
  140 Deep-rating calls. The whole run took 453.3 s (probe 38.5 s, final certification 8.6 s).

## Runs

| Run | Command (abridged) | Generated | Cert. attempts | Certified | Inconclusive (timeouts) | Runtime |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `20261002T205655Z` | `--seeds 9101,9102,9103,9104 --per-seed-count 12 --min-clues 22 --max-clues 30 --shortlist 20 --target-new 9` | 500 | 11 | 9 (all Deep 30) | 2 (2) | 453 s |
| aborted band-35 run (`evaluatedRunId 20261002T211958Z`) | `--reuse-archive --bands 35 --shortlist 12 --target-new 4` | 0 | 1 | 1 (`puzzle-1f8654f0383f0475e8a9`, 35) | 0 | interrupted |
| `20261002T212048Z` | `--reuse-archive --bands 35 --shortlist 12 --target-new 4 --runtime-budget 1800` | 0 (45 reused) | 9 | 3 (all 35) | 6 (6) | 96 s |

The aborted run was stopped after its first selection and left no report; its only effect is the archive entry for
`puzzle-1f8654f0383f0475e8a9` (selected, later merged). A retry failed fast on the archive lock it left behind
(`batch_run_band35.lockfail.log`, exit 2: the stale-lock behaviour working as designed); after the stale lock was
removed, run `20261002T212048Z` completed. Logs: `data/research/phase9/batch_run*.log`.

Run 1's original `batch_report.json` was written before the counter definitions were fixed (it showed
`rated = 140`, which was really the number of Deep calls, and `inconclusive = 0` with 2 timeouts). The
counters were recomputed from the checkpoints and archive into `batch_report.recomputed.json` with
`python -m generator production-report --run-dir data/research/phase9/runs/20261002T205655Z`; the original file is
untouched. Numbers below use the recomputed report. Counter definitions: `docs/DATA_FORMAT.md` §57.1.

## Funnel and yields

| Counter | Run 1 | 9101 | 9102 | 9103 | 9104 | Band-35 runs (both) | Phase 9 total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| generated (attempts) | 500 | 155 | 101 | 147 | 97 | 0 | **500** |
| unique (passed exact uniqueness) | 496 | 154 | 98 | 147 | 97 | — | **496** |
| rated (Quick and/or Deep) | 496 | 154 | 98 | 147 | 97 | 45 reused | 496 |
| Deep-rated Extreme candidates | 57 | 14 | 15 | 14 | 14 | — | 57 |
| in band 30/32/35 | 48 | 12 | 12 | 12 | 12 | — | 48 |
| eligible after prefilter | 48 | 12 | 12 | 12 | 12 | 37 / 36 | — |
| shortlisted | 20 | 5 | 5 | 4 | 6 | 10 + 9 | — |
| certification attempts | 11 | 3 | 2 | 3 | 3 | 1 + 9 | **21** |
| certified (default budget) | 9 | 2 | 2 | 2 | 3 | 1 + 3 | **13** |
| inconclusive (all CERTIFICATION_TIMEOUT) | 2 | 1 | 0 | 1 | 0 | 0 + 6 | **8** |
| certification yield (certified / attempts) | 81.8 % | 66.7 % | 100 % | 66.7 % | 100 % | 40.0 % | **61.9 %** |
| generation yield (certified / generated) | 1.8 % | 1.3 % | 2.0 % | 1.4 % | 3.1 % | — | **2.6 %** |

By Deep band: Deep 30 certified 9 of 11 attempts (82 %), Deep 35 certified 4 of 10 (40 %). The planner's probe
measured 90 % and 52 %. Every one of the 8 inconclusive results is a 15 s probe `CERTIFICATION_TIMEOUT` (SSL guard G4
chain limits at the closure, then the exhaustive fallback runs out of time). None was relabelled, retried with a
weaker policy or published. Of the 13 certified candidates, 9 were merged and 4 Deep-30 ones
(`puzzle-a60ef3350d0c5162839b`, `puzzle-a42bc89365f9d2c8e15f`, `puzzle-32b58e5e2bea86b099cf`,
`puzzle-7d168f0b529cfef39cce`) stay selected-but-unmerged in the archive for a later expansion, by user decision.

## Rejected (structured reasons)

Run 1 (500 attempts) by stage (`rejectedByStage`): generation 443, prefilter 37, certification 11.

| Reason | Run 1 | Archive now (500 entries, after the band-35 re-evaluation) |
| --- | ---: | ---: |
| `TOO_EASY` (generator: rated below Extreme) | 439 | 439 |
| `OUTSIDE_CLUE_RANGE` (minimalized below 22) | 4 | 4 |
| `NOT_UNIQUE`, `HUMAN_UNSOLVED`, `DUPLICATE`, `NEAR_DUPLICATE`, `PROOF_INVALID` | 0 | 0 |
| `OUT_OF_CONCLUSIVE_SCOPE` (Deep ≥ 36: 36 ×1, 39 ×2, 42 ×1, 50 ×5) | 9 | 9 |
| `NOT_SHORTLISTED` | 28 | 27 |
| `NOT_SELECTED_TARGET_REACHED` | 9 | 0 (re-evaluated by the band-35 runs) |
| `CERTIFICATION_TIMEOUT` (probe budget) | 2 | 8 |

Archive status summary: `byStatus` CERTIFIED_EXTREME 13, PROBE:CERTIFICATION_TIMEOUT 8, NOT_ATTEMPTED 479; selected 13,
merged 9.

## Shortlist criteria

1. **Exact duplicates.** Puzzle string or content ID against production, already-selected archive entries and
   earlier seeds of the same run.
2. **Suitability gate.** The candidate must have a verified Deep required level and be human-solved, with Extreme or
   Ultra class and Deep ≥ 30. Deep ≥ 36 is skipped as `OUT_OF_CONCLUSIVE_SCOPE` unless `--include-high` is given.
3. **Near-duplicates.** Rejected are same solution string with clue-mask distance ≤ 8, any second puzzle on one
   solution (policy), and an equal symmetry fingerprint.
4. **Order.** Score descending, then ID. The top `--shortlist` K go forward.
5. **Band options.** `--bands` (only these Deep ratings) and `--min-per-band` (reserve the best N per band) are
   available. Run 2 used `--bands 35` together with `--reuse-archive`, which re-evaluated the 45 rated, non-final
   archive candidates without regenerating.
6. **Certification.** Each shortlisted candidate gets a 15 s probe; on success, a fresh default-config certification
   (60 s budget). It is selected only if production-eligible, certified in ≤ 15 s (0.25 × budget, so CI
   re-certification on every deploy keeps a large margin) and still diverse against production and earlier selections.

## Suitability heuristic, and why it is sound as prioritization but not proof

Score (version 1) = 100 × band prior {30: 1.00, 32: 0.80, 35: 0.55, 36: 0.05} + 5 × min(Deep bottlenecks, 6)/6 +
3 × min(advanced steps, 20)/20 + 2 if band 32/35 − 0.2 per clue above 26 − 0.1 per chain step above 10 − 2 if the path
uses ALS/forcing. Measured scores: Deep 30 ≈ 105–107, Deep 35 ≈ 59–64.

Why it is sound as prioritization:

* Its inputs are the preliminary Deep metrics. The band prior is the measured probability that the unchanged certifier
  finishes conclusively in that band.
* It only decides which candidates get expensive certification time first, under a budget.

Why it is not proof:

* Deep is a bounded, greedy analysis. It does not show that no easier path exists, and its X-Chain limit (15) differs
  from the certifier's (19).
* The assessment object has no status field, and a test asserts the score never carries or implies one. Archive
  entries keep `certification.status = "NOT_ATTEMPTED"` until a real certifier run.
* `production-merge` ignores every archived or probe status and certifies again from scratch with
  `CertificationConfig()`.

A wrong score can cost time or skip a certifiable puzzle; it can never admit an uncertified one.

The heuristic's weakness showed in run 1: the strong band prior put all 20 shortlist slots on Deep 30, so the 10
Deep-35 candidates were `NOT_SHORTLISTED`. This was fixed procedurally with `--bands 35` plus `--reuse-archive`,
not by changing the certifier. The score itself remains secondary.

## Production database (10 records, all `CERTIFIED_EXTREME`, certification version `1`)

Order as stored (exporter key: difficulty, −rating, clues, id). All records use config fingerprint `bdf36558…`, negative
proof `STUCK_STATE_SUPERSET_LEMMA`, and the hardest step equals the certified minimum. "Seed" is the generator seed of
the Phase 9 run.

| ID | Clues | Status | Rating | Certified bottlenecks | Hardest technique | Seed |
| --- | ---: | --- | ---: | ---: | --- | --- |
| `puzzle-402277f36b14d1f25b38` | 22 | CERTIFIED_EXTREME | 35 | 6 | Grouped AIC | 9102 |
| `puzzle-8e2b144cecb50551d96b` | 22 | CERTIFIED_EXTREME | 35 | 3 | Grouped AIC | pre-Phase 9 baseline |
| `puzzle-1f8654f0383f0475e8a9` | 25 | CERTIFIED_EXTREME | 35 | 13 | Grouped AIC | 9104 |
| `puzzle-fba1027eee1fe3122fba` | 25 | CERTIFIED_EXTREME | 35 | 3 | Grouped AIC | 9103 |
| `puzzle-0880074738584f4bafaf` | 27 | CERTIFIED_EXTREME | 35 | 2 | Grouped AIC | 9103 |
| `puzzle-ef75603e05a5a50595b3` | 23 | CERTIFIED_EXTREME | 30 | 7 | AIC | 9101 |
| `puzzle-82d7ba971f8d1d590d21` | 24 | CERTIFIED_EXTREME | 30 | 8 | AIC | 9102 |
| `puzzle-f435769013cf93d845d9` | 24 | CERTIFIED_EXTREME | 30 | 5 | AIC | 9104 |
| `puzzle-44ce36d87f6b23932fd1` | 25 | CERTIFIED_EXTREME | 30 | 6 | AIC | 9103 |
| `puzzle-72ebea8bd07cdf09c006` | 26 | CERTIFIED_EXTREME | 30 | 5 | AIC | 9104 |

Fresh certification times in the merge were 0.59–2.56 s per record; advanced steps 4–23.
QC (`data/research/phase9/production_qc.json`): all 10 records OK. The checks cover format, valid solution, givens,
clue count, status/difficulty/rating consistency, evidence consistency and unique solution. Globally: 10 unique
IDs, puzzles and solutions, stats match, and 8e2b's serialized block is byte-identical to the frozen baseline fixture
(block SHA-256 `49582ca4…` on both sides).

### Ultra Extreme: 0, by design

Ultra needs a certified minimum ≥ 36 (ALS-XZ or harder), and a minimum is certified only when the threshold directly
below the observed upper bound is proven unsolvable. The only negative proof that finishes on real puzzles is SSL-v1,
which is defined only for thresholds < 36. At ≥ 36 the exhaustive fallback always hits its budget, so the result stays
`CERTIFICATION_TIMEOUT`/`SEARCH_INCONCLUSIVE`. Deep-36+ candidates (9 in run 1) were therefore archived as
`OUT_OF_CONCLUSIVE_SCOPE` rather than attempted. Producing Ultra would need a new proof method, not a relaxed one.

## Diversity summary and duplicate checks

* 10 distinct solution strings, so one puzzle per solution holds. All 10 symmetry fingerprints differ.
* The minimum clue-mask distance between any two records is 25. The near-duplicate rule only applies to the same
  solution, and no two records share one.
* Rating mix: 5 × 35 (Grouped AIC), 5 × 30 (AIC). Clues: 22, 22, 23, 24, 24, 25, 25, 25, 26, 27. Certified
  bottlenecks: 2–13.
* Technique profiles: the highest cosine similarity among same-clue-count pairs is 0.958, so no ≥ 0.98 warning was
  raised. The highest overall is 0.989, but those two records have different clue counts.
* All Phase 9 runs found 0 exact duplicates, 0 ID collisions and 0 near-duplicates (`selectedSameSolutionPairs` 0).
* The merge re-checked every candidate against the existing DB and earlier admissions for exact puzzle string, ID,
  same solution, clue-mask ≤ 8 and symmetry fingerprint. All 9 candidates passed (0 skipped).

## Merge result

`python -m generator production-merge --archive data/research/phase9_candidates.json --target-total 10` →
`data/research/phase9/merges/merge-20261003T052550Z.json`:

* The existing DB was validated first (fresh re-certification).
* 9 new records were admitted, each freshly certified with the default config. Skipped 0; total 10; `written: true`;
  `archiveUpdate: done` (the 9 archive entries carry `production.merged = true`).
* `existingFormatCanonical: true`, so 8e2b is preserved byte-for-byte.
* Backup: `data/research/phase9/backups/puzzles-20261003T052537Z-ba44f37a58f4.json` (gitignored). Its SHA-256
  `ba44f37a…` equals the pre-merge file and the test fixture.
* Write: temp file + atomic rename, then `validate_production_database`. The independent validator afterwards gave
  OK, 10 puzzles, 12.3 s. The file is now 3,138,983 bytes.
* Two dry runs preceded the merge (`merges/*.dry-run.json`, gitignored).

Process note: the launch agent's merge attempt was blocked by the permission classifier (a production-data write).
The manager ran the merge only after explicit user approval.

## Frontend: multi-puzzle tests, New Game behaviour, localStorage isolation

* **New Game** (`web/lib/selection.js`, pure and unit-tested) never returns the current puzzle while another
  selectable puzzle exists. Preference order:
  1. Unsolved and never opened.
  2. Unsolved in progress (resumes its own save).
  3. When everything is solved, the puzzle solved longest ago, as a fresh replay.

  With exactly one puzzle, the single-puzzle replay dialog from 0.1.0 is kept.
* **localStorage:** `extreme-sudoku.progress.v2` holds `{storageSchemaVersion: 2, activePuzzleId, games: {<id>:
  snapshot}}`. Values, notes, timer, mistakes, hints and undo history are stored per puzzle ID, and the solved list is
  in `extreme-sudoku.recent.v1`. Switching puzzles never overwrites another puzzle's progress (unit and E2E tested;
  also checked on the real 10-puzzle `dist/`).
* **Tests:** frontend unit tests went from 31 to 43 (selection logic plus multi-record production/build tests). The
  browser suite went from 26 to 28 groups, adding a multi-puzzle group per engine. Single-puzzle groups were pinned
  to a one-record payload, and tests look up 8e2b by ID instead of `puzzles[0]`. `build_pages.mjs` adds a content
  hash to the database URL so Pages caches cannot serve the old 1-puzzle JSON.

## GitHub Pages deploy result

PENDING — filled in after push

## Public smoke result

PENDING — filled in after push

## Known limitations

* **All solution grids are isomorphic by construction** (Latin pattern plus permutations). Variety comes only from
  clue masks, digit labels and orientation. The symmetry fingerprint is a conservative invariant, not a canonical
  form.
* **Only bands 30 and 35 are certifiable in practice.** Band 32 (Nice Loop) was never observed, and ≥ 36 is out of
  conclusive scope, so there is no Ultra content. Deep-35 certification yield is about 40–50 %.
* **Size of the source DB.** Each record carries its full evidence (59–159 KB serialized), so the source DB is 3.1 MB.
  The dev page (`/web/`) loads all of it. The published `dist` JSON is slim (10.8 KB).
* **CI cost.** CI re-certifies every record on every deploy (≈ 12 s for 10 locally). This grows linearly.
* **Stale locks.** If a batch or merge is killed, `<archive>.lock` stays behind and must be deleted by hand
  (documented; seen once in this phase).
* **Report counters before the fix.** Run 1's original `batch_report.json` uses those counter definitions; use
  `batch_report.recomputed.json`.
* **Heuristic calibration.** The suitability prior is calibrated on about 120 candidates only. Its strong band-30
  preference needs `--bands`/`--min-per-band` to get a rating mix.
* **Test coverage gap.** The browser suite's multi-puzzle group runs on a fixture that is mostly rehearsal puzzles;
  the real DB flow was checked by a one-off Playwright run, not by the committed suite.
* **Unmerged certified candidates.** Four certified Deep-30 candidates remain unmerged in the archive. A later merge
  re-certifies them anyway.

## Recommendation for the next phase (not started)

1. Grow content in small, reviewed merges.
   * First merge the 4 archived Deep-30 candidates.
   * Then run `production-batch --min-per-band 3` on new seeds (for example 9105–9108) to keep about half the new
     puzzles at rating 35.
   * Before each merge, run `--dry-run`, then the validator, QC, and the browser check on the real DB.
2. Change the multi-puzzle browser group to use the real production DB (or a frozen copy of it), and promote the
   one-off 10-puzzle Playwright check into the committed suite.
3. If the source DB passes about 25–30 records, consider keeping full evidence out of the committed file (for example
   a separate evidence store validated in CI) to bound repo size and dev-page load time.
4. Ultra Extreme needs a new, reviewed negative-proof method for thresholds ≥ 36. It should be planned as its own
   research phase. Budgets and SSL scope must not be relaxed.

## Exact commands

```console
# research batch (run 1)
python -m generator production-batch --seeds 9101,9102,9103,9104 --per-seed-count 12 --min-clues 22 --max-clues 30 --generation-seconds 600 --probe-seconds 15 --shortlist 20 --target-new 9 --runtime-budget 3600 --archive data/research/phase9_candidates.json
# band-35 from the archive (run 2)
python -m generator production-batch --reuse-archive --bands 35 --shortlist 12 --target-new 4 --probe-seconds 15 --runtime-budget 1800
# recompute run 1 counters into a new file
python -m generator production-report --run-dir data/research/phase9/runs/20261002T205655Z
# merge (after explicit approval), then validate
python -m generator production-merge --archive data/research/phase9_candidates.json --target-total 10
python scripts/validate_production_database.py
# tests
python -m unittest discover -s generator/tests
cd web && npm test
python web/tests/browser_regression.py --artifacts <dir>
```
