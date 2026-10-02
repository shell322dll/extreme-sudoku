"""Quick path metrics and bounded Deep analysis, separate from detectors."""
from math import log1p
from .config import DifficultyConfig
from .models import DifficultyResult
from .profiles import PROFILES, solver_for_profile, status
from .state_analysis import StateAnalyzer
from .mandatory import required_level
from .bottlenecks import detect_bottlenecks, summarize_bottlenecks
from .classification import classify
from ..solver.human_solver import HumanSolver, apply_step
from ..sudoku.candidates import SudokuState
from ..sudoku.grid import validate_grid

def chain_complexity(step, config):
    branches = sum(max(0, len(inference.parents) - 1)
                   for proof in step.assumptions for inference in proof.inferences)
    return (config.chain_length_factor * step.chain_length
            + config.grouped_node_factor * len(step.grouped_nodes)
            + config.branching_factor * (branches + max(0, len(step.assumptions) - 1)))

def step_score(step, config):
    return (config.registry.weight_of(step.technique) ** config.score_exponent
            + chain_complexity(step, config)
            + config.als_bonus * bool(step.als)
            + config.forcing_bonus * bool(step.assumptions)
            + config.search_complexity_factor * log1p(max(0, step.search_complexity)))

def path_metrics(puzzle, solved, config, mode="quick"):
    """Summarize the actual path; no claims of mandatory complexity here."""
    steps = solved.steps
    ratings = [config.registry.rating_of(s.technique) for s in steps]
    hardest = min(steps, key=lambda s: (-config.registry.rating_of(s.technique), s.technique), default=None)
    bins = [0] * config.distribution_bins
    peaks = []
    for i, rating in enumerate(ratings):
        if rating >= config.advanced_threshold:
            bins[min(len(bins)-1, i * len(bins) // max(1, len(steps)))] += 1
            if i == 0 or ratings[i-1] < config.advanced_threshold:
                peaks.append(i)
    signatures = []
    if steps:
        state = SudokuState(puzzle)
        for step in steps:
            signatures.append(state.signature())
            state = apply_step(state, step)
    total = sum(step_score(s, config) for s in steps)
    maximum = max(ratings, default=0.)
    return DifficultyResult(
        solved=solved.solved, mode=mode, invalid=solved.invalid,
        hardest_technique=hardest.technique if hardest else None, hardest_rating=maximum,
        rating=maximum + config.total_rating_factor * log1p(total), total_score=total,
        step_count=len(steps), advanced_steps=sum(r >= config.advanced_threshold for r in ratings),
        extreme_steps=sum(r >= config.extreme_step_threshold for r in ratings),
        chain_steps=sum(bool(s.chain or s.assumptions) for s in steps),
        longest_chain=max((s.chain_length for s in steps), default=0),
        chain_complexity=sum(chain_complexity(s, config) for s in steps),
        als_steps=sum(bool(s.als) for s in steps), forcing_steps=sum(bool(s.assumptions) for s in steps),
        difficulty_profile=ratings, peak_rating=maximum, high_peak_count=len(peaks), peak_positions=peaks,
        late_peak_count=sum(i >= len(steps)*config.late_fraction for i in peaks),
        advanced_distribution=bins, distributed_advanced_steps=sum(bool(n) for n in bins),
        state_signatures=signatures, clue_count=sum(bool(n) for n in puzzle),
        used_backtracking=solved.used_backtracking, guesses=solved.guesses)

class DifficultyAnalyzer:
    def __init__(self, config=None):
        self.config = config or DifficultyConfig()
        self.state_analyzer = StateAnalyzer(self.config)

    def quick(self, puzzle):
        puzzle = validate_grid(puzzle)
        weights = {e.name:e.base_rating for e in self.config.registry.entries}
        solved = HumanSolver(weights=weights, config=self.config.search).solve(puzzle)
        return classify(path_metrics(puzzle, solved, self.config),self.config)

    def deep(self,puzzle,*,check_unique=False):
        puzzle=validate_grid(puzzle)
        required=required_level(puzzle,config=self.config)
        profile_runs={p.name:solver_for_profile(p,self.config).solve(puzzle) for p in PROFILES}
        # Rate the lowest successful tested path, not a gratuitously harder path.
        solved=required.solution if required.solved else profile_runs["Extreme"]
        result=path_metrics(puzzle,solved,self.config,mode="deep")
        result.profile_statuses={name:status(run) for name,run in profile_runs.items()}
        result.threshold_results=list(required.attempts)
        result.hardest_required_rating=required.rating
        result.hardest_required_technique=required.technique
        result.minimum_tier=required.tier
        result.required_level_verified=required.verified
        self.state_analyzer.config=self.config
        if not result.invalid:
            result.bottlenecks=detect_bottlenecks(puzzle,solved.steps,analyzer=self.state_analyzer)
            summarize_bottlenecks(result,self.config)
        result.rating=0. if required.rating is None else (
            required.rating + self.config.total_rating_factor*log1p(result.total_score)
            + self.config.bottleneck_rating_factor*result.bottleneck_severity
            + self.config.distribution_rating_factor*result.distributed_advanced_steps)
        classify(result,self.config)
        if check_unique:
            from .precertification import check_uniqueness
            check_uniqueness(puzzle,result,self.config)
        return result

def analyze_difficulty(puzzle, *, mode="deep", config=None, check_unique=True):
    if mode not in ("quick","deep"):
        raise ValueError("Unknown analysis mode")
    analyzer=DifficultyAnalyzer(config)
    return analyzer.quick(puzzle) if mode=="quick" else analyzer.deep(puzzle,check_unique=check_unique)
