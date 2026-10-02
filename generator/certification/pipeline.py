"""Fresh mathematical gates surrounding solution-independent logical analysis."""
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

from ..rating.registry import DEFAULT_REGISTRY
from ..rating.bottlenecks import pattern_key
from ..solver.exact_solver import count_solutions, solve_one
from ..solver.human_solver import HumanSolver, apply_step
from ..sudoku.candidates import SudokuState
from ..sudoku.grid import validate_grid, is_complete
from .config import CertificationConfig, CERTIFICATION_VERSION
from .models import CertificationResult, CertificationStatus as CS, SearchStatus as SS, FailureReason as FR
from .enumeration import StepEnumerator
from .search import minimax_descent
from .transitions import SudokuTransitions
from .proofs import validate_path, validate_step


def algorithm_fingerprint():
    """Bind evidence to actual algorithms, not merely a manually updated version."""
    root = Path(__file__).resolve().parents[1]
    digest = sha256(CERTIFICATION_VERSION.encode())
    for folder in ("certification", "solver", "sudoku", "rating"):
        for path in sorted((root / folder).rglob("*.py")):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _grid(value, *, solution=False):
    if isinstance(value, str):
        alphabet = "123456789" if solution else "0123456789"
        if len(value) != 81 or any(c not in alphabet for c in value):
            raise ValueError("Expected an ASCII Sudoku string of length 81")
        value = [int(c) for c in value]
    result = validate_grid(value)
    if solution and not is_complete(result):
        raise ValueError("Solution is not a complete valid Sudoku")
    return result


def _same_path(first, second):
    def normalize(path):
        return json.dumps([asdict(s) if not isinstance(s, dict) else s for s in path],
                          sort_keys=True, separators=(",", ":"))
    return normalize(first) == normalize(second)


def certify_bottlenecks(grid, path, config, deadline, *, enumerator=None):
    """A valid high witness plus exhaustive absence of cheap moves proves a crisis.

    This proves the configured bottleneck floor, not the exact minimum step
    rating. Contiguous events and repeated proof identities merge transitively.
    ``enumerator`` may be the invocation-local enumerator of the descent, whose
    per-technique cache is keyed by the complete state signature.
    """
    enumerator = enumerator if enumerator is not None else StepEnumerator(config)
    state = SudokuState(grid)
    lower = max((e.base_rating for e in DEFAULT_REGISTRY.entries
                 if e.base_rating < config.bottleneck_threshold), default=0)
    events, patterns, reasons = [], {}, set()
    last_index, group = -2, -1
    for index, step in enumerate(path):
        if perf_counter() >= deadline:
            reasons.add("TIME_LIMIT")
            break
        if step.rating >= config.bottleneck_threshold:
            cheap = enumerator.enumerate(state, lower, deadline=deadline)
            reasons.update(cheap.limit_reasons)
            for candidate in cheap.steps:
                checked = validate_step(state, candidate, config=config)
                if not checked.valid:
                    raise ValueError("Invalid cheaper bottleneck proof: " + "; ".join(checked.errors))
            if cheap.complete and not cheap.steps:
                key = pattern_key(step)
                if index == last_index + 1:
                    chosen = events[-1]["group_id"]
                    if key in patterns and patterns[key] != chosen:
                        chosen, old = min(chosen, patterns[key]), max(chosen, patterns[key])
                        for event in events:
                            if event["group_id"] == old:
                                event["group_id"] = chosen
                        patterns = {k: chosen if v == old else v for k, v in patterns.items()}
                elif key in patterns:
                    chosen = patterns[key]
                else:
                    group += 1
                    chosen = group
                patterns[key] = chosen
                events.append({"step_index": index, "group_id": chosen,
                    "minimum_rating_lower_bound": config.bottleneck_threshold,
                    "observed_step_rating": step.rating, "genuine": True,
                    "state_signature": state.signature()})
                last_index = index
        state = apply_step(state, step)
    return events, sorted(reasons)


def classify_certificate(result, config):
    """Product labels require completed evidence, independently of clue count."""
    if not (result.unique and result.human_solved and result.proof_valid and result.reproducible
            and result.search_status == SS.SOLVED and result.minimum_required_rating is not None):
        return CS.SEARCH_INCONCLUSIVE
    if config.require_minimal and result.minimal is not True:
        result.failure_reasons.append(FR.NOT_MINIMAL)
        return CS.REJECTED
    if result.minimum_required_rating < config.extreme_threshold:
        result.failure_reasons.append(FR.RATING_BELOW_EXTREME)
        return CS.REJECTED
    if result.certified_bottlenecks < config.required_bottlenecks_extreme:
        result.failure_reasons.append(FR.INSUFFICIENT_BOTTLENECKS)
        return CS.REJECTED
    if result.advanced_steps < config.minimum_advanced_steps:
        result.failure_reasons.append(FR.INSUFFICIENT_ADVANCED_STEPS)
        return CS.REJECTED
    if (result.minimum_required_rating >= config.ultra_threshold
            and result.certified_bottlenecks >= config.required_bottlenecks_ultra
            and result.advanced_steps >= config.ultra_minimum_advanced_steps
            and result.longest_chain >= config.ultra_minimum_chain
            and result.distributed_bins >= config.ultra_minimum_distributed_bins
            and any(s.chain or s.als or s.assumptions for s in result.certified_path)):
        return CS.CERTIFIED_ULTRA_EXTREME
    return CS.CERTIFIED_EXTREME


def certify_puzzle(puzzle, solution=None, *, puzzle_id=None, config=None, fresh=True, previous_path=None):
    """No persisted certificate/rating cache is consulted, including fresh=False.

    Mathematical solution knowledge remains inside the validation stage. Search,
    enumeration, and proof validators receive only the puzzle/candidate states.
    """
    config = config or CertificationConfig()
    started, result = perf_counter(), CertificationResult()
    deadline = started + config.time_budget
    result.config_fingerprint = config.fingerprint()
    result.algorithm_fingerprint = algorithm_fingerprint()
    result.fresh = True
    stage = started

    def finish(status, *reasons):
        result.status = status
        result.failure_reasons.extend(r for r in reasons if r not in result.failure_reasons)
        result.elapsed_seconds = perf_counter() - started
        result.states_explored = sum(t.states_explored for t in result.threshold_results)
        result.cache_hits = sum(t.cache_hits for t in result.threshold_results)
        result.stage_seconds["search_proof_validation"] = sum(t.proof_seconds for t in result.threshold_results)
        return result

    def timed_out():
        return perf_counter() >= deadline

    try:
        grid = _grid(puzzle)
        result.puzzle = "".join(map(str, grid))
        result.puzzle_id = puzzle_id or "puzzle-" + sha256(result.puzzle.encode()).hexdigest()[:20]
        result.clues = sum(bool(v) for v in grid)
        if type(result.puzzle_id) is not str or not result.puzzle_id:
            raise ValueError("Puzzle ID must be a nonempty string")
        target = _grid(solution, solution=True) if solution is not None else None
        if target is not None and any(a and a != b for a, b in zip(grid, target)):
            return finish(CS.REJECTED, FR.SOLUTION_MISMATCH)
        if target is not None:
            result.solution = "".join(map(str, target))
    except (ValueError, TypeError) as exc:
        result.diagnostics.append(str(exc))
        return finish(CS.REJECTED, FR.INVALID_FORMAT)
    result.stage_seconds["format"] = perf_counter() - stage
    if timed_out():
        return finish(CS.CERTIFICATION_TIMEOUT, FR.SEARCH_TIMEOUT)

    stage = perf_counter()
    result.unique = count_solutions(grid, limit=2) == 1
    result.stage_seconds["uniqueness"] = perf_counter() - stage
    if timed_out():
        return finish(CS.CERTIFICATION_TIMEOUT, FR.SEARCH_TIMEOUT)
    if not result.unique:
        return finish(CS.REJECTED, FR.NOT_UNIQUE)
    if target is None:
        target = solve_one(grid)
        result.solution = "".join(map(str, target))
    stage = perf_counter()
    result.minimal = True
    for cell, value in enumerate(grid):
        if value:
            trial = list(grid)
            trial[cell] = 0
            if count_solutions(trial, limit=2) == 1:
                result.minimal = False
            if timed_out():
                result.minimal = None  # A partial test is not a minimality certificate.
                result.stage_seconds["minimality"] = perf_counter() - stage
                return finish(CS.CERTIFICATION_TIMEOUT, FR.SEARCH_TIMEOUT)
    result.stage_seconds["minimality"] = perf_counter() - stage
    if config.require_minimal and not result.minimal:
        return finish(CS.REJECTED, FR.NOT_MINIMAL)

    stage = perf_counter()
    first = HumanSolver(config=config.advanced_config).solve(grid)
    if timed_out():
        result.stage_seconds["human_replay"] = perf_counter() - stage
        return finish(CS.CERTIFICATION_TIMEOUT, FR.SEARCH_TIMEOUT)
    second = HumanSolver(config=config.advanced_config).solve(grid)
    result.stage_seconds["human_replay"] = perf_counter() - stage
    result.reproducible = (_same_path(first.steps, second.steps) and first.grid == second.grid
                           and first.solved == second.solved and first.invalid == second.invalid)
    result.human_solved = first.solved and not first.invalid and not first.used_backtracking and first.guesses == 0
    if timed_out():
        return finish(CS.CERTIFICATION_TIMEOUT, FR.SEARCH_TIMEOUT)
    if not result.reproducible:
        return finish(CS.REJECTED, FR.NONDETERMINISTIC_REPLAY)
    if previous_path is not None and not _same_path(first.steps, previous_path):
        result.diagnostics.append("Stored path differs from two reproducible fresh Human Solver runs.")
        return finish(CS.REJECTED, FR.STORED_PATH_MISMATCH)
    if not result.human_solved:
        return finish(CS.UNRATED, FR.HUMAN_UNSOLVED)
    if first.grid != target:
        return finish(CS.REJECTED, FR.SOLUTION_MISMATCH)
    stage = perf_counter()
    proof = validate_path(grid, first.steps, config=config)
    result.proof_valid = proof.valid
    result.stage_seconds["proof_validation"] = perf_counter() - stage
    if not proof.valid:
        result.diagnostics.extend(proof.errors)
        return finish(CS.INVALID_PROOF, FR.INVALID_LOGIC_PROOF)
    result.observed_path = list(first.steps)
    result.observed_upper_rating = first.max_rating
    if timed_out():
        return finish(CS.CERTIFICATION_TIMEOUT, FR.SEARCH_TIMEOUT)

    # A verified complete path is an upper witness. Proving failure immediately
    # below it excludes every smaller threshold (fixed, nested transition sets).
    ratings = sorted({0.0} | {e.base_rating for e in DEFAULT_REGISTRY.entries})
    stage = perf_counter()
    provider = SudokuTransitions(config)  # invocation-local caches only
    descent = minimax_descent(grid, ratings, config, provider=provider,
                              initial_witness=first.steps, deadline=deadline)
    result.threshold_results.extend(descent.threshold_results)
    result.search_telemetry = descent.cache_stats
    witness = descent.witness
    # Every accepted search witness is strictly cheaper than the previous one.
    if descent.upper is not None and descent.upper < first.max_rating:
        result.observed_path = list(witness)
        result.observed_upper_rating = descent.upper
    if not descent.conclusive:
        result.stage_seconds["alternative_search"] = perf_counter() - stage
        search = descent.last
        # A validated witness below the Extreme floor already proves rejection:
        # the true minimum is at most that witness rating. Not a certificate of
        # the minimum, so minimum_required_rating stays None.
        below_extreme = (descent.stop_reason != "ERROR" and descent.stop_reason != "INVALID_WITNESS"
                         and descent.upper is not None and descent.upper < config.extreme_threshold)
        if descent.stop_reason == "NODE_BUDGET":
            result.diagnostics.append("NODE_LIMIT")
            if below_extreme:
                return finish(CS.REJECTED, FR.RATING_BELOW_EXTREME)
            return finish(CS.SEARCH_INCONCLUSIVE, FR.SEARCH_INCONCLUSIVE, FR.INCONCLUSIVE_NODE_LIMIT)
        result.search_status = search.status
        result.diagnostics.extend(search.limit_reasons)
        if search.error:
            result.diagnostics.append(search.error)
            return finish(CS.INVALID_PROOF, FR.INVALID_LOGIC_PROOF)
        if below_extreme:
            return finish(CS.REJECTED, FR.RATING_BELOW_EXTREME)
        if timed_out() or any("TIME_LIMIT" in r for r in search.limit_reasons):
            return finish(CS.CERTIFICATION_TIMEOUT, FR.SEARCH_TIMEOUT)
        reasons = [FR.SEARCH_INCONCLUSIVE]
        if "NODE_LIMIT" in search.limit_reasons:
            reasons.append(FR.INCONCLUSIVE_NODE_LIMIT)
        return finish(CS.SEARCH_INCONCLUSIVE, *reasons)
    result.stage_seconds["alternative_search"] = perf_counter() - stage
    result.stage_seconds["search_proof_validation"] = sum(t.proof_seconds for t in result.threshold_results)
    if timed_out():
        return finish(CS.CERTIFICATION_TIMEOUT, FR.SEARCH_TIMEOUT)
    result.certified_path = list(witness)
    last = descent.last
    # Negative evidence immediately below the minimum: exhaustive search or SSL-v1.
    result.negative_proof_kind = (last.negative_proof_kind if last is not None
                                  and last.status == SS.PROVEN_UNSOLVABLE_WITHIN_MODEL
                                  else "NO_LOWER_THRESHOLD")
    result.minimum_required_rating = max((s.rating for s in witness), default=0.0)
    result.minimum_required_tier = max((DEFAULT_REGISTRY.tier_of(s.technique) for s in witness), default=0)
    result.minimum_required_tier = getattr(result.minimum_required_tier, "name", "TRIVIAL")
    result.search_status = SS.SOLVED
    stage = perf_counter()
    try:
        result.bottlenecks, limits = certify_bottlenecks(grid, witness, config, deadline,
                                                         enumerator=provider.enumerator)
    except ValueError as exc:
        result.diagnostics.append(str(exc))
        return finish(CS.INVALID_PROOF, FR.INVALID_LOGIC_PROOF)
    result.stage_seconds["bottlenecks"] = perf_counter() - stage
    if limits or timed_out():
        result.diagnostics.extend(limits)
        return finish(CS.CERTIFICATION_TIMEOUT if timed_out() else CS.SEARCH_INCONCLUSIVE,
                      FR.SEARCH_TIMEOUT if timed_out() else FR.SEARCH_INCONCLUSIVE)
    result.certified_bottlenecks = len({e["group_id"] for e in result.bottlenecks})
    result.late_game_bottlenecks = len({e["group_id"] for e in result.bottlenecks
                                      if e["step_index"] >= len(witness) * config.late_fraction})
    # TRIVIAL is the registry tier (Full House and Singles), not simply a gap
    # between crises; intermediate/advanced moves break a trivial run.
    trivial_run = 0
    for step in witness:
        trivial_run = trivial_run + 1 if DEFAULT_REGISTRY.tier_of(step.technique).name == "TRIVIAL" else 0
        result.max_trivial_gap = max(result.max_trivial_gap, trivial_run)
    result.advanced_steps = sum(s.rating >= config.advanced_threshold for s in witness)
    result.longest_chain = max((s.chain_length for s in witness), default=0)
    result.distributed_bins = len({min(config.distribution_bins - 1, i * config.distribution_bins // len(witness))
                                  for i, s in enumerate(witness) if s.rating >= config.advanced_threshold})
    return finish(classify_certificate(result, config))
