"""Bounded implication propagation under one assumption, with no nested guesses.

Each unresolved cell and each missing unit digit is an exactly-one clause.
A true literal excludes its clause companions; all-but-one exclusions imply
the remaining literal. Every inference stores antecedents and its proof depth.
Forcing combines consequences of A and not A; Nishio refutes an assumption
using an explicit empty-clause/opposite-literal contradiction. Limits mean
'unknown', never contradiction. No solver or solution is consulted.
"""

from collections import deque
from dataclasses import dataclass, replace

from .base import Technique, unique_steps
from .weights import TECHNIQUE_WEIGHTS
from ..advanced_config import AdvancedConfig
from ...sudoku.candidates import mask_digits
from ...sudoku.grid import ALL_UNITS


@dataclass(frozen=True)
class Inference:
    candidate: tuple[int, int]
    value: bool
    depth: int
    rule: str
    clause: tuple[tuple[int, int], ...]
    parents: tuple[int, ...]


@dataclass(frozen=True)
class Propagation:
    assumption: tuple[int, int, bool]
    inferences: tuple[Inference, ...]
    contradiction: tuple = ()
    limited: bool = False

    @property
    def facts(self):
        return {(item.candidate, item.value) for item in self.inferences}

    @property
    def depth(self):
        return max((item.depth for item in self.inferences), default=0)


def logical_clauses(state):
    clauses = []
    for cell in range(81):
        if not state.grid[cell]:
            clauses.append(tuple((cell, d) for d in mask_digits(state.candidates[cell])))
    for unit in ALL_UNITS:
        placed = {state.grid[c] for c in unit}
        for d in range(1, 10):
            if d not in placed:
                clauses.append(tuple((c, d) for c in unit if state.candidates[c] & (1 << (d - 1))))
    return tuple(dict.fromkeys(clauses))


def propagate(state, assumption, config=None, *, clauses=None):
    config = config or AdvancedConfig()
    cell, digit, value = assumption
    if type(value) is not bool or (cell, digit) not in {
            (c, d) for c in range(81) for d in mask_digits(state.candidates[c])}:
        raise ValueError("Assumption must reference a live candidate and a Boolean value")
    clauses = logical_clauses(state) if clauses is None else clauses
    memberships = {}
    for index, clause in enumerate(clauses):
        for candidate in clause:
            memberships.setdefault(candidate, []).append(index)
    trace, known = [], {}
    queue = deque()
    contradiction = ()
    limited = False

    def add(candidate, truth, depth, rule, clause=(), parents=()):
        nonlocal contradiction, limited
        if candidate in known:
            old = known[candidate]
            if trace[old].value != truth:
                # The attempted inference also belongs to the certificate.
                if depth > config.max_forcing_depth or len(trace) >= config.max_forcing_nodes:
                    limited = True
                    return
                trace.append(Inference(candidate, truth, depth, rule, clause, parents))
                contradiction = ("opposite", old, len(trace) - 1)
            return
        if depth > config.max_forcing_depth or len(trace) >= config.max_forcing_nodes:
            limited = True
            return
        known[candidate] = len(trace)
        trace.append(Inference(candidate, truth, depth, rule, clause, parents))
        queue.append(candidate)

    add((cell, digit), value, 0, "assumption")
    # Existing singles are premises too, so propagation is valid on arbitrary
    # states and does not assume that the caller already ran easier techniques.
    for clause in clauses:
        if not clause:
            contradiction = ("empty-clause", clause, ())
            break
        if len(clause) == 1:
            add(clause[0], True, 0, "single", clause)
            if contradiction:
                break
    while queue and not contradiction:
        changed = queue.popleft()
        for index in memberships.get(changed, ()):
            clause = clauses[index]
            trues = [known[c] for c in clause if c in known and trace[known[c]].value]
            false = [known[c] for c in clause if c in known and not trace[known[c]].value]
            if len(trues) > 1:
                contradiction = ("two-true", clause, tuple(trues))
                break
            if len(false) == len(clause):
                contradiction = ("empty-clause", clause, tuple(false))
                break
            if trues:
                parent = trues[0]
                for candidate in clause:
                    if candidate != trace[parent].candidate:
                        add(candidate, False, trace[parent].depth + 1, "exclusion", clause, (parent,))
                        if contradiction:
                            break
            elif len(false) == len(clause) - 1:
                candidate = next(c for c in clause if c not in known)
                depth = 1 + max((trace[i].depth for i in false), default=-1)
                add(candidate, True, depth, "last-support", clause, tuple(false))
            if contradiction:
                break
    return Propagation(tuple(assumption), tuple(trace), contradiction, limited)


def proof_for(proof, conclusion=None):
    """Keep only ancestors of the actual conclusion/contradiction, plus its premise.

    Search work is recorded separately; unrelated propagated facts must not
    inflate the displayed explanation or longest-chain metric.
    """
    if conclusion is not None:
        roots = [i for i, item in enumerate(proof.inferences)
                 if (item.candidate, item.value) == conclusion]
    elif proof.contradiction[0] == "opposite":
        roots = list(proof.contradiction[1:])
    else:
        roots = list(proof.contradiction[2])
    keep = {0}
    pending = list(roots)
    while pending:
        index = pending.pop()
        if index in keep:
            continue
        keep.add(index)
        pending.extend(proof.inferences[index].parents)
    ordered = sorted(keep)
    mapping = {old: new for new, old in enumerate(ordered)}
    trace = tuple(replace(proof.inferences[i], parents=tuple(mapping[p] for p in proof.inferences[i].parents))
                  for i in ordered)
    contradiction = proof.contradiction
    if contradiction:
        if contradiction[0] == "opposite":
            contradiction = ("opposite",) + tuple(mapping[i] for i in contradiction[1:])
        else:
            contradiction = contradiction[:2] + (tuple(mapping[i] for i in contradiction[2]),)
    return replace(proof, inferences=trace, contradiction=contradiction)


class ForcingChain(Technique):
    name = "Forcing Chain"
    difficulty = TECHNIQUE_WEIGHTS[name]

    def __init__(self, difficulty=None, *, config=None):
        super().__init__(difficulty)
        self.config = config or AdvancedConfig()

    def find_steps(self, state):
        clauses = logical_clauses(state)
        candidates = [(c, d) for c in range(81) for d in mask_digits(state.candidates[c])]
        steps = []
        for cell, digit in candidates[:self.config.max_forcing_starts]:
            yes = propagate(state, (cell, digit, True), self.config, clauses=clauses)
            no = propagate(state, (cell, digit, False), self.config, clauses=clauses)
            if yes.contradiction or no.contradiction:
                continue  # Contradiction proof belongs to Nishio below.
            common = yes.facts & no.facts
            # A placement already entails peer exclusions. Return one conclusion
            # per step so apply_step never tries to remove a now-filled candidate.
            for target, truth in sorted(common):
                steps.append(self.step(
                    placements=(target,) if truth else (), eliminations=() if truth else (target,),
                    premises=((cell, digit),), assumptions=(proof_for(yes, (target, truth)),
                                                          proof_for(no, (target, truth))),
                    search_complexity=len(yes.inferences) + len(no.inferences),
                    explanation=f"Both assumptions for r{cell // 9 + 1}c{cell % 9 + 1}={digit} "
                                f"imply {target} is {truth}; the common conclusion is unconditional.",
                ))
        return unique_steps(steps)


class Nishio(ForcingChain):
    name = "Nishio"
    difficulty = TECHNIQUE_WEIGHTS[name]

    def find_steps(self, state):
        clauses = logical_clauses(state)
        candidates = [(c, d) for c in range(81) for d in mask_digits(state.candidates[c])]
        steps = []
        for cell, digit in candidates[:self.config.max_forcing_starts]:
            for truth in (True, False):
                proof = propagate(state, (cell, digit, truth), self.config, clauses=clauses)
                if proof.contradiction:
                    work = len(proof.inferences)
                    proof = proof_for(proof)
                    steps.append(self.step(
                        placements=() if truth else ((cell, digit),),
                        eliminations=((cell, digit),) if truth else (),
                        premises=((cell, digit, truth),), assumptions=(proof,),
                        contradiction=proof.contradiction,
                        search_complexity=work,
                        explanation="The stated assumption yields a certified logical contradiction; "
                                    "its negation follows. No further assumption is introduced.",
                    ))
        return unique_steps(steps)
