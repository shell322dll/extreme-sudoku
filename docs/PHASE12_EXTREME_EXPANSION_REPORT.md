# Phase 12: ten additional certified Extreme puzzles

Generated and merged on 2026-10-09. The source database now contains **58 puzzles**:
**9 Easy, 9 Medium, 10 Hard, 10 Expert and 20 Extreme**. Exactly ten newly generated Extreme puzzles were added.
All 48 existing records are canonically unchanged against the baseline Git commit and saved record hashes.

## Generation and certification

- Fresh seeds: 120901, 120902, 120903, 120904; prior research archives were not reused or modified.
- Existing production-batch, clue range 22-30, minimal puzzles, 12 requested Extreme candidates per seed.
- Original solver, registry, class thresholds, proof rules and certification budgets are unchanged.
- Generation: 459 attempts; 48 preliminary Extreme candidates plus seven preliminary Ultra candidates.
- 47 candidates passed the scope/prefilter; shortlist 24 reserved three candidates per available rating band.
- 12 candidates underwent certification: ten accepted, two probe timeouts excluded.
- Final default-config certifications: nine minimum-rating 30 and one minimum-rating 35; every new record is CERTIFIED_EXTREME.
- Total batch time: 426.168 s (observed duration, not a future guarantee).
- New certificates completed well below the unchanged 15-second production selection limit.

## Verification and preservation

- Dry-run re-certified ten new puzzles, skipped zero and made no production changes.
- Final merge re-certified all ten with default policy, saved a SHA-256 verified backup and passed built-in post-write validation.
- All 48 original records match the baseline Git object and canonical SHA-256 hashes.
- All 58 IDs, puzzle strings, solutions and symmetry fingerprints are distinct.
- Every new puzzle passes the existing DiversityIndex against the original collection and preceding new puzzles.
- Algorithm fingerprint and certification configuration fingerprint are unchanged.
- Independent release QA: standalone strict validator passed all 58 puzzles in 62.7 seconds; Node tests 59/59 passed; the build contains 58 puzzles.
- Local smoke opened a new Extreme puzzle, verified save/reload and the writer lock, with zero JavaScript errors.
- Release QA independently confirmed preservation of the original 48 records and pre-existing untracked files. Published-site checks follow deployment.

## New records

| ID | Clues | Certified minimum | Bottlenecks | Advanced steps | Default certification seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| puzzle-178dda6a7a271cc89d94 | 26 | 30 | 6 | 8 | 0.813 |
| puzzle-524d16c2bf8075ff51c8 | 25 | 30 | 6 | 12 | 0.878 |
| puzzle-5beac1e2be948e07ba0e | 22 | 30 | 10 | 23 | 2.062 |
| puzzle-5cd814e24669234cc64f | 24 | 30 | 7 | 15 | 1.131 |
| puzzle-71baaef268ddb2a3f064 | 25 | 35 | 10 | 19 | 1.582 |
| puzzle-815dbb405ed14ecaab8f | 25 | 30 | 6 | 7 | 0.839 |
| puzzle-820afd8d58b16becdb48 | 23 | 30 | 6 | 16 | 1.739 |
| puzzle-9a6b8032f50995f11a69 | 27 | 30 | 6 | 13 | 1.112 |
| puzzle-a1a131614d6198c412fa | 25 | 30 | 5 | 15 | 1.330 |
| puzzle-c8f361de263cc6a7eb88 | 25 | 30 | 10 | 21 | 1.769 |

## Reproducibility

Exact commands, per-seed counts, attempt seeds, selected IDs and record hashes are retained in
[content-qc.json](../reports/phase12/content-qc.json). Full proof evidence is in the source production database.
The large research archive, checkpoints, logs and backup remain local under phase12.

Baseline commit: `c824f1c6513ab525a34af89dbde729aa63fccae3`.
Algorithm fingerprint: `3ccb7aa047be7ecb90b09da5e40e080e99727c85970e94463b5d697169cee805`.

No application or generator code was changed for this content expansion. Commit and deployment are handled by the release agent.
