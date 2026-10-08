# Phase 11: Hard/Expert and a local player profile

Validation date: 2026-10-08, Europe/Moscow. The implementation is ready for review
on `feature/hard-expert-local-profile`. Production publication is pending the
existing custom domain's HTTPS certificate; no new application deployment has
been performed by this release task.

## Player behavior

- A local name and preparation level are collected before the first puzzle.
  Preparation recommends a level; all populated levels remain selectable.
- The home screen lists unfinished games. Returning to a saved game requires an
  explicit Resume. Hidden pages, home, reloads and offline time do not advance
  the new active-time timer.
- New Game selects only never-started puzzles. Exhausted categories explain the
  situation and offer other levels or unfinished games. Completed games cannot
  be replayed or restarted. Restarting an unfinished game creates a new attempt
  and retains the previous attempt in history.
- Local statistics retain unique solved puzzles, completion history, reveal
  counts, error-check settings and comparable active-time records. Undo does
  not erase reveal assistance. Legacy timing and unknown legacy details do not
  become new active-time records.
- A Web Lock permits one writer per origin. Other tabs wait and reread current
  storage after acquiring ownership. This requires a secure context (HTTPS or
  localhost). Blocked storage and missing locks show an actionable state.

No accounts, server storage, cloud synchronization or automatic telemetry were
added. Existing browser saves remain on their original origin.

## Content and invariants

Production now contains **48 puzzles: 9 Easy, 9 Medium, 10 Hard, 10 Expert and
10 Extreme**. Exactly 10 Hard and 10 Expert were generated through the existing
standard batch pipeline and admitted through fresh verification. The existing
classification, registry thresholds and proof requirements were not relaxed.
Expert has no arbitrary rating cutoff below Extreme: its fresh Deep
classification must still be Expert, including the existing additional Extreme
gates.

All original 28 records are equal to their original complete records. The
certification, solver, Sudoku and rating source directories are unchanged.
Production SHA-256:
`0eb52e596bbe2c5cab344ebf86e40590c7ef88ee4228e02dfb20bd0c94731274`.

Generation parameters, seeds, selected IDs and quality-control evidence are in
[`reports/phase11/content-qc.json`](../reports/phase11/content-qc.json).

## Validation

- Python: **489 tests passed**, 281.935 seconds.
- Frontend Node tests: **59 passed**, no failures or skips.
- The standalone production validator freshly revalidated **48/48 puzzles**
  in 47.5 seconds.
- Real browsers: **36 scenario groups passed** across Chromium 153.0.8010.12,
  WebKit 26.6 and Firefox 155.0.
- Responsive rendering: **56 cases passed**, 14 viewports in light/dark themes
  on Chromium and WebKit. Profile and statistics screenshots were also reviewed.
- Scenarios include mandatory profile validation/editing, all five actual
  production levels, separate saves, explicit resume, hidden-page timing,
  exhaustion, reveal/Undo, restart history, completion deduplication, three
  mistake-check modes, legacy migration, blocked/corrupt storage, writer transfer
  between tabs and navigation, failed/empty database loading and built Pages
  paths under a project prefix.
- `git diff --check` passed. All **411 pre-existing untracked user files** retain
  their recorded SHA-256 hashes; none were included in the implementation commit.

The updated browser harness replaces obsolete automatic-start, wall-clock and
replay expectations with the agreed player flows. Core Sudoku interaction and
responsive geometry assertions remain. Compact machine-readable results are in
[`reports/phase11/player-validation.json`](../reports/phase11/player-validation.json).
Full logs, screenshots and project-local QA tools remain under
`reports/release-hard-expert-profile-20261007/` and are not release assets.

Actual installed Chrome/Edge were unavailable. Chromium is an engine test, not
a claim of an installed Edge run. WebKit on Windows is not physical Safari/iOS;
touch hardware, iOS browser bars and real device behavior were not validated.

## Publication boundary

The existing Pages workflow validates the production database, tests the web
app, builds `dist/` and deploys after a push to `main`. The current custom domain
is `extreme.onedesire.ru`. Its DNS and Pages health checks are valid, but the
certificate remains in `new` state and HTTPS fails hostname verification.
Saving the same domain and a controlled remove/re-add provisioning retry did
not resolve certificate issuance. DNS, build source and HTTPS enforcement were
not changed. The original domain was restored and HTTP availability verified.

Publishing the new Web-Lock-dependent application to that HTTP origin is held.
Changing origin or forcing HTTP-to-HTTPS redirection also requires considering
existing browser-local saves; they do not transfer automatically across origins.
