"""Structured Phase 9 rejection reasons and the mapping from certifier results.

The mapping is lossless in the sense that the raw certifier status and failure
reasons are always stored next to the Phase 9 reason (``detail``/``rawStatus``).
"""
from enum import Enum

from ..certification.models import CertificationStatus, FailureReason
from ..models import RejectionReason

ARCHIVE_KIND = "phase9-candidate-archive"
ARCHIVE_VERSION = 1
REPORT_KIND = "phase9-batch-report"
MERGE_REPORT_KIND = "phase9-merge-report"

# Statuses that are allowed into production (only after a FRESH default-config run).
PRODUCTION_STATUSES = (CertificationStatus.CERTIFIED_EXTREME.value,
                       CertificationStatus.CERTIFIED_ULTRA_EXTREME.value)

# The archive's placeholder for "no certification was run". It is not a
# CertificationStatus and can never be mistaken for one.
NOT_ATTEMPTED = "NOT_ATTEMPTED"


class Phase9Reason(str, Enum):
    INVALID = "INVALID"
    NOT_UNIQUE = "NOT_UNIQUE"
    NOT_MINIMAL = "NOT_MINIMAL"
    OUTSIDE_CLUE_RANGE = "OUTSIDE_CLUE_RANGE"
    TOO_EASY = "TOO_EASY"
    HUMAN_UNSOLVED = "HUMAN_UNSOLVED"
    DUPLICATE = "DUPLICATE"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    OUT_OF_CONCLUSIVE_SCOPE = "OUT_OF_CONCLUSIVE_SCOPE"
    CERTIFICATION_INCONCLUSIVE = "CERTIFICATION_INCONCLUSIVE"
    CERTIFICATION_TIMEOUT = "CERTIFICATION_TIMEOUT"
    PROOF_INVALID = "PROOF_INVALID"
    INSUFFICIENT_BOTTLENECKS = "INSUFFICIENT_BOTTLENECKS"
    INSUFFICIENT_ADVANCED_STEPS = "INSUFFICIENT_ADVANCED_STEPS"
    NOT_SHORTLISTED = "NOT_SHORTLISTED"
    NOT_SELECTED_SLOW_CERTIFICATE = "NOT_SELECTED_SLOW_CERTIFICATE"
    NOT_SELECTED_TARGET_REACHED = "NOT_SELECTED_TARGET_REACHED"
    NOT_SELECTED_BUDGET = "NOT_SELECTED_BUDGET"


# Reasons that depend only on the puzzle content (and the fixed algorithms), so a
# later run can never reach a different conclusion. Everything else (selection,
# budget, scope switches, duplicates relative to a changing production DB) stays
# re-evaluable on the next run.
# OUTSIDE_CLUE_RANGE is excluded: it depends on the requested clue range.
CONTENT_TERMINAL_REASONS = frozenset({Phase9Reason.INVALID, Phase9Reason.NOT_UNIQUE,
    Phase9Reason.NOT_MINIMAL, Phase9Reason.TOO_EASY, Phase9Reason.HUMAN_UNSOLVED})


GENERATOR_REASON = {
    RejectionReason.NOT_UNIQUE: Phase9Reason.NOT_UNIQUE,
    RejectionReason.OUTSIDE_CLUE_RANGE: Phase9Reason.OUTSIDE_CLUE_RANGE,
    RejectionReason.HUMAN_UNSOLVED: Phase9Reason.HUMAN_UNSOLVED,
    # With an Extreme/Ultra target, WRONG_DIFFICULTY without a record means the
    # puzzle rated below Extreme (harder off-target puzzles are kept as records).
    RejectionReason.WRONG_DIFFICULTY: Phase9Reason.TOO_EASY,
    RejectionReason.DUPLICATE: Phase9Reason.DUPLICATE,
}

FAILURE_REASON = {
    FailureReason.INVALID_FORMAT: Phase9Reason.INVALID,
    FailureReason.SOLUTION_MISMATCH: Phase9Reason.INVALID,
    FailureReason.NOT_UNIQUE: Phase9Reason.NOT_UNIQUE,
    FailureReason.NOT_MINIMAL: Phase9Reason.NOT_MINIMAL,
    FailureReason.HUMAN_UNSOLVED: Phase9Reason.HUMAN_UNSOLVED,
    FailureReason.INVALID_LOGIC_PROOF: Phase9Reason.PROOF_INVALID,
    FailureReason.NONDETERMINISTIC_REPLAY: Phase9Reason.PROOF_INVALID,
    FailureReason.STORED_PATH_MISMATCH: Phase9Reason.PROOF_INVALID,
    FailureReason.SEARCH_INCONCLUSIVE: Phase9Reason.CERTIFICATION_INCONCLUSIVE,
    FailureReason.SEARCH_TIMEOUT: Phase9Reason.CERTIFICATION_TIMEOUT,
    FailureReason.INCONCLUSIVE_NODE_LIMIT: Phase9Reason.CERTIFICATION_INCONCLUSIVE,
    FailureReason.RATING_BELOW_EXTREME: Phase9Reason.TOO_EASY,
    FailureReason.INSUFFICIENT_BOTTLENECKS: Phase9Reason.INSUFFICIENT_BOTTLENECKS,
    FailureReason.INSUFFICIENT_ADVANCED_STEPS: Phase9Reason.INSUFFICIENT_ADVANCED_STEPS,
    FailureReason.DUPLICATE: Phase9Reason.DUPLICATE,
}

STATUS_REASON = {
    CertificationStatus.CERTIFICATION_TIMEOUT: Phase9Reason.CERTIFICATION_TIMEOUT,
    CertificationStatus.SEARCH_INCONCLUSIVE: Phase9Reason.CERTIFICATION_INCONCLUSIVE,
    CertificationStatus.INVALID_PROOF: Phase9Reason.PROOF_INVALID,
    CertificationStatus.PRELIMINARY: Phase9Reason.CERTIFICATION_INCONCLUSIVE,
}


def reason_for_status(status, failure_reasons=()):
    """Phase 9 reason for a (non-certified) certifier outcome; None if certified.

    Budget/limit outcomes are never upgraded: TIMEOUT stays CERTIFICATION_TIMEOUT
    and every other unfinished search stays CERTIFICATION_INCONCLUSIVE.
    """
    status = CertificationStatus(status)
    reasons = [FailureReason(r) for r in failure_reasons]
    if status.value in PRODUCTION_STATUSES and not reasons:
        return None
    if status in STATUS_REASON:
        return STATUS_REASON[status]
    for reason in reasons:
        return FAILURE_REASON[reason]
    if status == CertificationStatus.UNRATED:
        return Phase9Reason.HUMAN_UNSOLVED
    # REJECTED without a reason, or a certified label with failure reasons:
    # never treat as a success.
    return Phase9Reason.CERTIFICATION_INCONCLUSIVE


def reason_for_result(result):
    """Reason for a CertificationResult; None only for production-eligible results."""
    if result.production_eligible:
        return None
    reason = reason_for_status(result.status, result.failure_reasons)
    return reason if reason is not None else Phase9Reason.PROOF_INVALID


def rejection(reason, detail="", **extra):
    value = {"reason": Phase9Reason(reason).value, "detail": detail}
    value.update(extra)
    return value
