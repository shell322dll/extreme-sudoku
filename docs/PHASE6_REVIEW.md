# Phase 6 — critical review, 2026-09-29

Scope: evolution configuration, fitness, population loop, uniqueness repair,
mask operators, selection, archive, CLI, export, diagnostics and regression tests.
Phase 7, frontend and published puzzle data remain outside this change.

## Findings and resolution

1. **Quick/Deep selection bias.** Only Deep received the tier bonus, allowing
   easier evaluated individuals to displace promising Quick candidates.
   Quick now uses a provisional tier on the same numerical scale. It still
   cannot enter the verified archive or become the reported best.
2. **Deferred Deep starvation.** Old Quick records and random injections were
   excluded from subsequent Deep selection. A single staged budget now selects
   pending records from the entire old/offspring/injection pool.
3. **Modes were only output filters.** Mode presets now change fitness weights;
   direct configuration and `for_mode` agree. MIN_CLUES is isolated from Extreme.
   Monster target matching also requires confirmed minimality.
4. **Pareto could erase the scalar champion.** The vector intentionally differs
   from the scalar formula, so dominance does not guarantee higher scalar fitness.
   A separate historical champion now survives Pareto updates and participates
   in export and snapshots.
5. **Equal-score evidence could remain stale.** Same-key champion updates now
   retain completed minimality checks even with zero minimality bonus.
6. **CLI could omit the sole matching champion.** The export gate now checks
   archive plus champion, matching the exporter selection domain.
7. **Cached local-search evidence mismatch.** If either endpoint already has
   Deep evidence, both endpoints are Deep-evaluated before accepting an improvement.
8. **Incomplete diagnostics.** Added per-generation advanced count, unique masks,
   mutation and repair success rates, archive size, cache lookup denominators
   and inclusive local-search timing.

Every corrected behavioral boundary has a regression assertion in
`test_evolution_core.py` or `test_evolution_engine.py`. The final suite is
**269 tests, OK, 85.488 s**, including all 230 historical Phase 1–5 tests.
Focused Phase 6 suite: **39 tests, OK, 29.714 s**.

## Review provenance

An independent reviewer checked the original implementation, rechecked the main
changes, and identified the equal-score evidence and CLI integration edge cases.
Sub-agent service limits interrupted the last review turn. The primary agent
inspected the remaining changes, closed those findings, ran their regressions,
and ran the complete suite. No remaining blocking defect was identified in this
review; this is not a claim of exhaustive correctness certification.

## Preserved boundaries and limitations

- Exact search remains confined to mathematical uniqueness/construction checks.
  Human difficulty uses the existing bounded logical solver without guessing.
- Repair clues come from witnessed target/alternative difference sets; cached
  conflicts do not replace the final exact uniqueness check.
- Export reuses Phase 5 schema-v1 validation and human-path reconstruction.
  Results retain preliminary metadata.
- Search allows exploratory clue counts above the 17–21 target; target matching
  and `--targets-only` apply the target limits explicitly.
- The Pareto frontier is capped; objective endpoints are preferred on truncation.
  The scalar champion is preserved separately.
- Snapshot is the requested minimum checkpoint, not a resumable RNG checkpoint.
- Reproducibility excludes timestamps, timings and wall-clock cutoff decisions.
- Stage timings overlap, and expensive in-flight solver calls can exceed the
  cooperative deadline. The experiment report states these limits explicitly.
