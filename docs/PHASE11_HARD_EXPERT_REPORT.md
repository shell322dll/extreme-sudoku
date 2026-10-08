# Phase 11: Hard and Expert production content

Generation and merge completed on 2026-10-07; final preservation audit on 2026-10-08.
The production database now has 48 puzzles: 9 Easy, 9 Medium, 10 Hard, 10 Expert and 10 Extreme.
All 28 pre-existing records are canonically identical to the baseline commit; no Ultra content was added.

## Admission contract

- Existing generator, registry, Deep classifier and certification algorithms are unchanged.
- Hard requires the existing Deep class Hard, required rating in [7, 12), and technique ceiling 11.
- Expert requires the existing Deep class Expert, required rating >= 12, and registry ceiling 55.
- Expert is not artificially capped below 30: one AIC bottleneck does not meet all Extreme gates.
- Both use verification v1 / DETERMINISTIC_THRESHOLD_REPLAY, unique solution, independent proof validation and deterministic replay.
- Standard verification does not claim a global minimum over every possible logical solution path.

## Reproducibility

Exact generation commands, every selected ID, seed, attempt seed and production record hash are in
[content-qc.json](../reports/phase11/content-qc.json). Commands are also documented in
[GENERATION_GUIDE section 21](GENERATION_GUIDE.md#21-hard-и-expert-phase-11).
Batch reports and backups stay local; source production contains full verification evidence.

| Level | Seeds | Attempts | Selected / verified pool | Seconds | Required ratings |
| --- | --- | ---: | ---: | ---: | --- |
| Hard | 11101, 11102, 11103 | 325 | 10 / 15 | 282.328 | 8.0, 9.0, 9.2 |
| Expert | 11201, 11202, 11203 | 51 | 10 / 15 | 77.708 | 14.0, 17.0, 22.0, 25.0, 30.0 |

The two runs overlapped; these are observed wall-clock durations, not a future performance guarantee.

## Verification and preservation

- Targeted Python checks: 7 new Hard/Expert tests and all 15 existing Phase 10 tests passed.
- Frontend standard admission checks: 6/6 passed, including Hard/Expert bands and fresh-only selection.
- Dry-run: 20 accepted, zero skipped, total 48, production untouched.
- Final merge: 20 accepted, zero skipped, verified backup and built-in post-write production validation succeeded.
- Independent content audit: 48 unique IDs, puzzles, solutions and symmetry fingerprints.
- All 28 baseline records match both saved canonical hashes and the baseline Git object.
- Certification algorithm fingerprint and original backup SHA-256 are unchanged/verified.
- Full-suite, browser and deployment validation is reported separately by release QA.

Baseline commit: `e7d5f2984f73a87db5e3cdcda47d70361f2c01aa`.
Algorithm fingerprint: `3ccb7aa047be7ecb90b09da5e40e080e99727c85970e94463b5d697169cee805`.

No commits, pushes or hosting changes were performed by the content-generation task.
