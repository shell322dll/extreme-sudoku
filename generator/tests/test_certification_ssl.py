"""Phase 7.1: Stuck-State Superset Lemma (SSL-v1) negative certificate.

See docs/PHASE7_1_STUCK_STATE_PROOFS.md (theorem section 2, guards section 6,
cross-check plan section 8). Runtime is kept modest: real-puzzle work uses the
8e2b puzzle (HARD), whose SSL closure at T=32 takes well under a second.
"""
from dataclasses import replace
import json
import random
import unittest
from unittest.mock import patch

from generator.certification import (CertificationConfig, CertificationStatus, SearchStatus, certify_puzzle)
from generator.certification import stuck_state
from generator.certification.enumeration import StepEnumerator
from generator.certification.io import _record
from generator.certification.search import threshold_search, minimax_descent
from generator.certification.stuck_state import (PROOF_KIND, EXHAUSTIVE_PROOF_KIND, LEMMA_VERSION,
                                                 check_certificate, compute_closure, dominates, live_mask)
from generator.certification.transitions import SudokuTransitions
from generator.solver.human_solver import apply_step
from generator.sudoku.candidates import ALL, SudokuState
from generator.tests.test_certification_engine import SOLUTION, almost

HARD = "009000001000050008010000640028004000000190000000002030002403000100000206000070003"
HARD_SOLUTION = "289647351476351928513928647628734195347195862951862734762413589134589276895276413"
CONFIG = CertificationConfig()


def bits(*digits):
    return sum(1 << (d - 1) for d in digits)


def state(grid=None, masks=None):
    return SudokuState(list(grid) if grid is not None else [0] * 81,
                       list(masks) if masks is not None else None)


def full_masks():
    return [ALL] * 81


def remove(masks, cells, digit):
    for cell in cells:
        masks[cell] &= ~bits(digit)
    return masks


def place(x, cell, digit):
    """Valid state with ``digit`` placed at ``cell`` (peers cleared)."""
    from generator.solver.models import LogicStep
    return apply_step(x, LogicStep("Naked Single", 1.0, placements=((cell, digit),)))


def eliminate(x, cell, digit):
    masks = list(x.candidates)
    masks[cell] &= ~bits(digit)
    return SudokuState(list(x.grid), masks)


def ssl_violations(step, g):
    """Effects of ``step`` violating SSL(F) w.r.t. G: eliminations not dead in G,
    placements not placed in G."""
    bad = [("elim", c, d) for c, d in step.eliminations if live_mask(g, c) & bits(d)]
    bad += [("place", c, d) for c, d in step.placements if g.grid[c] != d]
    return bad


def is_valid(x):
    try:
        SudokuState(list(x.grid), list(x.candidates)).validate()
        return True
    except ValueError:
        return False


def fresh_enumerate(x, threshold, config=CONFIG):
    return StepEnumerator(config, cache=False).enumerate(x, threshold)


def hard_root():
    return SudokuState([int(c) for c in HARD])


_CLOSURES = {}


def hard_closure(threshold):
    if threshold not in _CLOSURES:
        _CLOSURES[threshold] = compute_closure(hard_root(), threshold, StepEnumerator(CONFIG), CONFIG)
    return _CLOSURES[threshold]


def checked_certificate(root, threshold, **kwargs):
    certificate = compute_closure(root, threshold, StepEnumerator(CONFIG), CONFIG)
    return certificate, check_certificate(root, threshold, certificate, CONFIG, **kwargs)


class OrderTests(unittest.TestCase):
    def test_reflexive_and_eliminations(self):
        x = hard_root()
        self.assertTrue(dominates(x, x))
        cell = x.grid.index(0)
        digit = next(d for d in range(1, 10) if x.candidates[cell] & bits(d))
        g = eliminate(x, cell, digit)
        self.assertTrue(dominates(x, g))
        self.assertFalse(dominates(g, x))  # g lacks a candidate x has

    def test_placements(self):
        masks = full_masks()
        x = state(masks=masks)
        g = place(x, 0, 5)
        self.assertTrue(dominates(x, g))          # G-placed d: X has d live
        self.assertFalse(dominates(g, x))         # X-empty cell placed in g
        h = place(x, 0, 6)
        self.assertFalse(dominates(g, h) or dominates(h, g))  # different placed digit
        self.assertTrue(dominates(g, g))
        # Both placed with the same digit.
        self.assertTrue(dominates(place(g, 40, 1), place(place(g, 40, 1), 80, 2)))
        # G placed d at c, X has c empty without d: not ⊒.
        y = eliminate(x, 0, 5)
        self.assertFalse(dominates(y, g))

    def test_antisymmetric_and_transitive_on_walk(self):
        x = hard_root()
        path = hard_closure(32.0).path[:8]
        states = [x]
        for step in path:
            states.append(apply_step(states[-1], step))
        for i, a in enumerate(states):
            for j, b in enumerate(states):
                self.assertEqual(dominates(a, b), i <= j)


class GuardTests(unittest.TestCase):
    def test_hard_t32_certificate_accepted_with_all_guards(self):
        root = hard_root()
        certificate, ok = checked_certificate(root, 32.0)
        self.assertTrue(ok)
        self.assertEqual(certificate.outcome, "STUCK")
        self.assertTrue(all(g["result"] == "PASS" for g in certificate.guards))
        names = {g["guard"] for g in certificate.guards}
        for guard in ("G1", "G2", "G3", "G4", "G5.scope", "G5.ratings", "G5.proven", "G5.dependencies",
                      "G6.techniques", "G7.sources", "G8"):
            self.assertIn(guard, names)
        evidence = certificate.evidence()
        self.assertEqual(evidence["lemma_version"], LEMMA_VERSION)
        self.assertEqual(evidence["closure_candidates"], 125)  # matches the planner's cross-check
        self.assertEqual(json.loads(json.dumps(evidence)), evidence)

    def test_threshold_36_or_above_rejected(self):
        root = hard_root()
        certificate = hard_closure(32.0)
        for threshold in (36.0, 39.0, 50.0):
            ok = check_certificate(root, threshold, certificate, CONFIG)
            self.assertFalse(ok)
            failed = {g["guard"] for g in certificate.guards if g["result"] == "FAIL"}
            self.assertIn("G5.scope", failed)
            self.assertIn("G5.proven", failed)

    def test_missing_dependency_rejected(self):
        # T=1: Naked Single enabled, Hidden Single (1.2) not: proof needs both.
        certificate, ok = checked_certificate(hard_root(), 1.0)
        self.assertFalse(ok)
        self.assertIn("G5.dependencies", certificate.failed_guards)

    def test_tampered_source_hash_rejected(self):
        root = hard_root()
        certificate = hard_closure(32.0)
        pins = dict(stuck_state.PINNED_SOURCE_SHA256)
        pins["solver/techniques/wings.py"] = "0" * 64
        self.assertFalse(check_certificate(root, 32.0, certificate, CONFIG, pins=pins))
        self.assertIn("G7.sources", certificate.failed_guards)
        # Through the search: fallback to exhaustive, never SSL.
        with patch.dict(stuck_state.PINNED_SOURCE_SHA256, {"sudoku/grid.py": "f" * 64}):
            result = threshold_search(root, 32.0, replace(CONFIG, node_budget=30))
        self.assertNotEqual(result.negative_proof_kind, PROOF_KIND)
        self.assertEqual(result.status, SearchStatus.INCONCLUSIVE_BUDGET)
        self.assertEqual(result.telemetry["stuck_state_lemma"]["outcome"], "FALLBACK")
        self.assertIn("G7.sources", result.telemetry["stuck_state_lemma"]["failed_guards"])

    def test_tampered_rating_or_techniques_rejected(self):
        root = hard_root()
        certificate = hard_closure(32.0)

        def tampered():
            enumerator = StepEnumerator(CONFIG, cache=False)
            next(t for t in enumerator.techniques if t.name == "XY-Wing").difficulty = 40.0
            return enumerator
        self.assertFalse(check_certificate(root, 32.0, certificate, CONFIG, enumerator_factory=tampered))
        self.assertIn("G5.ratings", certificate.failed_guards)

        def dropped():
            enumerator = StepEnumerator(CONFIG, cache=False)
            enumerator.techniques = [t for t in enumerator.techniques if t.name != "Empty Rectangle"]
            return enumerator
        self.assertFalse(check_certificate(root, 32.0, certificate, CONFIG, enumerator_factory=dropped))
        self.assertIn("G6.techniques", certificate.failed_guards)

        def cached():
            return StepEnumerator(CONFIG, cache=True)
        self.assertFalse(check_certificate(root, 32.0, certificate, CONFIG, enumerator_factory=cached))
        self.assertIn("G4.fresh", certificate.failed_guards)

    def test_incomplete_enumeration_at_g_rejected(self):
        tiny = replace(CONFIG, max_chain_search_nodes=5)
        root = hard_root()
        certificate = compute_closure(root, 32.0, StepEnumerator(tiny), tiny)
        self.assertEqual(certificate.outcome, "STUCK")
        self.assertFalse(check_certificate(root, 32.0, certificate, tiny))
        self.assertIn("G4", certificate.failed_guards)
        result = threshold_search(root, 32.0, replace(tiny, node_budget=20))
        self.assertNotEqual(result.status, SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)
        self.assertEqual(result.telemetry["stuck_state_lemma"]["outcome"], "FALLBACK")

    def test_short_chain_length_limit_rejected(self):
        short = replace(CONFIG, max_chain_length=3)
        root = hard_root()
        certificate = compute_closure(root, 32.0, StepEnumerator(short), short)
        self.assertFalse(check_certificate(root, 32.0, certificate, short))
        self.assertIn("G4", certificate.failed_guards)

    def test_invalid_or_non_dominated_g_rejected(self):
        root = hard_root()
        good = hard_closure(32.0)
        # G1: invalid closure (an empty cell with no candidates).
        bad = replace(good, closure=SudokuState.__new__(SudokuState), guards=[])
        cell = good.closure.grid.index(0)
        bad.closure.grid = list(good.closure.grid)
        bad.closure.candidates = list(good.closure.candidates)
        bad.closure.candidates[cell] = 0
        self.assertFalse(check_certificate(root, 32.0, bad, CONFIG))
        self.assertIn("G1", bad.failed_guards)
        # G2: closure claims a candidate the root does not have (not root ⊒ G).
        other = replace(good, guards=[])
        start = place(hard_root(), cell, next(d for d in range(1, 10) if good.closure.candidates[cell] & bits(d)))
        other.closure = good.closure
        self.assertFalse(check_certificate(start, 32.0, other, CONFIG))
        self.assertIn("G2", other.failed_guards)
        # G8: a tampered closure path is an ERROR, never a proof.
        tampered = replace(good, path=good.path[1:], guards=[])
        self.assertFalse(check_certificate(root, 32.0, tampered, CONFIG))
        self.assertIn("G8", tampered.failed_guards)
        self.assertEqual(tampered.outcome, "ERROR")

    def test_solved_closure_is_a_validated_witness_not_a_certificate(self):
        root = SudokuState(almost(0, 1, 2, 10, 20, 40, 41, 80))
        certificate, ok = checked_certificate(root, 1.2)
        self.assertEqual(certificate.outcome, "SOLVED")
        self.assertFalse(ok)
        result = threshold_search(root, 1.2, CONFIG)
        self.assertEqual(result.status, SearchStatus.SOLVED)
        self.assertEqual(result.telemetry["stuck_state_lemma"]["outcome"], "SOLVED")
        self.assertIsNone(result.negative_proof_kind)
        self.assertTrue(SudokuTransitions(CONFIG).validate_witness(root, result.path))
        # Hard puzzle at T=35: the closure itself solves it (84 steps).
        hard = threshold_search(hard_root(), 35.0, CONFIG)
        self.assertEqual(hard.status, SearchStatus.SOLVED)
        self.assertEqual(hard.states_explored, len(hard.path))  # closure applications count (P2-5)
        self.assertLessEqual(max(s.rating for s in hard.path), 35.0)

    def test_timeout_never_proves(self):
        root = hard_root()
        certificate = compute_closure(root, 32.0, StepEnumerator(CONFIG), CONFIG, deadline=0.0)
        self.assertEqual(certificate.outcome, "TIMEOUT")
        self.assertFalse(check_certificate(root, 32.0, certificate, CONFIG))
        # Expired deadline during G4.
        good = replace(hard_closure(32.0), guards=[])
        self.assertFalse(check_certificate(root, 32.0, good, CONFIG, deadline=0.0))
        self.assertIn("G4", good.failed_guards)
        result = threshold_search(root, 32.0, replace(CONFIG, time_budget=0))
        self.assertEqual(result.status, SearchStatus.INCONCLUSIVE_BUDGET)
        self.assertIn("TIME_LIMIT", result.limit_reasons)
        self.assertIsNone(result.negative_proof_kind)


class ConfigTests(unittest.TestCase):
    def test_flag_default_fingerprint_and_round_trip(self):
        self.assertTrue(CONFIG.use_stuck_state_lemma)
        off = CertificationConfig(use_stuck_state_lemma=False)
        self.assertNotEqual(off.fingerprint(), CONFIG.fingerprint())
        for config in (CONFIG, off):
            data = json.loads(json.dumps(config.to_dict()))
            self.assertEqual(CertificationConfig.from_dict(data), config)
        for bad in (1, 0, "true", None):
            with self.assertRaises(ValueError):
                CertificationConfig(use_stuck_state_lemma=bad)


def _hand_xyz():
    masks = full_masks()
    masks[0], masks[4], masks[10] = bits(1, 2, 3), bits(1, 3), bits(2, 3)
    return masks


def _hand_er():
    masks = full_masks()
    remove(masks, [10, 11, 19, 20], 1)
    remove(masks, [r * 9 + 4 for r in (1, 2, 3, 4, 6, 7, 8)], 1)
    return masks


class DegenerateHandTests(unittest.TestCase):
    """Local lemma (doc §3/§8.4): if a step of family F at X violates SSL w.r.t.
    X ⊒ G, then G is invalid or enumerate(G, T) is nonempty (the proof's derived
    step). Additionally the stuck closure G* of G satisfies SSL for every X step."""

    def check(self, x, g, threshold, family, expected_family=None):
        self.assertTrue(dominates(x, g))
        steps = [s for s in fresh_enumerate(x, threshold).steps if s.technique == family]
        self.assertTrue(steps, f"no {family} step at X")
        violating = [s for s in steps if ssl_violations(s, g)]
        self.assertTrue(violating, "test must exercise a degenerate G")
        g_steps = []
        if is_valid(g):
            found = fresh_enumerate(g, threshold)
            g_steps = found.steps
            self.assertTrue(g_steps, "SSL violation without a derived step at G")
            if expected_family:
                self.assertIn(expected_family, {s.technique for s in g_steps})
        closure = compute_closure(g, threshold, StepEnumerator(CONFIG), CONFIG)
        if closure.outcome == "STUCK":
            final = fresh_enumerate(closure.closure, threshold)
            if final.complete and not final.steps:
                self.assertTrue(dominates(x, closure.closure))
                for step in fresh_enumerate(x, threshold).steps:
                    self.assertEqual(ssl_violations(step, closure.closure), [], step.technique)
        return g_steps

    def test_xyz_wing_degenerates_to_xy_wing(self):
        x = state(masks=_hand_xyz())
        g = eliminate(x, 0, 3)  # pivot {1,2}: XY-Wing at G
        steps = self.check(x, g, 16.0, "XYZ-Wing", "XY-Wing")
        xy = next(s for s in steps if s.technique == "XY-Wing")
        self.assertTrue({(1, 3), (2, 3)} <= set(xy.eliminations))

    def test_xyz_wing_degenerates_to_naked_pair(self):
        x = state(masks=_hand_xyz())
        self.check(x, eliminate(x, 0, 2), 16.0, "XYZ-Wing", "Naked Pair")
        # Placed wing: the pivot is left with {2,3} = Naked Pair with the other wing.
        self.check(x, place(x, 4, 1), 16.0, "XYZ-Wing", "Naked Pair")

    def test_xyz_wing_without_dependencies_has_no_derived_step(self):
        """Why G5.dependencies exists: at a T that enables XYZ but not XY-Wing
        (impossible with the audited ratings) the degenerate G would be stuck."""
        x = state(masks=_hand_xyz())
        g = eliminate(x, 0, 3)
        restricted = StepEnumerator(CONFIG, cache=False)
        restricted.techniques = [t for t in restricted.techniques if t.name not in ("XY-Wing",)]
        self.assertFalse(restricted.enumerate(g, 16.0).steps)
        self.assertTrue(ssl_violations(next(s for s in fresh_enumerate(x, 16.0).steps
                                            if s.technique == "XYZ-Wing"), g))

    def test_empty_rectangle_degenerates_to_locked_candidates(self):
        x = state(masks=_hand_er())
        # All box positions in column Cc: LC pointing eliminates the target.
        steps = self.check(x, eliminate(eliminate(x, 1, 1), 2, 1), 11.0, "Empty Rectangle",
                           "Locked Candidates")
        self.assertTrue(any((45, 1) in s.eliminations for s in steps if s.technique == "Locked Candidates"))
        # Near cell n placed (far cell f dead): LC again.
        steps = self.check(x, place(x, 4, 1), 11.0, "Empty Rectangle", "Locked Candidates")
        self.assertTrue(any((45, 1) in s.eliminations for s in steps))
        # All box positions in row R: LC eliminates (n, d) instead.
        self.check(x, eliminate(eliminate(x, 9, 1), 18, 1), 11.0, "Empty Rectangle", "Locked Candidates")

    def test_naked_triple_hall_violation_gives_naked_pair(self):
        masks = full_masks()
        for cell in (0, 1, 2):
            masks[cell] = bits(1, 2, 3)
        x = state(masks=masks)
        g = eliminate(eliminate(x, 0, 3), 1, 3)  # {1,2},{1,2},{1,2,3}
        self.check(x, g, 5.0, "Naked Triple", "Naked Pair")

    def test_hidden_triple_hall_violation_gives_hidden_pair(self):
        masks = full_masks()
        remove(masks, range(3, 9), 1)
        remove(masks, range(3, 9), 2)
        remove(masks, range(3, 9), 3)
        x = state(masks=masks)
        g = eliminate(eliminate(x, 2, 1), 2, 2)  # digits 1,2 confined to c0,c1
        self.check(x, g, 5.2, "Hidden Triple", "Hidden Pair")

    def test_swordfish_hall_violation_gives_x_wing(self):
        masks = full_masks()
        for row in (0, 3, 6):
            remove(masks, [row * 9 + c for c in range(9) if c not in (0, 3, 6)], 1)
        x = state(masks=masks)
        g = eliminate(eliminate(x, 6, 1), 33, 1)  # rows 0 and 3 confined to columns 0, 3
        self.check(x, g, 12.0, "Swordfish", "X-Wing")

    def test_x_wing_with_placed_base_gives_singles(self):
        masks = full_masks()
        for row in (0, 3):
            remove(masks, [row * 9 + c for c in range(9) if c not in (0, 3)], 1)
        x = state(masks=masks)
        self.check(x, place(x, 0, 1), 8.0, "X-Wing", None)


# Real states found by random walks (docs/PHASE7_EXPERIMENT_INPUT.json puzzles); format
# of ``stuck_state.state_signature_text``. Enumeration at T=32 includes AIC, X-Chain,
# Empty Rectangle, 2-String Kite (first) and AIC, Nice Loop, XY-Chain (second).
CHAIN_STATES = (
    "050000000000028000090600000671080349528394176943716258205043017030067005700050030/08d00006a1090441010c81a200f00d02106811900000015812000d08d00004a0000440110d808200f0000000000120000120000000000000000000000000000000000000000000000000000000000000000000a00001800000001a00000000090001081830000001881820000000a11281830001031a800000a",
    "089647351000351928513020647028034105300190002951062034002413000100080276895276413/0020000000000000000000000000080680680000000000000000000000000001800001800000000000600000000400000000001200000000080600000000900c00a00000000000000c00000000c000000006006000000000000009018010000000c008110000110000000000000000000000000000000000000",
)


def parse_state(text):
    grid, masks = text.split("/")
    return SudokuState([int(c) for c in grid], [int(masks[3 * i:3 * i + 3], 16) for i in range(81)])


def has_step(g, threshold):
    """Cheapest-first: is some step emitted at G (at any enabled rating level)?"""
    enumerator = StepEnumerator(CONFIG, cache=False)
    for level in sorted({t.difficulty for t in enumerator.techniques if t.difficulty <= threshold}):
        if enumerator.enumerate(g, level).steps:
            return True
    return False


class DegenerateChainTests(unittest.TestCase):
    """Local lemma for chain families and ER/Kite on real states: perturb X by
    placing or eliminating a chain node / target (G = X with one more fact, so
    X ⊒ G). Whenever the X step then violates SSL w.r.t. a valid G, a step of
    some enabled family exists at G. Covers P/D chain nodes (CCL, §4.6-4.8)."""

    def run_family(self, x, family, threshold=32.0, max_steps=2, max_cases=14):
        steps = [s for s in fresh_enumerate(x, threshold).steps if s.technique == family][:max_steps]
        self.assertTrue(steps, family)
        cases = violations = 0
        for step in steps:
            facts = set(step.eliminations) | set(step.placements)
            if step.chain:
                facts |= {(n.cells[0], n.digit) for n in step.chain.nodes if len(n.cells) == 1}
            for cell, digit in sorted(facts):
                for operation in (place, eliminate):
                    if cases >= max_cases * len(steps):
                        break
                    try:
                        g = operation(x, cell, digit)
                    except ValueError:
                        continue  # the perturbation itself is contradictory
                    if not is_valid(g):
                        continue
                    self.assertTrue(dominates(x, g))
                    cases += 1
                    if ssl_violations(step, g):
                        violations += 1
                        self.assertTrue(has_step(g, threshold), (family, cell, digit, operation.__name__))
        self.assertGreater(violations, 0, family)
        return cases, violations

    def test_aic_x_chain_er_kite(self):
        x = parse_state(CHAIN_STATES[0])
        for family in ("AIC", "X-Chain", "Empty Rectangle", "2-String Kite"):
            with self.subTest(family=family):
                self.run_family(x, family)

    def test_nice_loop_xy_chain_aic(self):
        x = parse_state(CHAIN_STATES[1])
        for family in ("Nice Loop", "XY-Chain", "AIC"):
            with self.subTest(family=family):
                self.run_family(x, family)


BCF460 = "050000000000028000090600000670000009008300006900010250000040010030000005700050030"
F23734 = "050000700100028000090600000070000009000300076900010250205040010030000005700050030"
B4D935 = "030900000409000003001003540000062000020000008900070000004100026700006900300050780"


class InvariantWalkTests(unittest.TestCase):
    """Doc §8.1: random walks from the root at T never leave ⊒ G, every emitted
    step satisfies SSL w.r.t. G, and every complete dead end equals G (confluence)."""

    CASES = ((HARD, 32.0), (BCF460, 32.0), (F23734, 30.0), (B4D935, 25.0))

    def test_random_walks_stay_above_g(self):
        terminals = 0
        for puzzle, threshold in self.CASES:
            root = SudokuState([int(c) for c in puzzle])
            enumerator = StepEnumerator(CONFIG)
            certificate = compute_closure(root, threshold, enumerator, CONFIG)
            self.assertTrue(check_certificate(root, threshold, certificate, CONFIG), (puzzle, threshold))
            g = certificate.closure
            for seed in (1, 2):
                rng = random.Random(seed * 7919 + int(threshold))
                x = root
                for _ in range(200):
                    self.assertTrue(dominates(x, g))
                    found = enumerator.enumerate(x, threshold)
                    for step in found.steps:
                        self.assertEqual(ssl_violations(step, g), [], (puzzle, threshold, step.technique))
                    if not found.steps:
                        if found.complete:
                            self.assertEqual(x.signature(), g.signature())
                            terminals += 1
                        break
                    x = apply_step(x, rng.choice(found.steps))
                else:
                    self.fail("walk did not terminate")
        self.assertGreaterEqual(terminals, len(self.CASES))


def _hard_path_states(count):
    states = [hard_root()]
    for step in hard_closure(35.0).path[:count]:
        states.append(apply_step(states[-1], step))
    return states


class ExhaustiveAgreementTests(unittest.TestCase):
    """Doc §8.2: on lattices small enough for the exhaustive search, both modes agree."""

    # (index on the deterministic T=35 closure path of HARD, threshold)
    CASES = ((10, 1.2), (10, 2.0), (16, 3.2), (16, 14.0), (22, 2.0), (22, 30.0), (28, 32.0),
             (40, 2.0), (40, 22.0), (60, 8.0), (60, 32.0))

    def test_ssl_and_exhaustive_verdicts_agree(self):
        states = _hard_path_states(60)
        exhaustive = replace(CONFIG, use_stuck_state_lemma=False, node_budget=4000, state_budget=4000,
                             time_budget=20)
        lemma = replace(exhaustive, use_stuck_state_lemma=True)
        proven_by_ssl = solved = 0
        for index, threshold in self.CASES:
            with self.subTest(index=index, threshold=threshold):
                a = threshold_search(states[index], threshold, exhaustive)
                b = threshold_search(states[index], threshold, lemma)
                self.assertIn(a.status, (SearchStatus.SOLVED, SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL))
                self.assertEqual(a.status, b.status)
                if a.status == SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL:
                    self.assertEqual(a.negative_proof_kind, EXHAUSTIVE_PROOF_KIND)
                    proven_by_ssl += b.negative_proof_kind == PROOF_KIND
                else:
                    solved += 1
                    self.assertTrue(SudokuTransitions(CONFIG).validate_witness(states[index], b.path))
                    self.assertLessEqual(max(s.rating for s in b.path), threshold)
        self.assertGreaterEqual(proven_by_ssl, 5)
        self.assertGreaterEqual(solved, 2)

    def test_whole_lattice_above_g_with_unique_terminal(self):
        start, threshold = _hard_path_states(16)[16], 8.0
        certificate = compute_closure(start, threshold, StepEnumerator(CONFIG), CONFIG)
        self.assertTrue(check_certificate(start, threshold, certificate, CONFIG))
        g = certificate.closure
        enumerator = StepEnumerator(CONFIG)
        seen, frontier, terminals = {start.signature()}, [start], set()
        while frontier:
            x = frontier.pop()
            self.assertTrue(dominates(x, g))
            found = enumerator.enumerate(x, threshold)
            self.assertTrue(found.complete)
            if not found.steps:
                terminals.add(x.signature())
            for step in found.steps:
                self.assertEqual(ssl_violations(step, g), [])
                child = apply_step(x, step)
                if child.signature() not in seen:
                    seen.add(child.signature())
                    frontier.append(child)
            self.assertLess(len(seen), 3000)
        self.assertGreater(len(seen), 20)
        self.assertEqual(terminals, {g.signature()})


class PipelineTests(unittest.TestCase):
    def test_hard_puzzle_minimum_certified_by_ssl(self):
        result = certify_puzzle(HARD, HARD_SOLUTION, puzzle_id="puzzle-8e2b144cecb50551d96b")
        self.assertEqual(result.status, CertificationStatus.CERTIFIED_EXTREME)
        self.assertEqual(result.minimum_required_rating, 35.0)
        self.assertEqual(result.negative_proof_kind, PROOF_KIND)
        self.assertEqual(result.failure_reasons, [])
        below = result.threshold_results[-1]
        self.assertEqual((below.threshold, below.status), (32.0, SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL))
        self.assertEqual(below.negative_proof_kind, PROOF_KIND)
        self.assertEqual(below.negative_certificate["closure_candidates"], 125)
        self.assertEqual(below.negative_certificate["closure_length"], 28)
        self.assertTrue(all(g["result"] == "PASS" for g in below.negative_certificate["guards"]))
        telemetry = below.telemetry["stuck_state_lemma"]
        self.assertEqual(telemetry["outcome"], "PROVEN")
        self.assertGreater(telemetry["seconds"], 0)
        self.assertLess(result.elapsed_seconds, 30)
        self.assertGreaterEqual(result.certified_bottlenecks, 2)
        record = _record(result, CONFIG)
        self.assertEqual(record["certification"]["negativeProofKind"], PROOF_KIND)
        evidence = record["certification"]["evidence"]["threshold_results"][-1]
        self.assertEqual(evidence["negative_proof_kind"], PROOF_KIND)
        self.assertEqual(evidence["negative_certificate"]["lemma_version"], LEMMA_VERSION)
        # Deterministic evidence: a fresh rerun yields identical stable metadata.
        from generator.certification.io import _stable_record
        again = certify_puzzle(HARD, HARD_SOLUTION, puzzle_id="puzzle-8e2b144cecb50551d96b")
        self.assertEqual(_stable_record(record), _stable_record(_record(again, CONFIG)))

    def test_production_export_readback_with_ssl_record(self):
        import tempfile
        from pathlib import Path
        from generator.certification.io import export_production, read_json, validate_production_database
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "puzzles.json"
            database, _ = export_production([{"id": "puzzle-8e2b144cecb50551d96b", "puzzle": HARD,
                                              "solution": HARD_SOLUTION}], path)
            self.assertEqual(len(database["puzzles"]), 1)
            stored = read_json(path)
            self.assertEqual(stored["puzzles"][0]["certification"]["negativeProofKind"], PROOF_KIND)
            validate_production_database(stored)

    def test_disabled_flag_reproduces_exhaustive_behaviour(self):
        off = CertificationConfig(use_stuck_state_lemma=False, time_budget=4)
        result = certify_puzzle(HARD, HARD_SOLUTION, config=off)
        self.assertEqual(result.status, CertificationStatus.CERTIFICATION_TIMEOUT)
        self.assertIsNone(result.minimum_required_rating)
        self.assertIsNone(result.negative_proof_kind)
        below = result.threshold_results[-1]
        self.assertEqual(below.threshold, 32.0)
        self.assertEqual(below.status, SearchStatus.INCONCLUSIVE_BUDGET)
        self.assertNotIn("stuck_state_lemma", below.telemetry)
        self.assertGreater(below.states_explored, 0)
        # Exhaustive proofs are labelled as such.
        easy = certify_puzzle(almost(0), SOLUTION, config=CertificationConfig(use_stuck_state_lemma=False))
        self.assertEqual(easy.threshold_results[0].negative_proof_kind, EXHAUSTIVE_PROOF_KIND)
        self.assertEqual(easy.threshold_results[0].negative_certificate, {})
        easy_ssl = certify_puzzle(almost(0), SOLUTION)
        self.assertEqual(easy_ssl.threshold_results[0].status, SearchStatus.PROVEN_UNSOLVABLE_WITHIN_MODEL)
        self.assertEqual(easy_ssl.threshold_results[0].negative_proof_kind, PROOF_KIND)

    def test_custom_or_patched_enumerator_never_uses_ssl(self):
        """SSL is a theorem about the audited StepEnumerator only."""
        class Custom(StepEnumerator):
            pass
        self.assertIsNone(SudokuTransitions(CONFIG, Custom(CONFIG)).negative_certificate(hard_root(), 32.0))
        patched = StepEnumerator(CONFIG)
        patched.enumerate = lambda *a, **k: None
        self.assertIsNone(SudokuTransitions(CONFIG, patched).negative_certificate(hard_root(), 32.0))
        with patch.object(StepEnumerator, "enumerate", lambda self, *a, **k: None):
            self.assertIsNone(SudokuTransitions(CONFIG).negative_certificate(hard_root(), 32.0))
        outcome = minimax_descent(hard_root(), [30.0, 32.0, 35.0], replace(CONFIG, node_budget=5),
                                  provider=SudokuTransitions(CONFIG, Custom(CONFIG)))
        self.assertFalse(any(t.negative_proof_kind == PROOF_KIND for t in outcome.threshold_results))



def synthetic_state(seed):
    """Possibly unsolvable but valid state: HARD's solution with 40-60 blanks and
    random small masks (always containing the solution digit). Review test D."""
    from generator.sudoku.grid import PEERS
    rng = random.Random(seed)
    grid = [int(c) for c in HARD_SOLUTION]
    blanks = rng.sample(range(81), rng.randint(40, 60))
    for cell in blanks:
        grid[cell] = 0
    masks = [0] * 81
    for cell in blanks:
        used = {grid[p] for p in PEERS[cell] if grid[p]}
        allowed = [d for d in range(1, 10) if d not in used]
        pick = set(rng.sample(allowed, min(len(allowed), rng.randint(2, 4)))) | {int(HARD_SOLUTION[cell])}
        masks[cell] = bits(*pick)
    return SudokuState(grid, masks)


def random_superset(g, root, rng, p_unplace, p_add):
    """A valid X with root-compatible extra freedom and X ⊒ G (not necessarily
    reachable): unplace some non-given G placements, add root candidates."""
    from generator.sudoku.grid import PEERS
    grid, masks = list(g.grid), list(g.candidates)
    for cell in range(81):
        if grid[cell] and not root.grid[cell] and rng.random() < p_unplace:
            masks[cell], grid[cell] = bits(grid[cell]), 0
    for cell in range(81):
        if not grid[cell]:
            placed = {grid[p] for p in PEERS[cell] if grid[p]}
            for digit in range(1, 10):
                if digit not in placed and root.candidates[cell] & bits(digit) and rng.random() < p_add:
                    masks[cell] |= bits(digit)
    x = SudokuState(grid, masks)
    x.validate()
    return x


class SupersetRegressionTests(unittest.TestCase):
    """Review R6: random valid supersets X ⊒ G of a complete stuck G at
    T ∈ {12, 25, 32, 35}; every enumerated step's effects already hold in G."""

    def check_supersets(self, root, threshold, count, seed, families):
        certificate = compute_closure(root, threshold, StepEnumerator(CONFIG), CONFIG)
        self.assertTrue(check_certificate(root, threshold, certificate, CONFIG), threshold)
        g = certificate.closure
        rng, enumerator = random.Random(seed), StepEnumerator(CONFIG)
        for _ in range(count):
            x = random_superset(g, root, rng, rng.choice((.1, .3, .6)), rng.choice((.1, .3, .6)))
            self.assertTrue(dominates(x, g))
            for step in enumerator.enumerate(x, threshold).steps:
                families[step.technique] = families.get(step.technique, 0) + 1
                self.assertEqual(ssl_violations(step, g), [], (threshold, step.technique))

    def test_real_puzzle_supersets_at_12_25_32(self):
        families = {}
        for threshold in (12.0, 25.0, 32.0):
            with self.subTest(threshold=threshold):
                self.check_supersets(hard_root(), threshold, 10, int(threshold * 10), families)
        for family in ("Hidden Single", "Locked Candidates", "AIC", "Nice Loop", "X-Chain", "XY-Chain"):
            self.assertIn(family, families)

    def test_synthetic_supersets_at_35_include_grouped_aic(self):
        families, complete = {}, 0
        for seed in range(20):
            root = synthetic_state(seed)
            certificate = compute_closure(root, 35.0, StepEnumerator(CONFIG), CONFIG)
            if certificate.outcome != "STUCK" or not check_certificate(root, 35.0, certificate, CONFIG):
                continue
            complete += 1
            self.check_supersets(root, 35.0, 6, seed, families)
        self.assertGreaterEqual(complete, 3)
        self.assertIn("Grouped AIC", families)


class ConfluenceAlarmTests(unittest.TestCase):
    """Review R5 / proofs §8.3: contradictions to an SSL certificate are ERROR."""

    def ssl_result(self):
        result = threshold_search(hard_root(), 32.0, CONFIG)
        self.assertEqual(result.negative_proof_kind, PROOF_KIND)
        return result

    def test_unit_alarms(self):
        from generator.certification.models import ThresholdResult
        from generator.certification.stuck_state import confluence_violation
        proven = self.ssl_result()
        witness = hard_closure(35.0).path
        self.assertIsNone(confluence_violation(hard_root(), [proven], witness))
        solved_below = ThresholdResult(30.0, SearchStatus.SOLVED)
        self.assertIn("SOLVED", confluence_violation(hard_root(), [proven, solved_below], witness))
        cheap = [replace(s, rating=min(s.rating, 30.0)) for s in witness]
        self.assertIn("witness", confluence_violation(hard_root(), [proven], cheap))
        # A G that the first (reachable at T) witness step contradicts.
        forged = replace(proven, negative_certificate=dict(
            proven.negative_certificate, closure_signature=stuck_state.state_signature_text(hard_root())))
        self.assertIn("violates SSL", confluence_violation(hard_root(), [forged], witness))
        # A G in which a cell placed on the reachable prefix is still empty.
        late = hard_closure(32.0).closure
        cell = next(c for c in range(81) if late.grid[c] and not hard_root().grid[c])
        masks, grid = list(late.candidates), list(late.grid)
        masks[cell], grid[cell] = bits(grid[cell]), 0
        loose = SudokuState(grid, masks)
        forged = replace(proven, negative_certificate=dict(
            proven.negative_certificate, closure_signature=stuck_state.state_signature_text(loose)))
        self.assertIn("SSL confluence alarm", confluence_violation(hard_root(), [forged], witness))

    def test_descent_and_pipeline_fail_closed_on_alarm(self):
        original = stuck_state.StuckStateCertificate.evidence

        def forged(certificate):
            evidence = original(certificate)
            evidence["closure_signature"] = stuck_state.state_signature_text(hard_root())
            return evidence
        with patch.object(stuck_state.StuckStateCertificate, "evidence", forged):
            outcome = minimax_descent(hard_root(), [30.0, 32.0, 35.0], CONFIG,
                                      initial_witness=hard_closure(35.0).path)
            self.assertFalse(outcome.conclusive)
            self.assertEqual(outcome.stop_reason, "ERROR")
            self.assertEqual(outcome.last.status, SearchStatus.ERROR)
            self.assertIn("SSL confluence alarm", outcome.last.error)
            result = certify_puzzle(HARD, HARD_SOLUTION)
        self.assertEqual(result.status, CertificationStatus.INVALID_PROOF)
        self.assertFalse(result.production_eligible)
        # Unforged: the same descent is conclusive.
        outcome = minimax_descent(hard_root(), [30.0, 32.0, 35.0], CONFIG, initial_witness=hard_closure(35.0).path)
        self.assertTrue(outcome.conclusive)



class CodeReviewHardeningTests(unittest.TestCase):
    """Phase 7.1 code review P2-2, P2-5, P2-6, P2-8."""

    def test_monkeypatched_module_function_disables_ssl(self):
        from generator.certification.models import EnumerationResult
        targets = ("generator.certification.enum_chains.enumerate_chains",
                   "generator.certification.enumeration.canonical_steps",
                   "generator.certification.enum_chains.InferenceGraph",
                   "generator.solver.techniques.wings.WWing.find_steps")
        replacements = {targets[0]: lambda *a, **k: EnumerationResult(),
                        targets[1]: lambda steps: list(steps),
                        targets[2]: type("FakeGraph", (), {}),
                        targets[3]: lambda self, state: []}
        for target in targets:
            with self.subTest(target=target), patch(target, replacements[target]):
                self.assertTrue(stuck_state.changed_code_identity())
                self.assertIsNone(SudokuTransitions(CONFIG).negative_certificate(hard_root(), 32.0))
                result = threshold_search(hard_root(), 32.0, replace(CONFIG, node_budget=3, time_budget=5))
                self.assertNotEqual(result.negative_proof_kind, PROOF_KIND)
                self.assertNotIn("stuck_state_lemma", result.telemetry)
        self.assertEqual(stuck_state.changed_code_identity(), [])
        # Review reproduction: a patched chain enumerator must not turn T=35 into an SSL proof.
        with patch(targets[0], replacements[targets[0]]):
            result = threshold_search(hard_root(), 35.0, replace(CONFIG, node_budget=3, time_budget=5))
        self.assertNotEqual(result.negative_proof_kind, PROOF_KIND)
        # A check_certificate call made while patched fails G6 as well.
        certificate = hard_closure(32.0)
        with patch(targets[0], replacements[targets[0]]):
            self.assertFalse(check_certificate(hard_root(), 32.0, certificate, CONFIG))
        self.assertIn("G6.techniques", certificate.failed_guards)

    def test_solved_closure_respects_path_depth_and_node_budget(self):
        for config in (replace(CONFIG, max_path_depth=50), replace(CONFIG, node_budget=50)):
            with self.subTest(config=(config.max_path_depth, config.node_budget)):
                result = threshold_search(hard_root(), 35.0, replace(config, time_budget=3))
                self.assertEqual(result.telemetry["stuck_state_lemma"]["outcome"], "FALLBACK")
                self.assertNotEqual(result.status, SearchStatus.SOLVED)  # 84 > 50: no closure witness

    def test_confluence_check_exception_is_an_alarm(self):
        from generator.certification.stuck_state import confluence_violation
        proven = threshold_search(hard_root(), 32.0, CONFIG)
        broken = replace(proven, negative_certificate=dict(proven.negative_certificate, closure_signature="bad"))
        alarm = confluence_violation(hard_root(), [broken], hard_closure(35.0).path)
        self.assertIn("SSL confluence alarm: check failed", alarm)
        with patch("generator.certification.stuck_state._confluence_violation", side_effect=RuntimeError("x")):
            self.assertIn("check failed", confluence_violation(hard_root(), [proven], []))
            outcome = minimax_descent(hard_root(), [30.0, 32.0, 35.0], CONFIG,
                                      initial_witness=hard_closure(35.0).path)
        self.assertEqual(outcome.stop_reason, "ERROR")
        self.assertFalse(outcome.conclusive)

    def test_shared_cache_is_keyed_by_config(self):
        from generator.certification.enumeration import EnumerationCache
        shared = EnumerationCache()
        loose = StepEnumerator(CONFIG, cache=shared)
        tight_config = replace(CONFIG, max_chain_search_nodes=5)
        tight = StepEnumerator(tight_config, cache=shared)
        root = hard_root()
        full = loose.enumerate(root, 32.0)
        limited = tight.enumerate(root, 32.0)
        self.assertTrue(full.complete)
        self.assertFalse(limited.complete)
        self.assertEqual(limited, StepEnumerator(tight_config, cache=False).enumerate(root, 32.0))
        self.assertEqual(loose.enumerate(root, 32.0), full)


if __name__ == "__main__":
    unittest.main()
