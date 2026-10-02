"""Transition providers for the certification search.

A provider exposes an abstract, deterministic state graph:

* ``initial(state_or_grid)``      -> root state
* ``signature(state)``            -> hashable, complete state identity
* ``is_solved(state)``            -> bool
* ``progress(state)``             -> frontier priority (smaller = more advanced)
* ``depth_bound(state)``          -> upper bound on any path length from state, or None
* ``enumerate(state, T, deadline)`` -> EnumerationResult (steps carry ``rating``)
* ``child(state, step)``          -> successor state or None if it cannot be applied
* ``validate(state, step)``       -> object with ``valid`` and ``errors``
* ``apply_checked(state, step)``  -> successor, raising ValueError if inapplicable
* ``validate_witness(root, path)`` -> bool (fresh replay of a complete witness)
* ``negative_certificate(state, T, deadline)`` -> candidate certificate or None
* ``check_negative_certificate(state, T, certificate, deadline)`` -> bool

``SudokuTransitions`` is the production provider. Its fast successor
construction is certification-local and has exactly the semantics of
``human_solver.apply_step`` (see ``apply_step`` below).

Negative certificates (Phase 7.1): ``negative_certificate`` computes the
deterministic closure G of the Stuck-State Superset Lemma (``stuck_state.py``,
docs/PHASE7_1_STUCK_STATE_PROOFS.md) and ``check_negative_certificate``
independently evaluates guards G1-G8 with fresh objects. Only a checked
certificate is evidence; its absence or rejection is never evidence, and the
search then falls back to exhaustive exploration.
"""
from collections import OrderedDict

from ..sudoku.candidates import ALL, SudokuState
from ..sudoku.grid import ALL_UNITS, PEERS

_CELL_UNITS = tuple((c // 9, 9 + c % 9, 18 + c // 27 * 3 + c % 9 // 3) for c in range(81))


def _locally_valid(grid, masks):
    """Exactly ``SudokuState.validate`` for 81-int grids with digits 0..9 and
    9-bit masks (both guaranteed by construction from a validated parent)."""
    placed = []
    for unit in ALL_UNITS:
        seen = 0
        for c in unit:
            v = grid[c]
            if v:
                bit = 1 << (v - 1)
                if seen & bit:
                    return False  # is_consistent: duplicate digit in a unit
                seen |= bit
        placed.append(seen)
    for c in range(81):
        mask = masks[c]
        if grid[c]:
            if mask:
                return False
        else:
            r, k, b = _CELL_UNITS[c]
            # _allowed(c) = ALL minus digits placed in peers; c itself is empty.
            allowed = ALL & ~(placed[r] | placed[k] | placed[b])
            if not mask or mask & ~allowed:
                return False
    for u, unit in enumerate(ALL_UNITS):
        supported = placed[u]
        for c in unit:
            supported |= masks[c]
        if supported != ALL:
            return False
    return True


def _trusted_state(grid, masks):
    state = SudokuState.__new__(SudokuState)
    state.grid, state.candidates = grid, masks
    return state


def apply_step(state, step):
    """Certification-local equivalent of ``human_solver.apply_step``.

    The original applies effects one at a time, validating after each one. Every
    validation condition is monotone under placements/eliminations of live
    candidates (masks only shrink, a unit's supported digits only shrink, a cell
    can be filled only from a live candidate), so an intermediate failure implies
    a later precondition failure or a final validation failure, and a valid final
    state implies valid intermediates. One final validation is thus equivalent.
    Raises ValueError exactly when the original raises (messages may differ).
    """
    if type(state) is not SudokuState:
        from ..solver.human_solver import apply_step as reference
        return reference(state, step)
    if not step.placements and not step.eliminations:
        raise ValueError("A logical step must make progress")
    grid, masks = list(state.grid), list(state.candidates)
    for cell, digit in step.placements + step.eliminations:
        if type(cell) is not int or not 0 <= cell < 81:
            raise ValueError("Invalid cell in logical step")
        if type(digit) is not int or not 1 <= digit <= 9:
            raise ValueError("digit must be an integer in 1..9")
        if grid[cell] or not masks[cell] & (1 << (digit - 1)):
            raise ValueError("Logical step targets an absent candidate")
    for cell, digit in step.placements:
        bit = 1 << (digit - 1)
        if grid[cell] or not masks[cell] & bit:
            raise ValueError("placement is not an available candidate")
        grid[cell], masks[cell] = digit, 0
        for peer in PEERS[cell]:
            masks[peer] &= ~bit
    for cell, digit in step.eliminations:
        if grid[cell]:
            raise ValueError("cannot eliminate from a filled cell")
        masks[cell] &= ~(1 << (digit - 1))
    if not _locally_valid(grid, masks):
        raise ValueError("Logical step leaves an inconsistent state")
    return _trusted_state(grid, masks)


class LRU:
    def __init__(self, max_entries):
        self.max_entries = max_entries
        self.entries = OrderedDict()
        self.hits = self.misses = self.evictions = self.unhashable = 0

    def get(self, key, default=None):
        try:
            value = self.entries[key]
        except KeyError:
            self.misses += 1
            return default
        except TypeError:
            self.unhashable += 1
            return default
        self.entries.move_to_end(key)
        self.hits += 1
        return value

    def put(self, key, value):
        try:
            self.entries[key] = value
        except TypeError:
            self.unhashable += 1
            return
        self.entries.move_to_end(key)
        while len(self.entries) > self.max_entries:
            self.entries.popitem(last=False)
            self.evictions += 1

    def stats(self):
        lookups = self.hits + self.misses
        return {"lookups": lookups, "hits": self.hits, "hit_rate": self.hits / lookups if lookups else 0.0,
                "entries": len(self.entries), "evictions": self.evictions, "unhashable": self.unhashable}


class SudokuTransitions:
    """Production provider: real SudokuState, StepEnumerator and proofs.validate_step.

    ``search.apply_step`` and ``proofs.validate_step`` are looked up at call time
    so tests can substitute scheduling-only state graphs.
    """

    # Phase 7.1 memory tuning: validation results are reused only for repeated
    # (signature, step) pairs, which are rare (0 hits measured in one search).
    def __init__(self, config, enumerator=None, *, validation_cache_size=4096):
        from .enumeration import StepEnumerator
        self.config = config
        self.enumerator = enumerator if enumerator is not None else StepEnumerator(config)
        self.validation_cache = LRU(validation_cache_size) if validation_cache_size else None

    def initial(self, state_or_grid):
        return state_or_grid.copy() if isinstance(state_or_grid, SudokuState) else SudokuState(state_or_grid)

    def signature(self, state):
        return state.signature()

    def is_solved(self, state):
        if type(state) is SudokuState:
            # Every state in the search is validated on construction.
            return all(state.grid)
        return state.is_solved

    def progress(self, state):
        return sum(m.bit_count() for m in state.candidates)

    def depth_bound(self, state):
        # Each applied step removes at least one live candidate and a solved
        # state has none, so no path from ``state`` is longer than its count.
        if type(state) is SudokuState:
            return sum(m.bit_count() for m in state.candidates)
        return None

    def enumerate(self, state, threshold, deadline):
        return self.enumerator.enumerate(state, threshold, deadline=deadline)

    def child(self, state, step):
        from . import search
        try:
            return search.apply_step(state, step)
        except ValueError:
            return None

    def apply_checked(self, state, step):
        from . import search
        return search.apply_step(state, step)

    def validate(self, state, step, signature=None):
        from . import proofs
        cache = self.validation_cache
        if cache is not None and signature is not None:
            key = (signature, step)
            found = cache.get(key)
            if found is not None:
                return found
            result = proofs.validate_step(state, step, config=self.config)
            cache.put(key, result)
            return result
        return proofs.validate_step(state, step, config=self.config)

    def validate_witness(self, root, path):
        from .proofs import validate_path
        if type(root) is not SudokuState:
            return True  # Scheduling-only graphs: every edge was validated by the provider.
        return validate_path(root, path, config=self.config).valid

    def negative_certificate(self, state, threshold, deadline=float("inf")):
        """SSL closure candidate (not yet evidence) for real Sudoku states, else None."""
        from .stuck_state import audited_enumerator, compute_closure
        # SSL is a theorem about the audited StepEnumerator model only.
        if type(state) is not SudokuState or not audited_enumerator(self.enumerator):
            return None
        return compute_closure(state, threshold, self.enumerator, self.config, deadline)

    def check_negative_certificate(self, state, threshold, certificate, deadline=float("inf")):
        """Independent guard evaluation (G1-G8); True only if every guard passes."""
        if type(state) is not SudokuState or certificate is None:
            return False
        from .stuck_state import check_certificate
        return check_certificate(state, threshold, certificate, self.config, deadline=deadline)

    def cache_stats(self):
        stats = {}
        cache = getattr(self.enumerator, "cache", None)
        if cache is not None:
            stats["enumeration_cache"] = cache.stats()
        if self.validation_cache is not None:
            stats["validation_cache"] = self.validation_cache.stats()
        return stats
