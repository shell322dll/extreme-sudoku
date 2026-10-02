"""Independent, fail-closed checking of detector certificates.

No detector, graph builder, propagation engine, or mathematical solver is called.
The verifier checks the supplied witness against Sudoku's exactly-one constraints;
it never searches for a replacement explanation when the supplied one is wrong.
"""

from dataclasses import dataclass
from math import isfinite

from ..rating.registry import DEFAULT_REGISTRY
from ..solver.advanced_config import AdvancedConfig
from ..solver.models import CandidateNode, LogicStep
from ..sudoku.candidates import SudokuState, mask_digits, digit_mask
from ..sudoku.grid import ALL_UNITS, ROWS, COLS, BOXES, PEERS


@dataclass(frozen=True)
class ProofValidationResult:
    valid: bool
    errors: tuple[str, ...] = ()


class InvalidProof(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidProof(message)


def _premise_types(value):
    """Pattern indices/digits are strict integers, never bool/float aliases."""
    if isinstance(value, tuple):
        for item in value:
            _premise_types(item)
    else:
        require(type(value) in (int, str), "invalid premise scalar type")


def supports(state, unit, digit):
    return tuple(c for c in unit if state.candidates[c] & digit_mask(digit))


def live(state, cell, digit):
    require(type(cell) is int and 0 <= cell < 81, "invalid candidate cell")
    require(type(digit) is int and 1 <= digit <= 9, "invalid candidate digit")
    require(not state.grid[cell] and state.candidates[cell] & digit_mask(digit),
            "candidate absent or target filled/given")


def unit_check(unit):
    require(all(type(c) is int for c in unit), "unit cells must be integers")
    require(tuple(unit) in ALL_UNITS, "premise is not a Sudoku unit")


def cell_premise(state, item):
    cell, digits = item
    require(type(cell) is int and 0 <= cell < 81, "invalid premise cell")
    require(all(type(d) is int for d in digits)
            and tuple(digits) == mask_digits(state.candidates[cell]), "stale candidate premise")
    require(bool(digits), "filled premise cell")
    return cell, set(digits)


def _simple(state, step):
    """Return exactly the effects licensed by the supplied finite pattern."""
    name, p = step.technique, step.premises
    _premise_types(p)
    place, remove = set(), set()
    if name in ("Full House", "Naked Single", "Hidden Single"):
        require(len(step.placements) == 1 and not step.eliminations, "single requires one placement")
        c, d = step.placements[0]
        if name == "Naked Single":
            require(len(p) == 1 and cell_premise(state, p[0]) == (c, {d}), "invalid naked single")
        else:
            unit_check(p[0])
            require(supports(state, p[0], d) == (c,), "single has other supports")
            if name == "Full House":
                require(len(p) == 1 and [i for i in p[0] if not state.grid[i]] == [c], "not a full house")
            else:
                require(p == (p[0], (d, (c,))), "wrong hidden single premise")
        place.add((c, d))
    elif name == "Locked Candidates":
        mode, source, target, d, cells = p
        unit_check(source); unit_check(target)
        require(mode in ("Pointing", "Claiming"), "unknown intersection mode")
        require((source in BOXES and target in ROWS + COLS) if mode == "Pointing"
                else (target in BOXES and source in ROWS + COLS), "wrong box/line orientation")
        require(tuple(cells) == supports(state, source, d) and len(cells) >= 2
                and set(cells) <= set(target), "invalid locked supports")
        remove = {(c, d) for c in target if c not in source}
    elif name.startswith(("Naked ", "Hidden ")):
        kind, size_name = name.split()
        size = {"Pair": 2, "Triple": 3, "Quad": 4}[size_name]
        unit, entries = p
        unit_check(unit)
        require(len(entries) == size, "wrong subset size")
        if kind == "Naked":
            parsed = [cell_premise(state, item) for item in entries]
            cells = {c for c, _ in parsed}
            digits = set().union(*(ds for _, ds in parsed))
            require(len(cells) == size and cells <= set(unit) and len(digits) == size,
                    "invalid naked subset union")
            remove = {(c, d) for c in unit if c not in cells for d in digits}
        else:
            digits = {d for d, _ in entries}
            require(len(digits) == size, "repeated hidden subset digit")
            for d, cells in entries:
                require(tuple(cells) == supports(state, unit, d) and cells, "invalid hidden supports")
            cells = set().union(*(set(cs) for _, cs in entries))
            require(len(cells) == size, "invalid hidden subset union")
            remove = {(c, d) for c in cells for d in range(1, 10) if d not in digits}
    elif name in ("X-Wing", "Swordfish", "Jellyfish"):
        orientation, d, bases, covers, pattern = p
        size = {"X-Wing": 2, "Swordfish": 3, "Jellyfish": 4}[name]
        require(orientation in ("rows", "columns"), "invalid fish orientation")
        base_units, cover_units = (ROWS, COLS) if orientation == "rows" else (COLS, ROWS)
        require(len(set(bases)) == len(bases) == size and len(set(covers)) == len(covers) == size,
                "invalid fish size")
        require(all(type(i) is int and 0 <= i < 9 for i in bases + covers), "invalid fish line")
        cells = tuple(c for i in bases for c in supports(state, base_units[i], d))
        require(tuple(pattern) == cells, "wrong fish support witness")
        require(all(2 <= len(supports(state, base_units[i], d)) <= size for i in bases), "empty fish base")
        cover_cells = set().union(*(set(cover_units[i]) for i in covers))
        require(set(cells) <= cover_cells, "fish has uncovered candidate")
        base_cells = set().union(*(set(base_units[i]) for i in bases))
        remove = {(c, d) for c in cover_cells - base_cells}
    elif name in ("XY-Wing", "XYZ-Wing"):
        require(len(p) == 3, "wing needs three cells")
        (pivot, a), (first, b), (second, c) = [cell_premise(state, item) for item in p]
        require(len({pivot, first, second}) == 3 and first in PEERS[pivot] and second in PEERS[pivot],
                "invalid wing visibility")
        require(len(b) == len(c) == 2 and len(b & c) == 1, "invalid wing candidates")
        d = next(iter(b & c))
        if name == "XY-Wing":
            require(len(a) == 2 and d not in a and b | c == a | {d}, "invalid XY pivot")
            targets = set(PEERS[first]) & set(PEERS[second]) - {pivot}
        else:
            require(len(a) == 3 and b | c == a, "invalid XYZ pivot")
            targets = set(PEERS[first]) & set(PEERS[second]) & set(PEERS[pivot])
        remove = {(t, d) for t in targets}
    elif name == "W-Wing":
        (first, a), (second, b) = [cell_premise(state, item) for item in p[:2]]
        unit, d, pair = p[2]
        unit_check(unit)
        require(a == b and len(a) == 2 and d in a and first != second, "invalid W wings")
        require(tuple(pair) == supports(state, unit, d) and len(pair) == 2, "invalid W bridge")
        (f, near), (s, far) = p[3]
        require(f == first and s == second and {near, far} == set(pair)
                and not {first, second} & set(pair) and near in PEERS[first] and far in PEERS[second],
                "invalid W bridge visibility")
        other = next(iter(a - {d}))
        remove = {(t, other) for t in set(PEERS[first]) & set(PEERS[second])}
    elif name in ("Skyscraper", "2-String Kite", "Turbot Fish"):
        d, (u, a), (v, b), (ia, ib), (oa, ob) = p
        require(type(u) is int and type(v) is int and 0 <= u < 27 and 0 <= v < 27, "invalid conjugate unit")
        require(tuple(a) == supports(state, ALL_UNITS[u], d) and tuple(b) == supports(state, ALL_UNITS[v], d),
                "stale conjugate pair")
        require(len(a) == len(b) == 2 and len(set(a + b)) == 4
                and {ia, oa} == set(a) and {ib, ob} == set(b) and ib in PEERS[ia], "invalid two-link path")
        if name == "Skyscraper":
            require((u < 9 and v < 9 and ia % 9 == ib % 9 and oa % 9 != ob % 9)
                    or (9 <= u < 18 and 9 <= v < 18 and ia // 9 == ib // 9 and oa // 9 != ob // 9),
                    "invalid skyscraper geometry")
        if name == "2-String Kite":
            require(u < 9 and 9 <= v < 18 and any(ia in box and ib in box for box in BOXES),
                    "invalid kite geometry")
        remove = {(t, d) for t in set(PEERS[oa]) & set(PEERS[ob]) - set(a + b)}
    elif name == "Empty Rectangle":
        d, box_id, cells, row, col, orientation, pair = p
        require(type(box_id) is int and 0 <= box_id < 9 and type(row) is int and 0 <= row < 9
                and type(col) is int and 0 <= col < 9, "invalid rectangle coordinate")
        box = BOXES[box_id]
        require(tuple(cells) == supports(state, box, d) and len(cells) >= 2
                and all(c // 9 == row or c % 9 == col for c in cells)
                and any(c // 9 != row for c in cells) and any(c % 9 != col for c in cells),
                "invalid rectangle arms")
        require(orientation in ("row", "column") and len(pair) == 2 and len(set(pair)) == 2,
                "invalid rectangle bridge")
        for near in pair:
            far = next(c for c in pair if c != near)
            if near in box or (near // 9 != row if orientation == "row" else near % 9 != col):
                continue
            bridge = COLS[near % 9] if orientation == "row" else ROWS[near // 9]
            require(tuple(pair) == supports(state, bridge, d), "rectangle bridge not conjugate")
            target = far // 9 * 9 + col if orientation == "row" else row * 9 + far % 9
            if target not in box and target not in pair:
                remove.add((target, d))
        require(bool(remove), "rectangle has no justified conclusion")
    else:
        raise InvalidProof("unsupported technique")
    return place, remove


def conflict(a, b):
    return a != b and all((x == y and a.digit != b.digit) or
                          (x != y and a.digit == b.digit and y in PEERS[x])
                          for x in a.cells for y in b.cells)


def _node(state, node, grouped):
    require(isinstance(node, CandidateNode) and node.cells
            and tuple(sorted(set(node.cells))) == node.cells, "invalid chain node")
    for c in node.cells:
        live(state, c, node.digit)
    if len(node.cells) > 1:
        require(grouped, "group in ungrouped chain")
        require(any(tuple(sorted(set(supports(state, box, node.digit)) & set(line))) == node.cells
                    for box in BOXES for line in ROWS + COLS), "group is not a complete box/line intersection")


def _link(state, edge):
    a, b, reason = edge.source, edge.target, edge.reason
    _premise_types(reason)
    require(a != b and edge.kind in ("strong", "weak"), "invalid chain edge")
    if edge.kind == "weak":
        require(conflict(a, b), "weak link lacks all-to-all conflict")
        require(reason in (("visibility",), ("closure",)) or
                (len(a.cells) == len(b.cells) == 1 and a.cells == b.cells and reason == ("cell", a.cells[0])),
                "invalid weak link reason")
    elif reason and reason[0] == "cell":
        require(len(a.cells) == len(b.cells) == 1 and a.cells == b.cells
                and reason == ("cell", a.cells[0])
                and set(mask_digits(state.candidates[a.cells[0]])) == {a.digit, b.digit}, "cell link is not strong")
    else:
        require(reason and reason[0] in ("unit", "partition") and type(reason[1]) is int
                and 0 <= reason[1] < 27, "invalid strong unit reason")
        cells = supports(state, ALL_UNITS[reason[1]], a.digit)
        require(a.digit == b.digit and not set(a.cells) & set(b.cells)
                and set(a.cells + b.cells) == set(cells), "unit link does not partition all supports")
        if reason[0] == "unit":
            require(len(reason) == 2 and len(a.cells) == len(b.cells) == 1, "ordinary unit link must be binary")
        else:
            require(len(reason) == 3 and reason[2] == cells, "wrong partition witness")


def _chains(state, step, cfg):
    chain = step.chain
    require(chain is not None and len(chain.links) >= 3 and len(chain.nodes) == len(chain.links) + 1,
            "malformed chain")
    require(type(chain.closed) is bool, "invalid loop flag")
    limit = {"X-Chain": cfg.max_x_chain_length, "XY-Chain": cfg.max_xy_chain_length,
             "Grouped AIC": cfg.max_grouped_aic_length}.get(step.technique, cfg.max_aic_length)
    require(len(chain.links) <= limit, "chain length budget exceeded")
    nodes = chain.nodes[:-1] if chain.closed else chain.nodes
    require(len(set(nodes)) == len(nodes), "repeated chain node")
    require(not chain.closed or chain.nodes[0] == chain.nodes[-1], "loop endpoint mismatch")
    grouped = step.technique == "Grouped AIC"
    for node in nodes:
        _node(state, node, grouped)
        if step.technique == "XY-Chain":
            require(state.candidates[node.cells[0]].bit_count() == 2, "XY node is not bivalue")
    groups = tuple(n for n in chain.nodes if len(n.cells) > 1)
    require(step.grouped_nodes == groups and (not grouped or groups), "group metadata mismatch")
    require(step.premises == (chain.nodes[0], chain.nodes[-1]), "chain endpoint premise mismatch")
    for i, edge in enumerate(chain.links):
        require(edge.source == chain.nodes[i] and edge.target == chain.nodes[i + 1], "edge/node mismatch")
        _link(state, edge)
        require(not i or edge.kind != chain.links[i - 1].kind, "broken strong/weak alternation")
        if step.technique == "XY-Chain":
            require((edge.source.cells == edge.target.cells) if edge.kind == "strong"
                    else (edge.source.digit == edge.target.digit and edge.source.cells != edge.target.cells),
                    "illegal XY link")
    if step.technique == "X-Chain":
        require(len({n.digit for n in nodes}) == 1, "X-chain changes digit")
    place, remove = set(), set()
    first, last = chain.links[0].kind, chain.links[-1].kind
    if step.technique == "Nice Loop":
        require(chain.closed and first != last, "Nice Loop must be continuously alternating")
        pairs = [(e.source, e.target) for e in chain.links if e.kind == "weak"]
    elif chain.closed:
        require(step.technique in ("AIC", "Grouped AIC") and first == last
                and len(chain.nodes[0].cells) == 1, "invalid discontinuity")
        node = chain.nodes[0]
        (place if first == "strong" else remove).add((node.cells[0], node.digit))
        pairs = []
    else:
        require(first == last == "strong", "open chain requires strong endpoints")
        if step.technique == "XY-Chain":
            require(nodes[0].digit == nodes[-1].digit, "XY endpoint digits differ")
        pairs = [(nodes[0], nodes[-1])]
    for c, d in step.eliminations:
        target = CandidateNode((c,), d)
        if target not in nodes and any(conflict(target, a) and conflict(target, b) for a, b in pairs):
            remove.add((c, d))
    return place, remove


def _als(state, step, cfg):
    _premise_types(step.premises)
    path = step.als
    n = len(path)
    require((n == 2 if step.technique == "ALS-XZ" else n == 3 if step.technique == "ALS-XY-Wing" else n >= 4)
            and n <= cfg.max_als_chain_length, "wrong ALS path size")
    require(step.chain is not None and step.chain.nodes == path and not step.chain.closed
            and len(step.chain.links) == n - 1, "ALS chain metadata mismatch")
    used, unions = set(), []
    for als in path:
        require(1 <= len(als.cells) <= cfg.max_als_size and len(als.cells) == len(als.masks)
                and len(set(als.cells)) == len(als.cells) and not used.intersection(als.cells), "invalid or overlapping ALS")
        require(any(set(als.cells) <= set(unit) for unit in ALL_UNITS), "ALS lacks common unit")
        union = set()
        for c, mask in zip(als.cells, als.masks):
            require(type(c) is int and 0 <= c < 81 and mask == state.candidates[c] and mask, "stale ALS mask")
            union.update(mask_digits(mask))
        require(len(union) == len(als.cells) + 1, "ALS violates N+1 rule")
        unions.append(union); used.update(als.cells)
    rccs = []
    for i, edge in enumerate(step.chain.links):
        a, b, d = path[i], path[i + 1], edge.digit
        require(type(d) is int, "RCC digit must be integer")
        require(edge.first == a and edge.second == b and d in unions[i] & unions[i + 1], "wrong RCC endpoints/digit")
        ac = supports(state, a.cells, d); bc = supports(state, b.cells, d)
        require(all(y in PEERS[x] for x in ac for y in bc), "RCC lacks complete visibility")
        require(not rccs or d != rccs[-1], "consecutive RCC digits coincide")
        rccs.append(d)
    require(step.premises == (tuple((a.cells, tuple(sorted(ds))) for a, ds in zip(path, unions)), tuple(rccs)),
            "ALS premise mismatch")
    remove = set()
    for c, d in step.eliminations:
        if c not in used and d in (unions[0] & unions[-1]) - {rccs[0], rccs[-1]}:
            occurrences = supports(state, path[0].cells + path[-1].cells, d)
            if all(c in PEERS[x] for x in occurrences):
                remove.add((c, d))
    return set(), remove


def _clauses(state):
    result = {tuple((c, d) for d in mask_digits(state.candidates[c]))
              for c in range(81) if not state.grid[c]}
    for unit in ALL_UNITS:
        placed = {state.grid[c] for c in unit}
        for d in set(range(1, 10)) - placed:
            result.add(tuple((c, d) for c in supports(state, unit, d)))
    return result


def _propagation(state, proof, clauses, cfg):
    c, d, truth = proof.assumption
    live(state, c, d)
    require(type(truth) is bool and type(proof.limited) is bool, "invalid assumption truth")
    trace = proof.inferences
    require(0 < len(trace) <= cfg.max_forcing_nodes, "forcing proof node budget exceeded")
    facts = set()
    for i, inference in enumerate(trace):
        live(state, *inference.candidate)
        require(type(inference.value) is bool and type(inference.depth) is int
                and 0 <= inference.depth <= cfg.max_forcing_depth, "invalid forcing fact/depth")
        require(len(set(inference.parents)) == len(inference.parents)
                and all(type(p) is int and 0 <= p < i for p in inference.parents), "invalid forcing parents")
        parents = [trace[p] for p in inference.parents]
        if i == 0:
            require(inference.rule == "assumption" and inference.candidate == (c, d)
                    and inference.value == truth and inference.depth == 0
                    and not parents and not inference.clause, "wrong initial assumption")
        else:
            clause = inference.clause
            for candidate in clause:
                live(state, *candidate)
            require(clause in clauses and inference.candidate in clause, "fact uses non-Sudoku clause")
            if inference.rule == "single":
                require(clause == (inference.candidate,) and inference.value and not parents
                        and inference.depth == 0, "invalid singleton inference")
            elif inference.rule == "exclusion":
                require(len(parents) == 1 and parents[0].value and not inference.value
                        and parents[0].candidate in clause and parents[0].candidate != inference.candidate,
                        "invalid clause exclusion")
            elif inference.rule == "last-support":
                require(inference.value and all(not p.value for p in parents)
                        and {p.candidate for p in parents} == set(clause) - {inference.candidate},
                        "invalid last-support inference")
            else:
                raise InvalidProof("unsupported propagation rule or nested assumption")
            if parents:
                require(inference.depth == 1 + max(p.depth for p in parents), "wrong dependency depth")
            else:
                require(inference.depth == 0, "root fact has nonzero depth")
        facts.add((inference.candidate, inference.value))
    contradiction = proof.contradiction
    if contradiction:
        kind = contradiction[0]
        if kind == "opposite":
            require(len(contradiction) == 3 and all(type(i) is int and 0 <= i < len(trace) for i in contradiction[1:]),
                    "invalid contradiction references")
            a, b = (trace[i] for i in contradiction[1:])
            require(a.candidate == b.candidate and a.value != b.value, "opposite contradiction not proved")
        else:
            require(len(contradiction) == 3 and kind in ("two-true", "empty-clause"), "unknown contradiction")
            _, clause, indices = contradiction
            for candidate in clause:
                live(state, *candidate)
            require(clause in clauses and len(set(indices)) == len(indices)
                    and all(type(i) is int and 0 <= i < len(trace) for i in indices), "invalid contradiction clause")
            items = [trace[i] for i in indices]
            if kind == "two-true":
                require(len({p.candidate for p in items}) >= 2 and all(p.value and p.candidate in clause for p in items),
                        "two-true contradiction not proved")
            else:
                require(all(not p.value for p in items) and {p.candidate for p in items} == set(clause),
                        "empty-clause contradiction not proved")
    return facts


def _forcing(state, step, cfg):
    clauses = _clauses(state)
    proofs = step.assumptions
    require(len(proofs) == (1 if step.technique == "Nishio" else 2), "wrong assumption branch count")
    facts = [_propagation(state, proof, clauses, cfg) for proof in proofs]
    if step.technique == "Nishio":
        p = proofs[0]
        require(len(step.premises) == 1 and len(step.premises[0]) == 3
                and type(step.premises[0][2]) is bool, "invalid Nishio premise types")
        live(state, *step.premises[0][:2])
        require(p.contradiction and step.contradiction == p.contradiction
                and step.premises == (p.assumption,), "missing/mismatched Nishio contradiction")
        c, d, truth = p.assumption
        return (set(), {(c, d)}) if truth else ({(c, d)}, set())
    a, b = proofs
    _premise_types(step.premises)
    require(a.assumption[:2] == b.assumption[:2] and a.assumption[2] != b.assumption[2]
            and not a.contradiction and not b.contradiction and not step.contradiction
            and step.premises == (a.assumption[:2],), "forcing branches are not complementary")
    common = facts[0] & facts[1]
    return {c for c, value in common if value}, {c for c, value in common if not value}


def _apply(state, step):
    """Independent simultaneous poststate construction; preserves every given."""
    grid, masks = list(state.grid), list(state.candidates)
    for c, d in step.placements:
        grid[c], masks[c] = d, 0
        for peer in PEERS[c]:
            masks[peer] &= ~digit_mask(d)
    for c, d in step.eliminations:
        masks[c] &= ~digit_mask(d)
    return SudokuState(grid, masks)


def validate_step(state, step, *, config=None):
    """Check a supplied proof without mutating state. Invalid input fails closed."""
    try:
        require(isinstance(state, SudokuState) and isinstance(step, LogicStep), "wrong state/step type")
        state.validate()
        require(all(type(field) is tuple for field in (step.placements, step.eliminations, step.premises,
                    step.grouped_nodes, step.als, step.assumptions, step.contradiction)), "proof fields must be tuples")
        require(type(step.rating) in (float, int) and isfinite(step.rating) and step.rating >= 0, "invalid step rating")
        require(type(step.search_complexity) in (int, float) and isfinite(step.search_complexity)
                and step.search_complexity >= 0, "invalid search complexity")
        rating_config = getattr(config, "difficulty_config", None)
        registry = getattr(rating_config, "registry", DEFAULT_REGISTRY)
        require(step.rating == registry.rating_of(step.technique), "step rating differs from registry")
        effects = step.placements + step.eliminations
        require(bool(effects) and len(set(effects)) == len(effects), "empty or duplicate/contradictory effects")
        require(not ({c for c, _ in step.placements} & {c for c, _ in step.eliminations}), "mixed effects on placed cell")
        require(len({c for c, _ in step.placements}) == len(step.placements), "multiple placements in one cell")
        for c, d in effects:
            live(state, c, d)
        cfg = getattr(config, "advanced_config", config) if config is not None else AdvancedConfig()
        require(isinstance(cfg, AdvancedConfig), "invalid proof validation configuration")
        if step.technique in ("X-Chain", "XY-Chain", "AIC", "Nice Loop", "Grouped AIC"):
            require(not step.als and not step.assumptions and not step.contradiction, "unexpected chain evidence")
            placements, eliminations = _chains(state, step, cfg)
        elif step.technique in ("ALS-XZ", "ALS-XY-Wing", "ALS Chain"):
            require(not step.grouped_nodes and not step.assumptions and not step.contradiction, "unexpected ALS evidence")
            placements, eliminations = _als(state, step, cfg)
        elif step.technique in ("Forcing Chain", "Nishio"):
            require(not step.chain and not step.als and not step.grouped_nodes, "unexpected forcing evidence")
            placements, eliminations = _forcing(state, step, cfg)
        else:
            require(not step.chain and not step.als and not step.grouped_nodes and not step.assumptions
                    and not step.contradiction, "unexpected pattern evidence")
            placements, eliminations = _simple(state, step)
        require(set(step.placements) <= placements and set(step.eliminations) <= eliminations,
                "conclusion does not follow from supplied proof")
        _apply(state, step).validate()
        return ProofValidationResult(True)
    except (ValueError, TypeError, AttributeError, IndexError, KeyError, OverflowError) as exc:
        return ProofValidationResult(False, (str(exc) or type(exc).__name__,))


def validate_path(state_or_grid, steps, *, config=None, require_solved=True):
    """Fresh sequential replay; the initial candidate masks are part of the input."""
    try:
        state = state_or_grid.copy() if isinstance(state_or_grid, SudokuState) else SudokuState(state_or_grid)
        for index, step in enumerate(steps):
            result = validate_step(state, step, config=config)
            if not result.valid:
                return ProofValidationResult(False, tuple(f"step {index}: {e}" for e in result.errors))
            state = _apply(state, step)
        require(not require_solved or state.is_solved, "path does not solve puzzle")
        return ProofValidationResult(True)
    except (ValueError, TypeError, AttributeError) as exc:
        return ProofValidationResult(False, (str(exc),))
