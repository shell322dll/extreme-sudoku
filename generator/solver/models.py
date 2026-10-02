"""Explainable logical deductions and single-path solver results."""

from dataclasses import dataclass, field


@dataclass(frozen=True, order=True)
class CandidateNode:
    """An OR of one digit's candidates; singleton nodes are ordinary candidates."""

    cells: tuple[int, ...]
    digit: int


@dataclass(frozen=True)
class ChainLink:
    source: CandidateNode
    target: CandidateNode
    kind: str
    reason: tuple = ()


@dataclass(frozen=True)
class Chain:
    nodes: tuple
    links: tuple
    closed: bool = False

    @property
    def length(self):
        """Number of inference links (not number of cells)."""
        return len(self.links)


@dataclass(frozen=True)
class LogicStep:
    technique: str
    rating: float
    placements: tuple[tuple[int, int], ...] = ()
    eliminations: tuple[tuple[int, int], ...] = ()
    premises: tuple = ()
    explanation: str = ""
    search_complexity: float = 0.0
    chain: Chain | None = None
    grouped_nodes: tuple = ()
    als: tuple = ()
    assumptions: tuple = ()
    contradiction: tuple = ()

    @property
    def chain_length(self):
        """Graph/RCC link count, or longest dependency depth in a forcing proof."""
        return self.chain.length if self.chain else max(
            (proof.depth for proof in self.assumptions), default=0)


@dataclass
class HumanSolveResult:
    """Metrics describe this greedy path, not mandatory difficulty certification.

    ``invalid`` means a local contradiction was detected. A stuck result does
    not assert existence or uniqueness: those belong to the exact solver.
    """

    solved: bool
    stuck: bool
    invalid: bool
    grid: list[int]
    steps: list[LogicStep] = field(default_factory=list)
    hardest_technique: str | None = None
    max_rating: float = 0.0
    total_score: float = 0.0
    technique_counts: dict[str, int] = field(default_factory=dict)
    advanced_steps: int = 0
    bottlenecks: list = field(default_factory=list)
    used_backtracking: bool = False
    guesses: int = 0
    intermediate_steps: int = 0
    chain_step_count: int = 0
    longest_chain: int = 0
    als_step_count: int = 0
    forcing_step_count: int = 0
