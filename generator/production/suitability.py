"""Certification-suitability heuristic: PRIORITIZATION ONLY, never proof.

Why this is not a certificate
-----------------------------
The score is computed exclusively from preliminary, bounded Deep-rating metrics
(greedy Human Solver path, bounded required-level search, observed bottlenecks).
None of these is a proof that no easier logical path exists; only the exhaustive
or Stuck-State-Lemma evidence produced by ``certify_puzzle`` is. The score
therefore only decides the ORDER in which candidates are spent expensive
certification time on, and which ones are skipped from the production quota.

* It never returns, sets or implies a certification status (the assessment has no
  status field; the batch keeps ``certification.status = "NOT_ATTEMPTED"`` until a
  real certifier run happens).
* A high score can still end in CERTIFICATION_TIMEOUT; a low score could still be
  certifiable. Being skipped is a budget decision recorded in the research archive.
* Nothing here is stored in production records.

Calibration (Phase 9 planning probe, 100 Deep-30..35 candidates, unchanged
certifier): Deep required rating 30 -> 90 % certified, 35 -> 52 %, >= 36 never
conclusive because the Stuck-State-Lemma is only defined for thresholds < 36 and
the exhaustive fallback does not finish. Hence the band preference
30 (AIC) > 32 (Nice Loop) > 35 (Grouped AIC), and >= 36 is skipped from the
production quota (archived as research, ``OUT_OF_CONCLUSIVE_SCOPE``).
"""
from dataclasses import dataclass, field

from .models import Phase9Reason

SUITABILITY_VERSION = 1

# Measured/derived prior that the default certifier finishes conclusively.
BAND_SCORE = {30.0: 1.00, 32.0: 0.80, 35.0: 0.55, 36.0: 0.05}
EXTREME_FLOOR = 30.0
# First threshold that the Stuck-State Lemma cannot prove (T >= 36 needs U >= 39);
# U == 36 is in SSL scope (T = 35) but has never been observed conclusive.
CONCLUSIVE_SCOPE_LIMIT = 36.0
HIGH_DIFFICULTIES = ("Extreme", "Ultra Extreme")


@dataclass(frozen=True)
class SuitabilityAssessment:
    """Ordering information only. Deliberately has NO status/certified field."""
    score: float
    eligible: bool
    skip_reason: Phase9Reason | None = None
    detail: str = ""
    components: dict = field(default_factory=dict)
    version: int = SUITABILITY_VERSION

    def to_dict(self):
        value = {"score": self.score, "version": self.version, "eligible": self.eligible,
                 "components": dict(self.components)}
        if self.skip_reason is not None:
            value["skipReason"] = self.skip_reason.value
            value["detail"] = self.detail
        return value


def features_from_generated(puzzle):
    """Deep metrics of a GeneratedPuzzle as the plain feature dict used below."""
    result = puzzle.difficulty_result
    return {
        "requiredRating": result.hardest_required_rating,
        "difficulty": result.difficulty_class,
        "mode": result.mode,
        "requiredLevelVerified": bool(result.required_level_verified),
        "humanSolved": bool(result.solved and not result.invalid and not result.used_backtracking
                            and not result.guesses),
        "observedHardestRating": result.hardest_rating,
        "trueBottlenecks": result.true_bottleneck_count,
        "advancedSteps": result.advanced_steps,
        "longestChain": result.longest_chain,
        "alsSteps": result.als_steps,
        "forcingSteps": result.forcing_steps,
        "clues": puzzle.clues,
        "minimal": puzzle.minimal,
    }


def _number(value, default=0):
    return value if type(value) in (int, float) else default


def assess_suitability(features, *, include_high=False):
    """Score a candidate for certification priority (higher = try earlier).

    ``features`` is the dict from ``features_from_generated`` (archive ``deep``).
    Skips (eligible=False) are prioritization decisions only.
    """
    required = features.get("requiredRating")
    difficulty = features.get("difficulty")
    if not features.get("humanSolved", True):
        return SuitabilityAssessment(0.0, False, Phase9Reason.HUMAN_UNSOLVED,
                                     "Deep human path did not solve the puzzle")
    if features.get("mode") not in (None, "deep") or not features.get("requiredLevelVerified") or required is None:
        return SuitabilityAssessment(0.0, False, Phase9Reason.HUMAN_UNSOLVED,
                                     "No verified Deep required level")
    required = float(required)
    if required < EXTREME_FLOOR or difficulty not in HIGH_DIFFICULTIES:
        return SuitabilityAssessment(0.0, False, Phase9Reason.TOO_EASY,
                                     f"Deep required rating {required:g}, class {difficulty}")
    bottlenecks = _number(features.get("trueBottlenecks"))
    advanced = _number(features.get("advancedSteps"))
    clues = _number(features.get("clues"), 26)
    longest = _number(features.get("longestChain"))
    heavy = _number(features.get("alsSteps")) + _number(features.get("forcingSteps"))
    components = {
        "band": round(100.0 * BAND_SCORE.get(required, 0.0), 6),
        # Certification still needs >= 2 certified bottlenecks and >= 3 advanced steps.
        "bottlenecks": round(5.0 * min(bottlenecks, 6) / 6, 6),
        "advanced": round(3.0 * min(advanced, 20) / 20, 6),
        # Product tie-break toward the harder conclusive bands.
        "harderBand": 2.0 if required in (32.0, 35.0) else 0.0,
        # Clue count is NOT an objective; only a mild preference for fewer.
        "clues": round(-0.2 * max(0, clues - 26), 6),
        # Unvalidated small tie-breaks: long chains and ALS/forcing dependence on
        # the observed path correlate with chain/ALS enumeration limits (SSL G4).
        "longChain": round(-0.1 * max(0, longest - 10), 6),
        "alsForcing": -2.0 if heavy else 0.0,
    }
    score = round(sum(components.values()), 6)
    if required >= CONCLUSIVE_SCOPE_LIMIT and not include_high:
        return SuitabilityAssessment(score, False, Phase9Reason.OUT_OF_CONCLUSIVE_SCOPE,
            f"Deep required rating {required:g} >= {CONCLUSIVE_SCOPE_LIMIT:g}: not conclusively "
            "certifiable today; archived as research", components)
    return SuitabilityAssessment(score, True, None, "", components)


def priority_key(entry):
    """Stable order: score descending, then content ID."""
    return (-entry["suitability"]["score"], entry["id"])
