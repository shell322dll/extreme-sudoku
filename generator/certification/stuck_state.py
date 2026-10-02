"""Stuck-State Superset Lemma (SSL-v1): a negative certificate for one threshold.

Reference: ``docs/PHASE7_1_STUCK_STATE_PROOFS.md`` (theorem in section 2, runtime
guards G1-G9 in section 6). Summary: let G be a valid, unsolved state with
``root ⊒ G`` (bitwise order, section 1) at which a fresh, uncached enumeration at
threshold T is complete and yields no step. If every technique with rating <= T
has a proven SSL (true for every T < 36 with the audited registry ratings and the
audited source code), then no transition path of the unbounded model M_T reaches
a solved state from the root. The proof does not depend on the path from the root
to G, on step soundness, on the unique solution or on any operational limit.

This module only builds the candidate closure and evaluates the guards. Any guard
failure, timeout or unexpected condition yields NO certificate (fail closed); the
caller then falls back to the exhaustive threshold search, unchanged.
"""
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from ..rating.registry import DEFAULT_REGISTRY
from ..sudoku.candidates import SudokuState
from .enumeration import StepEnumerator as _AuditedEnumerator

from . import enumeration as _enumeration, enum_chains as _enum_chains
from . import enum_als as _enum_als, enum_forcing as _enum_forcing
from ..solver import human_solver as _human_solver
from ..solver import techniques as _techniques
from ..solver.techniques import base as _base, chains as _chains

# Identity of the audited code at import time (review P2-2). G7 pins the bytes on
# disk; this pins the in-process objects the enumerator dispatches to, so a
# replaced class, method or module-level function (monkeypatching) disables SSL:
# it defines a different transition model, for which SSL proves nothing.
_AUDITED_ENUMERATE = _AuditedEnumerator.enumerate
_AUDITED_RUN = _AuditedEnumerator._run


def _code_identity():
    items = {
        "enumeration.StepEnumerator": _enumeration.StepEnumerator,
        "enumeration.canonical_steps": _enumeration.canonical_steps,
        "enumeration.default_techniques": _enumeration.default_techniques,
        "enum_chains.enumerate_chains": _enum_chains.enumerate_chains,
        "enum_chains.canonical_steps": _enum_chains.canonical_steps,
        "enum_chains.InferenceGraph": _enum_chains.InferenceGraph,
        "enum_als.enumerate_als_steps": _enum_als.enumerate_als_steps,
        "enum_forcing.enumerate_forcing": _enum_forcing.enumerate_forcing,
        "chains.InferenceGraph": _chains.InferenceGraph,
        "techniques.default_techniques": _techniques.default_techniques,
        "base.Technique.step": _base.Technique.step,
        "human_solver.apply_step": _human_solver.apply_step,
    }
    for cls in _techniques.TECHNIQUE_TYPES:
        items[f"{cls.__name__}.find_steps"] = cls.find_steps
        items[f"{cls.__name__}.step"] = cls.step
    return items


_AUDITED_IDENTITY = _code_identity()


def changed_code_identity():
    """Names of audited in-process objects that differ from the import-time identity."""
    try:
        current = _code_identity()
    except Exception:  # noqa: BLE001  fail closed
        return ["<identity check failed>"]
    return sorted(k for k in set(current) | set(_AUDITED_IDENTITY)
                  if current.get(k) is not _AUDITED_IDENTITY.get(k))


def audited_enumerator(enumerator):
    """True only for an unmodified ``StepEnumerator`` (exact class and methods)
    whose module-level dispatch targets are the audited objects."""
    return (type(enumerator) is _AuditedEnumerator and type(enumerator).enumerate is _AUDITED_ENUMERATE
            and type(enumerator)._run is _AUDITED_RUN and "enumerate" not in vars(enumerator)
            and "_run" not in vars(enumerator)
            and all(type(t).find_steps is _AUDITED_IDENTITY.get(f"{type(t).__name__}.find_steps")
                    and "find_steps" not in vars(t) for t in enumerator.techniques)
            and not changed_code_identity())

LEMMA_VERSION = "SSL-v1"
PROOF_KIND = "STUCK_STATE_SUPERSET_LEMMA"
EXHAUSTIVE_PROOF_KIND = "EXHAUSTIVE_SEARCH"
# Families rated >= 36 (ALS, forcing, Nishio) are not covered by the proofs.
MAX_THRESHOLD_EXCLUSIVE = 36.0

# Audited technique table: name -> (class name, rating, structural flags).
# Flags: subset/fish ``size``; chain ``mode``, ``grouped``, ``loops_only``.
PROVEN_TECHNIQUES = {
    "Full House": ("FullHouse", 0.5, {}),
    "Naked Single": ("NakedSingle", 1.0, {}),
    "Hidden Single": ("HiddenSingle", 1.2, {}),
    "Locked Candidates": ("LockedCandidates", 2.0, {}),
    "Naked Pair": ("NakedPair", 3.0, {"size": 2}),
    "Hidden Pair": ("HiddenPair", 3.2, {"size": 2}),
    "Naked Triple": ("NakedTriple", 5.0, {"size": 3}),
    "Hidden Triple": ("HiddenTriple", 5.2, {"size": 3}),
    "Naked Quad": ("NakedQuad", 7.0, {"size": 4}),
    "Hidden Quad": ("HiddenQuad", 7.2, {"size": 4}),
    "X-Wing": ("XWing", 8.0, {"size": 2}),
    "Skyscraper": ("Skyscraper", 9.0, {}),
    "2-String Kite": ("TwoStringKite", 9.2, {}),
    "Turbot Fish": ("TurbotFish", 10.0, {}),
    "Empty Rectangle": ("EmptyRectangle", 11.0, {}),
    "Swordfish": ("Swordfish", 12.0, {"size": 3}),
    "XY-Wing": ("XYWing", 14.0, {}),
    "XYZ-Wing": ("XYZWing", 16.0, {}),
    "W-Wing": ("WWing", 17.0, {}),
    "Jellyfish": ("Jellyfish", 18.0, {"size": 4}),
    "X-Chain": ("XChain", 22.0, {"mode": "x", "grouped": False, "loops_only": False}),
    "XY-Chain": ("XYChain", 25.0, {"mode": "xy", "grouped": False, "loops_only": False}),
    "AIC": ("AIC", 30.0, {"mode": "aic", "grouped": False, "loops_only": False}),
    "Nice Loop": ("NiceLoop", 32.0, {"mode": "aic", "grouped": False, "loops_only": True}),
    "Grouped AIC": ("GroupedAIC", 35.0, {"mode": "aic", "grouped": True, "loops_only": False}),
}

# Audited techniques that are known to the registry but NOT covered by SSL.
UNPROVEN_TECHNIQUES = {
    "ALS-XZ": ("ALSXZ", 36.0), "ALS-XY-Wing": ("ALSXYWing", 39.0), "ALS Chain": ("ALSChain", 42.0),
    "Forcing Chain": ("ForcingChain", 50.0), "Nishio": ("Nishio", 55.0),
}

# Exact class order of ``default_techniques`` at audit time.
DEFAULT_TECHNIQUE_ORDER = (
    "FullHouse", "NakedSingle", "HiddenSingle", "LockedCandidates", "NakedPair", "HiddenPair",
    "NakedTriple", "HiddenTriple", "NakedQuad", "HiddenQuad", "XWing", "Skyscraper", "TwoStringKite",
    "TurbotFish", "EmptyRectangle", "Swordfish", "XYWing", "XYZWing", "WWing", "Jellyfish", "XChain",
    "XYChain", "AIC", "NiceLoop", "GroupedAIC", "ALSXZ", "ALSXYWing", "ALSChain", "ForcingChain", "Nishio",
)

# Proof dependencies (doc section 0): every listed family must be enabled (<= T)
# whenever the key family is enabled, because its proof derives a step of that
# family at G.
_NS, _HS = "Naked Single", "Hidden Single"
PROOF_DEPENDENCIES = {
    "Full House": ("Full House",),
    "Naked Single": (_NS, _HS),
    "Hidden Single": (_NS, _HS),
    "Locked Candidates": (_HS, "Locked Candidates"),
    "Naked Pair": (_NS, "Naked Pair"),
    "Naked Triple": (_NS, "Naked Pair", "Naked Triple"),
    "Naked Quad": (_NS, "Naked Pair", "Naked Triple", "Naked Quad"),
    "Hidden Pair": (_HS, "Hidden Pair"),
    "Hidden Triple": (_HS, "Hidden Pair", "Hidden Triple"),
    "Hidden Quad": (_HS, "Hidden Pair", "Hidden Triple", "Hidden Quad"),
    "X-Wing": (_HS, "X-Wing"),
    "Swordfish": (_HS, "X-Wing", "Swordfish"),
    "Jellyfish": (_HS, "X-Wing", "Swordfish", "Jellyfish"),
    "Skyscraper": (_HS, "Skyscraper"),
    "2-String Kite": (_HS, "2-String Kite"),
    "Turbot Fish": (_HS, "Turbot Fish"),
    "Empty Rectangle": (_HS, "Locked Candidates", "Empty Rectangle"),
    "XY-Wing": (_NS, "XY-Wing"),
    "XYZ-Wing": (_NS, "Naked Pair", "XY-Wing", "XYZ-Wing"),
    "W-Wing": (_NS, _HS, "W-Wing"),
    "X-Chain": (_NS, _HS, "X-Chain"),
    "XY-Chain": (_NS, _HS, "XY-Chain"),
    "AIC": (_NS, _HS, "AIC"),
    "Nice Loop": (_NS, _HS, "Nice Loop"),
    "Grouped AIC": (_NS, _HS, "Locked Candidates", "AIC", "Grouped AIC"),
}

# G7: SHA-256 of the audited sources (paths relative to the ``generator`` package).
# Any difference voids the proofs: no certificate is issued until re-audit.
PINNED_SOURCE_SHA256 = {
    "certification/models.py":
        "fb8b166be5c6d280708fdc985c45da05b1f689109f9aa16dfc99672d4b378e86",
    "certification/enum_chains.py":
        "16f996ceb84e94bf5d138c0a6673b7f4843979cb80d0c791146568eef4749fb7",
    "certification/enumeration.py":
        "f87115df409531ab5eba69f52582964abf831af68ae2a82278d7b3f28a3215aa",
    "certification/transitions.py":
        "2c2709c12ee0971ccce198ebca88a0e113acf64cfaf3af26d7bbf47c2eb0a031",
    "solver/human_solver.py":
        "480bdcc48cc5204533e866c4297295dca427600aaa07e8d5a8c82645172ae8e8",
    "solver/models.py":
        "f3d7f3c6eb1567a5c40c7591023ec31be19f12a6dd8049f55c584f0defd9c54d",
    "solver/techniques/__init__.py":
        "b7767f4aefe8da0ce3a5bdf59a2867dd286d619aeb5df3a65fff10d2549f663c",
    "solver/techniques/base.py":
        "da0ef19154ef9bc6a38af97c410821d5c04b1be1bc2b97a2e96ca2f310554cbc",
    "solver/techniques/chains.py":
        "8d23d1f448a0ce26ee59bfe0ccdf7ab61b59f76758ce2749edbdc7bb14dbc917",
    "solver/techniques/fish.py":
        "fcedfff118c53bc5cff4486e08e34c573ccbcfecb37866b663d924651f0b1099",
    "solver/techniques/locked_candidates.py":
        "40d6e52e9c8020b81457f0b7dad9690066de8592868efec37c3debdbd34ce636",
    "solver/techniques/single_digit_patterns.py":
        "9756b0302a798e07b4d194c96ab8dce289a123aec676c414df5ef3d6e6252bb3",
    "solver/techniques/singles.py":
        "ebc56c28bcd5a10bc1b39e27a1d8c7182bfd90d7ac2cc5d331d92533c261203e",
    "solver/techniques/subsets.py":
        "f3563bf16555b72a9fdbf5fb3c88e7451d40deea3c2cf4e7559b2ef0034fc199",
    "solver/techniques/wings.py":
        "4e896a4a0fd2a0cba30be433d0e35235baf4fe2a444c944a62ff2e57b36875fd",
    "sudoku/candidates.py":
        "87bb1d94b6560f75fc231b540cb1cefe768745391b14512878985de005471ced",
    "sudoku/grid.py":
        "f47660de1ae324316e11aaa7da841208dcd02f4829c5c63072e29a6727b6de40",
}

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def source_hashes(paths=None):
    """Current SHA-256 of each audited source file (None if unreadable)."""
    result = {}
    for relative in sorted(paths if paths is not None else PINNED_SOURCE_SHA256):
        try:
            result[relative] = sha256((_PACKAGE_ROOT / relative).read_bytes()).hexdigest()
        except OSError:
            result[relative] = None
    return result


def source_fingerprint(hashes):
    digest = sha256(LEMMA_VERSION.encode())
    for relative, value in sorted(hashes.items()):
        digest.update(f"{relative}={value};".encode())
    return digest.hexdigest()


def live_mask(state, cell):
    """``L_S(c)``: candidate bits plus the placed digit, as a 9-bit mask."""
    value = state.grid[cell]
    return state.candidates[cell] | ((1 << (value - 1)) if value else 0)


def dominates(x, g):
    """``x ⊒ g`` (doc section 1): L_g(c) ⊆ L_x(c) for every c, and every cell empty
    in g is empty in x. A direct bitwise check, independent of any path."""
    if len(x.grid) != 81 or len(g.grid) != 81 or len(x.candidates) != 81 or len(g.candidates) != 81:
        return False
    for c in range(81):
        if live_mask(g, c) & ~live_mask(x, c):
            return False
        if g.grid[c] == 0 and x.grid[c] != 0:
            return False
    return True


def state_signature_text(state):
    """JSON-native, complete state identity: 81 digits, '/', 81 masks as 3 hex digits."""
    return "".join(map(str, state.grid)) + "/" + "".join(f"{m:03x}" for m in state.candidates)


def parse_signature_text(text):
    grid, masks = text.split("/")
    if len(grid) != 81 or len(masks) != 243:
        raise ValueError("Malformed state signature text")
    return SudokuState([int(c) for c in grid], [int(masks[3 * i:3 * i + 3], 16) for i in range(81)])


def confluence_violation(root, threshold_results, witness):
    """Fail-closed wrapper (review P2-6): any exception is itself an alarm."""
    try:
        return _confluence_violation(root, threshold_results, witness)
    except Exception as exc:  # noqa: BLE001
        return f"SSL confluence alarm: check failed ({type(exc).__name__}: {exc})"


def _confluence_violation(root, threshold_results, witness):
    """Review R5 / proofs §8.3: cheap consistency alarm after an SSL certificate.

    For every threshold T certified by SSL in this invocation (closure G), it is a
    contradiction (theorem or code defect) if
      * a SOLVED result or the accepted witness has max rating <= T (a solved
        state reachable at T, the certificate also covers every T' <= T);
      * a state on the witness prefix whose steps are all rated <= T (states
        reachable at T, including the first state after the prefix) is not ``⊒ G``,
        or a prefix step violates SSL w.r.t. G.
    A second complete dead end Y != G is not searched for here (it would need
    extra enumerations); it is only implied by the checks above. Returns an error
    message or None. Callers must treat a message as ERROR (fail closed).
    """
    from ..solver.human_solver import apply_step as reference_apply
    certified = [t for t in threshold_results if t.negative_proof_kind == PROOF_KIND and t.negative_certificate]
    for result in certified:
        threshold = result.threshold
        for other in threshold_results:
            if other.status.value == "SOLVED" and other.threshold <= threshold:
                return f"SSL confluence alarm: SOLVED at T={other.threshold} <= certified T={threshold}"
        if witness is not None and max((s.rating for s in witness), default=0.0) <= threshold:
            return f"SSL confluence alarm: witness rated <= certified T={threshold}"
        if type(root) is not SudokuState or witness is None:
            continue
        g = parse_signature_text(result.negative_certificate["closure_signature"])
        state = root
        for step in witness:
            if not dominates(state, g):
                return f"SSL confluence alarm: a state reachable at T={threshold} is not ⊒ G"
            if step.rating > threshold:
                break
            bad = [e for e in step.eliminations if live_mask(g, e[0]) & (1 << (e[1] - 1))]
            bad += [p for p in step.placements if g.grid[p[0]] != p[1]]
            if bad:
                return f"SSL confluence alarm: {step.technique} at T={threshold} violates SSL w.r.t. G"
            state = reference_apply(state, step)
    return None


def candidate_count(state):
    return sum(m.bit_count() for m in state.candidates)


@dataclass
class StuckStateCertificate:
    """Candidate certificate (closure) plus, after checking, the guard results.

    ``outcome``: STUCK (unsolved closure, guards still to be checked), SOLVED
    (closure is solved: a positive witness), TIMEOUT (deadline: no certificate),
    ERROR (a closure step failed independent validation).
    """
    threshold: float
    outcome: str
    closure: SudokuState | None = None
    path: list = field(default_factory=list)
    error: str | None = None
    closure_enumerations: int = 0
    closure_seconds: float = 0.0
    check_seconds: float = 0.0
    guards: list = field(default_factory=list)
    accepted: bool = False
    enumeration_work: int = 0
    source_fingerprint: str = ""

    @property
    def failed_guards(self):
        return [g["guard"] for g in self.guards if g["result"] == "FAIL"]

    def evidence(self):
        """Deterministic, JSON-native evidence (no timings)."""
        return {
            "lemma_version": LEMMA_VERSION, "proof_kind": PROOF_KIND, "threshold": self.threshold,
            "covers": "every threshold T' <= threshold",
            "model": "unbounded-length transition model M_T (operational limits are not part of the model)",
            "closure_signature": state_signature_text(self.closure) if self.closure is not None else None,
            "closure_length": len(self.path),
            "closure_candidates": candidate_count(self.closure) if self.closure is not None else None,
            "closure_enumeration_work": self.enumeration_work,
            "source_fingerprint": self.source_fingerprint,
            "guards": [dict(g) for g in self.guards],
        }

    def telemetry(self):
        return {"outcome": ("PROVEN" if self.accepted else self.outcome if self.outcome != "STUCK"
                            else "FALLBACK"),
                "closure_seconds": self.closure_seconds, "check_seconds": self.check_seconds,
                "seconds": self.closure_seconds + self.check_seconds,
                "closure_length": len(self.path), "closure_enumerations": self.closure_enumerations,
                "closure_candidates": candidate_count(self.closure) if self.closure is not None else None,
                "guards": [dict(g) for g in self.guards], "failed_guards": self.failed_guards,
                "error": self.error}


def compute_closure(root, threshold, enumerator, config, deadline=float("inf")):
    """Deterministic cheapest-first fixpoint G at threshold T.

    At each state the enabled rating levels are enumerated in increasing order and
    the first step (canonical order: rating, step_key) of the first nonempty level
    is applied after ``proofs.validate_step`` accepts it. Stops when no step exists
    at T (G found), the state is solved, or the deadline passes (TIMEOUT). The path
    is logically irrelevant to the theorem (only ``root ⊒ G`` matters, guard G2),
    so intermediate operational limits are harmless here.
    """
    from .proofs import validate_step
    from ..solver.human_solver import apply_step as reference_apply
    started = perf_counter()
    certificate = StuckStateCertificate(float(threshold), "STUCK")
    levels = sorted({t.difficulty for t in enumerator.techniques if t.difficulty <= threshold})
    state = root.copy()
    path = certificate.path
    try:
        while True:
            if perf_counter() >= deadline:
                certificate.outcome = "TIMEOUT"
                break
            if all(state.grid):
                certificate.outcome = "SOLVED"
                break
            chosen = None
            for level in levels:
                found = enumerator.enumerate(state, level, deadline=deadline)
                certificate.closure_enumerations += 1
                if any("TIME_LIMIT" in reason for reason in found.limit_reasons):
                    certificate.outcome = "TIMEOUT"
                    break
                if found.steps:
                    chosen = found.steps[0]
                    break
            if certificate.outcome == "TIMEOUT" or chosen is None:
                break
            if chosen.rating > threshold:
                raise ValueError("Enumerator returned a step above its threshold")
            proof = validate_step(state, chosen, config=config)
            if not proof.valid:
                raise ValueError("Invalid logic proof: " + "; ".join(proof.errors))
            state = reference_apply(state, chosen)
            path.append(chosen)
    except (ValueError, TypeError, AttributeError) as exc:
        certificate.outcome, certificate.error = "ERROR", "Stuck-state closure: " + str(exc)
    certificate.closure = state
    certificate.closure_seconds = perf_counter() - started
    return certificate


def _guard(certificate, guard, check, passed, detail=""):
    certificate.guards.append({"guard": guard, "check": check,
                               "result": "PASS" if passed else "FAIL", "detail": detail})
    return passed


def _skip(certificate, guard, check):
    certificate.guards.append({"guard": guard, "check": check, "result": "SKIPPED", "detail": ""})


def static_guards(certificate, threshold, techniques, *, registry=DEFAULT_REGISTRY, pins=None, enumerator=None):
    """G5 (ratings, scope, dependencies), G6 (technique set) and G7 (source pins)."""
    pins = PINNED_SOURCE_SHA256 if pins is None else pins
    ok = True
    # G5: threshold scope.
    in_scope = type(threshold) in (int, float) and 0 <= threshold < MAX_THRESHOLD_EXCLUSIVE
    ok &= _guard(certificate, "G5.scope", "0 <= T < 36", in_scope, f"T={threshold}")
    # G5: ratings equal the audited table and the registry, per instance.
    table = {**{n: v[1] for n, v in PROVEN_TECHNIQUES.items()}, **{n: v[1] for n, v in UNPROVEN_TECHNIQUES.items()}}
    mismatched = []
    for technique in techniques:
        name = getattr(technique, "name", None)
        try:
            registry_rating = registry.rating_of(name)
        except ValueError:
            registry_rating = None
        if (name not in table or technique.difficulty != table[name] or registry_rating != table[name]):
            mismatched.append(str(name))
    ok &= _guard(certificate, "G5.ratings", "instance difficulty == registry rating == audited table",
                 not mismatched and len(registry.entries) == len(table)
                 and all(registry.rating_of(n) == r for n, r in table.items()),
                 ", ".join(mismatched))
    # G5: every enabled family is proven.
    enabled = {t.name for t in techniques if t.difficulty <= threshold}
    unproven = sorted(enabled - set(PROVEN_TECHNIQUES))
    ok &= _guard(certificate, "G5.proven", "every technique with rating <= T has a proven SSL",
                 not unproven, ", ".join(unproven))
    # G5: proof dependencies are enabled.
    missing = sorted(f"{name}->{dep}" for name in enabled & set(PROVEN_TECHNIQUES)
                     for dep in PROOF_DEPENDENCIES[name] if dep not in enabled)
    ok &= _guard(certificate, "G5.dependencies", "proof dependencies of every enabled family are <= T",
                 not missing, ", ".join(missing))
    # G6: exactly default_techniques (classes, order, flags).
    from ..solver.techniques import TECHNIQUE_TYPES
    classes = tuple(type(t).__name__ for t in techniques)
    flags_bad = []
    for technique in techniques:
        entry = PROVEN_TECHNIQUES.get(technique.name) or UNPROVEN_TECHNIQUES.get(technique.name)
        if entry is None or type(technique).__name__ != entry[0]:
            flags_bad.append(technique.name)
            continue
        for attribute, value in (entry[2].items() if len(entry) > 2 else ()):
            if getattr(technique, attribute, object()) != value:
                flags_bad.append(f"{technique.name}.{attribute}")
    same_types = tuple(type(t) for t in techniques) == tuple(TECHNIQUE_TYPES)
    if enumerator is not None and not audited_enumerator(enumerator):
        flags_bad.append("enumerator or audited code replaced: " + ", ".join(changed_code_identity()))
    ok &= _guard(certificate, "G6.techniques", "technique classes, order and flags equal default_techniques",
                 classes == DEFAULT_TECHNIQUE_ORDER and same_types and not flags_bad, ", ".join(flags_bad))
    # G7: audited source fingerprint.
    hashes = source_hashes(pins)
    certificate.source_fingerprint = source_fingerprint(hashes)
    changed = sorted(p for p, h in hashes.items() if h is None or h != pins.get(p))
    ok &= _guard(certificate, "G7.sources", "SHA-256 of audited sources equals the pinned table",
                 bool(pins) and set(hashes) == set(PINNED_SOURCE_SHA256) and not changed, ", ".join(changed))
    return bool(ok)


def check_certificate(root, threshold, certificate, config, *, deadline=float("inf"), pins=None,
                      enumerator_factory=None):
    """Evaluate guards G1-G8 with fresh objects; True only if every guard passes.

    Fail closed: any exception, timeout or unmet condition rejects the certificate.
    The closure path and caches are never trusted (G2 and G4 are recomputed).
    """
    from .enumeration import StepEnumerator
    from .proofs import validate_path
    started = perf_counter()
    certificate.guards, certificate.accepted = [], False
    try:
        if certificate.outcome != "STUCK" or certificate.closure is None:
            _guard(certificate, "G0.closure", "closure computed without timeout or error", False,
                   certificate.outcome)
            return False
        factory = enumerator_factory or (lambda: StepEnumerator(config, cache=False))
        fresh = factory()
        ok = static_guards(certificate, threshold, fresh.techniques, pins=pins, enumerator=fresh)
        if fresh.cache is not None:
            ok &= _guard(certificate, "G4.fresh", "fresh enumerator without cache", False)
        if not ok:
            for guard, check in (("G1", "closure is a valid SudokuState"), ("G2", "root ⊒ G (bitwise)"),
                                 ("G3", "closure is not solved"), ("G4", "fresh complete empty enumeration at G"),
                                 ("G8", "closure path replays from root (diagnostic)")):
                _skip(certificate, guard, check)
            return False
        try:
            closure = SudokuState(list(certificate.closure.grid), list(certificate.closure.candidates))
            fresh_root = SudokuState(list(root.grid), list(root.candidates))
            closure.validate()
            fresh_root.validate()
            valid = True
        except ValueError as exc:
            valid, detail = False, str(exc)
        if not _guard(certificate, "G1", "closure is a valid SudokuState", valid, "" if valid else detail):
            return False
        if not _guard(certificate, "G2", "root ⊒ G (bitwise)", dominates(fresh_root, closure)):
            return False
        if not _guard(certificate, "G3", "closure is not solved", not all(closure.grid)):
            return False
        enumeration = fresh.enumerate(closure, threshold, deadline=deadline)
        certificate.enumeration_work = enumeration.work
        g4 = (enumeration.complete is True and enumeration.limit_reasons == [] and enumeration.steps == []
              and perf_counter() < deadline)
        detail = (f"steps={len(enumeration.steps)} limits={','.join(enumeration.limit_reasons)}"
                  if not g4 else f"work={enumeration.work}")
        if not _guard(certificate, "G4", "fresh complete empty enumeration at G", g4, detail):
            return False
        replay = validate_path(fresh_root, certificate.path, config=config, require_solved=False)
        replayed_ok = replay.valid
        if replayed_ok:
            replayed = fresh_root
            from ..solver.human_solver import apply_step as reference_apply
            for step in certificate.path:
                replayed = reference_apply(replayed, step)
            replayed_ok = replayed.signature() == closure.signature()
        if not _guard(certificate, "G8", "closure path replays from root (diagnostic)", replayed_ok,
                      "" if replay.valid else "; ".join(replay.errors)):
            certificate.outcome = "ERROR"
            certificate.error = "Stuck-state closure path failed independent replay"
            return False
        certificate.accepted = True
        return True
    except Exception as exc:  # noqa: BLE001  fail closed on anything unexpected
        _guard(certificate, "G9.exception", "guard evaluation raised", False, f"{type(exc).__name__}: {exc}")
        certificate.accepted = False
        return False
    finally:
        certificate.check_seconds = perf_counter() - started
