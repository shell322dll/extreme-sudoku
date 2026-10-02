"""Enumerate single-assumption propagation, reporting every skipped start."""
from time import perf_counter
from ..sudoku.candidates import mask_digits
from ..solver.techniques.forcing import logical_clauses, propagate, proof_for
from .models import EnumerationResult
from .enumeration import canonical_steps


def enumerate_forcing(state, technique, config, deadline=float("inf")):
    result = EnumerationResult()
    reasons = set()
    clauses = logical_clauses(state)
    candidates = [(c, d) for c in range(81) for d in mask_digits(state.candidates[c])]
    if len(candidates) > config.max_forcing_starts:
        reasons.add("FORCING_START_LIMIT")
    for cell, digit in candidates[:config.max_forcing_starts]:
        if perf_counter() >= deadline:
            reasons.add("TIME_LIMIT")
            break
        proofs = [propagate(state, (cell, digit, truth), config.advanced_config, clauses=clauses)
                  for truth in (True, False)]
        result.work += sum(len(p.inferences) for p in proofs)
        if any(p.limited for p in proofs):
            reasons.add("FORCING_DEPTH_OR_NODE_LIMIT")
        if technique.name == "Nishio":
            for proof in proofs:
                if proof.contradiction:
                    truth = proof.assumption[2]
                    reduced = proof_for(proof)
                    result.steps.append(technique.step(
                        placements=() if truth else ((cell, digit),),
                        eliminations=((cell, digit),) if truth else (),
                        premises=((cell, digit, truth),), assumptions=(reduced,),
                        contradiction=reduced.contradiction,
                        explanation="A single logical assumption yields a checked contradiction."))
        elif not any(p.contradiction for p in proofs):
            yes, no = proofs
            for target, truth in sorted(yes.facts & no.facts):
                result.steps.append(technique.step(placements=(target,) if truth else (),
                    eliminations=() if truth else (target,), premises=((cell, digit),),
                    assumptions=(proof_for(yes, (target, truth)), proof_for(no, (target, truth))),
                    explanation="Both truth values of one candidate imply the conclusion."))
    result.steps = canonical_steps(result.steps)
    result.limit_reasons = sorted(reasons)
    result.complete = not reasons
    return result
