"""Certificates distinguish witnesses, exhaustive failures, and unfinished search."""
from dataclasses import asdict, dataclass, field
from enum import Enum
from .config import CERTIFICATION_VERSION


class CertificationStatus(str, Enum):
    REJECTED = "REJECTED"
    UNRATED = "UNRATED"
    PRELIMINARY = "PRELIMINARY"
    CERTIFIED_EXTREME = "CERTIFIED_EXTREME"
    CERTIFIED_ULTRA_EXTREME = "CERTIFIED_ULTRA_EXTREME"
    SEARCH_INCONCLUSIVE = "SEARCH_INCONCLUSIVE"
    CERTIFICATION_TIMEOUT = "CERTIFICATION_TIMEOUT"
    INVALID_PROOF = "INVALID_PROOF"


class SearchStatus(str, Enum):
    SOLVED = "SOLVED"
    PROVEN_UNSOLVABLE_WITHIN_MODEL = "PROVEN_UNSOLVABLE_WITHIN_MODEL"
    INCONCLUSIVE_BUDGET = "INCONCLUSIVE_BUDGET"
    ERROR = "ERROR"


class FailureReason(str, Enum):
    INVALID_FORMAT = "INVALID_FORMAT"
    SOLUTION_MISMATCH = "SOLUTION_MISMATCH"
    NOT_UNIQUE = "NOT_UNIQUE"
    NOT_MINIMAL = "NOT_MINIMAL"
    HUMAN_UNSOLVED = "HUMAN_UNSOLVED"
    INVALID_LOGIC_PROOF = "INVALID_LOGIC_PROOF"
    NONDETERMINISTIC_REPLAY = "NONDETERMINISTIC_REPLAY"
    STORED_PATH_MISMATCH = "STORED_PATH_MISMATCH"
    SEARCH_INCONCLUSIVE = "SEARCH_INCONCLUSIVE"
    SEARCH_TIMEOUT = "SEARCH_TIMEOUT"
    INCONCLUSIVE_NODE_LIMIT = "INCONCLUSIVE_NODE_LIMIT"
    RATING_BELOW_EXTREME = "RATING_BELOW_EXTREME"
    INSUFFICIENT_BOTTLENECKS = "INSUFFICIENT_BOTTLENECKS"
    INSUFFICIENT_ADVANCED_STEPS = "INSUFFICIENT_ADVANCED_STEPS"
    DUPLICATE = "DUPLICATE"


@dataclass
class EnumerationResult:
    steps: list = field(default_factory=list)
    complete: bool = True
    limit_reasons: list[str] = field(default_factory=list)
    work: int = 0


@dataclass
class ThresholdResult:
    threshold: float
    status: SearchStatus
    path: list = field(default_factory=list)
    states_explored: int = 0
    states_generated: int = 0
    limit_reasons: list[str] = field(default_factory=list)
    elapsed_seconds: float = field(default=0.0, compare=False)
    error: str | None = None
    proof_seconds: float = field(default=0.0, compare=False)
    cache_hits: int = 0
    # False as soon as any limit reason appears: the result can then only be
    # SOLVED or INCONCLUSIVE_BUDGET, never PROVEN_UNSOLVABLE_WITHIN_MODEL.
    negative_proof_possible: bool = True
    # How a PROVEN_UNSOLVABLE_WITHIN_MODEL result was established:
    # "EXHAUSTIVE_SEARCH" or "STUCK_STATE_SUPERSET_LEMMA" (None otherwise).
    negative_proof_kind: str | None = None
    # Deterministic, JSON-native SSL evidence (closure signature/length, guards,
    # lemma version, source fingerprint); empty for exhaustive proofs.
    negative_certificate: dict = field(default_factory=dict)
    # Diagnostic counters and timings; not certificate evidence.
    telemetry: dict = field(default_factory=dict, compare=False)


@dataclass
class CertificationResult:
    puzzle_id: str = ""
    puzzle: str = ""
    solution: str = ""
    clues: int = 0
    status: CertificationStatus = CertificationStatus.UNRATED
    unique: bool = False
    minimal: bool | None = None
    human_solved: bool = False
    proof_valid: bool = False
    reproducible: bool = False
    search_status: SearchStatus = SearchStatus.INCONCLUSIVE_BUDGET
    minimum_required_rating: float | None = None
    # Kind of the negative evidence immediately below the certified minimum.
    negative_proof_kind: str | None = None
    minimum_required_tier: str | None = None
    certified_bottlenecks: int = 0
    certified_path: list = field(default_factory=list)
    observed_path: list = field(default_factory=list)
    observed_upper_rating: float | None = None
    threshold_results: list[ThresholdResult] = field(default_factory=list)
    bottlenecks: list = field(default_factory=list)
    late_game_bottlenecks: int = 0
    max_trivial_gap: int = 0
    advanced_steps: int = 0
    longest_chain: int = 0
    distributed_bins: int = 0
    states_explored: int = 0
    elapsed_seconds: float = field(default=0.0, compare=False)
    failure_reasons: list[FailureReason] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    stage_seconds: dict = field(default_factory=dict, compare=False)
    config_fingerprint: str = ""
    algorithm_fingerprint: str = ""
    certification_version: str = CERTIFICATION_VERSION
    fresh: bool = True
    cache_hits: int = 0
    search_telemetry: dict = field(default_factory=dict, compare=False)
    scope: str = "All implemented pattern rules, simple candidate chains, disjoint ALS chains, and single-assumption clause propagation; budgets never count as exhaustive failure."

    @property
    def production_eligible(self):
        return (self.status in (CertificationStatus.CERTIFIED_EXTREME,
                               CertificationStatus.CERTIFIED_ULTRA_EXTREME)
                and self.unique and self.human_solved and self.proof_valid and self.reproducible
                and self.search_status == SearchStatus.SOLVED
                and self.minimum_required_rating is not None and not self.failure_reasons)

    def to_dict(self):
        return asdict(self)
