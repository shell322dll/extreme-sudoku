"""Batch report counters (one definition for live runs and recomputation).

Every counter is derived from two sources only: the per-seed generation
checkpoints (generator attempts and attempt-level rejections) and the final
archive state of the run's rated candidates. The funnel is monotone:

    generated >= unique >= rated >= extremeCandidates >= eligible >= shortlisted
              >= certificationAttempts >= certified >= selected

* generated              generator attempts (``GenerationStats.attempts``; a final attempt cut by
                         the timeout is included but has no outcome).
* unique                 completed attempts whose puzzle passed the exact uniqueness check. The
                         generator only removes clues while the puzzle stays unique, so NOT_UNIQUE is
                         rare; OUTSIDE_CLUE_RANGE is rejected before the check and is excluded.
* rated                  puzzles that received a human rating (Quick and/or Deep):
                         generator TOO_EASY + HUMAN_UNSOLVED + rated candidates (records).
* deepRated              number of Deep-rating calls (informational, <= rated is not guaranteed
                         because Deep can run more than once per attempt in quick_then_deep).
* reusedFromArchive      rated candidates re-evaluated from the archive (``--reuse-archive``; row
                         ``seed: "archive"``). Such rows have no generator counters (generated =
                         unique = 0), so the funnel's first two steps apply to generation rows only.
* extremeCandidates      Deep-rated Extreme/Ultra records returned by the generator (incl. off-target).
* inBand30to35           extremeCandidates whose Deep required rating is 30, 32 or 35.
* duplicatesInRun        records already produced by an earlier seed of this run.
* alreadyArchived        records skipped because the archive already holds a final result.
* eligible               candidates that passed the prefilter (duplicates, suitability, near-duplicates).
* shortlisted            eligible candidates placed on the certification shortlist.
* probed / probeCertified  candidates with probe evidence / probe-certified.
* certificationAttempts  candidates with any certifier run (probe or default budget).
* certified              default-budget, production-eligible results.
* inconclusive           certifier runs that did not finish conclusively (CERTIFICATION_INCONCLUSIVE
                         **plus** CERTIFICATION_TIMEOUT); ``timeouts`` is the timeout sub-count.
* selected               certified, fast and diverse candidates offered to production-merge.
* rejected               every non-selected outcome by Phase 9 reason, from all stages;
                         ``rejectedByStage`` splits it into generation / prefilter / certification.
* generationYield = certified / generated; certificationYield = certified / certificationAttempts.
"""
from collections import Counter

from .archive import is_certified_summary
from .models import Phase9Reason

IN_BAND = (30.0, 32.0, 35.0)
FIELDS = ("generated", "unique", "rated", "deepRated", "reusedFromArchive", "extremeCandidates", "inBand30to35",
          "duplicatesInRun", "alreadyArchived", "eligible", "shortlisted", "probed", "probeCertified",
          "certificationAttempts", "certified", "inconclusive", "timeouts", "selected")
SHORTLIST_STAGES = ("shortlist", "probe", "certification")
GENERATOR_RATED_REASONS = (Phase9Reason.TOO_EASY.value, Phase9Reason.HUMAN_UNSOLVED.value)


def _row(label):
    return {"seed": label, **dict.fromkeys(FIELDS, 0), "rejected": Counter(),
            "rejectedByStage": {"generation": 0, "prefilter": 0, "certification": 0}}


def _reject(row, reason, stage):
    row["rejected"][reason] += 1
    row["rejectedByStage"][stage] += 1


def _count_candidate(row, state):
    rejection = (state.get("rejection") or {}).get("reason")
    stage = state.get("stage")
    shortlisted = stage in SHORTLIST_STAGES
    if shortlisted or rejection == Phase9Reason.NOT_SHORTLISTED.value:
        row["eligible"] += 1
    if shortlisted:
        row["shortlisted"] += 1
    probe = state.get("probe")
    final = state.get("certification") or {}
    attempted_final = final.get("status", "NOT_ATTEMPTED") != "NOT_ATTEMPTED"
    if probe:
        row["probed"] += 1
        if is_certified_summary(probe):
            row["probeCertified"] += 1
    if probe or attempted_final:
        row["certificationAttempts"] += 1
    if is_certified_summary(final):
        row["certified"] += 1
    if rejection in (Phase9Reason.CERTIFICATION_INCONCLUSIVE.value, Phase9Reason.CERTIFICATION_TIMEOUT.value):
        row["inconclusive"] += 1
        if rejection == Phase9Reason.CERTIFICATION_TIMEOUT.value:
            row["timeouts"] += 1
    if state.get("selected"):
        row["selected"] += 1
    if rejection:
        # Shortlisted outcomes (incl. target/budget skips) belong to the certification stage.
        _reject(row, rejection, "certification" if (shortlisted or probe or attempted_final) else "prefilter")


def _finish(row):
    row["rejected"] = dict(sorted(row["rejected"].items()))
    row["generationYield"] = row["certified"] / row["generated"] if row["generated"] else 0.0
    row["certificationYield"] = (row["certified"] / row["certificationAttempts"]
                                 if row["certificationAttempts"] else 0.0)
    return row


def compute_counters(sources, state_by_id, *, skipped_ids=()):
    """Per-source rows and a total row.

    ``sources``: list of (label, checkpoint) in processing order; a checkpoint is a
    generation checkpoint dict, or ``{"entries": [...]}`` for archive reuse (no
    generator counters). ``state_by_id``: final entry state of candidates processed
    by the run. ``skipped_ids``: IDs skipped because the archive was already final.
    """
    skipped_ids = set(skipped_ids)
    seen, rows = set(), []
    for label, checkpoint in sources:
        row = _row(label)
        row["generated"] = checkpoint.get("attempts", 0)
        row["unique"] = checkpoint.get("unique", 0)
        row["deepRated"] = checkpoint.get("deepRated", 0)
        attempt_rejections = checkpoint.get("attemptRejections", {})
        for reason, count in attempt_rejections.items():
            row["rejected"][reason] += count
            row["rejectedByStage"]["generation"] += count
        records = [entry for entry in checkpoint.get("entries", []) if "deep" in entry]
        row["rated"] = sum(attempt_rejections.get(reason, 0) for reason in GENERATOR_RATED_REASONS) + len(records)
        if label == "archive":
            row["reusedFromArchive"] = len(records)
        for entry in records:
            row["extremeCandidates"] += 1
            if entry["deep"].get("requiredRating") in IN_BAND:
                row["inBand30to35"] += 1
            if entry["id"] in seen:
                row["duplicatesInRun"] += 1
                _reject(row, Phase9Reason.DUPLICATE.value, "prefilter")
                continue
            seen.add(entry["id"])
            if entry["id"] in skipped_ids or entry["id"] not in state_by_id:
                row["alreadyArchived"] += 1
                continue
            _count_candidate(row, state_by_id[entry["id"]])
        rows.append(_finish(row))
    total = _row("total")
    for row in rows:
        for name in FIELDS:
            total[name] += row[name]
        total["rejected"].update(row["rejected"])
        for stage, count in row["rejectedByStage"].items():
            total["rejectedByStage"][stage] += count
    total = _finish(total)
    total.pop("seed")
    return rows, total
