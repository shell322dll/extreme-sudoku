"""Independent review probes; run from project root. No product mutations."""
import ast
from collections import Counter
from contextlib import ExitStack
from dataclasses import replace
import json
from itertools import combinations
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator.certification.config import CertificationConfig
from generator.certification.enumeration import StepEnumerator
from generator.certification.proofs import validate_step, validate_path
from generator.certification.search import threshold_search
from generator.certification.models import EnumerationResult
from generator.certification.enum_als import enumerate_als_steps
from generator.certification.enum_forcing import enumerate_forcing
from generator.rating.registry import DEFAULT_REGISTRY
from generator.solver.human_solver import HumanSolver
from generator.solver.techniques import default_techniques
from generator.solver.techniques.forcing import propagate, proof_for
from generator.solver.techniques.forcing import ForcingChain, Nishio
from generator.solver.techniques.als import enumerate_als, ALSXZ
from generator.sudoku.grid import ALL_UNITS
from generator.tests.test_certification_proofs import fixtures
import generator.solver.exact_solver as exact


def atoms(value, path=()):
    if isinstance(value, tuple):
        for index, item in enumerate(value):
            yield from atoms(item, path + (index,))
    else:
        yield path, value


def replace_at(value, path, new):
    if not path:
        return new
    index = path[0]
    return value[:index] + (replace_at(value[index], path[1:], new),) + value[index + 1:]


def audit():
    result = {}
    paths = list((ROOT / 'generator/solver/techniques').glob('*.py'))
    paths += [ROOT / 'generator/solver/human_solver.py']
    paths += [ROOT / ('generator/certification/' + name + '.py') for name in
              ('search', 'proofs', 'enumeration', 'enum_chains', 'enum_als', 'enum_forcing')]
    for path in paths:
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert 'exact_solver' not in (node.module or ''), path
            if isinstance(node, ast.Import):
                assert all('exact_solver' not in alias.name for alias in node.names), path
    result['static_files_checked'] = len(paths)
    states = fixtures()
    names = {technique.name: technique.difficulty for technique in default_techniques()}
    assert names == {entry.name: entry.base_rating for entry in DEFAULT_REGISTRY.entries}
    result['registry_names_and_ratings_matched'] = len(names)
    als_state = states['ALS-XZ']
    independent_als = set()
    for unit in ALL_UNITS:
        for size in range(1, 9):
            for cells in combinations([c for c in unit if not als_state.grid[c]], size):
                digits = {d for c in cells for d in range(1, 10)
                          if als_state.candidates[c] & (1 << (d - 1))}
                if len(digits) == size + 1:
                    independent_als.add(tuple(sorted(cells)))
    assert independent_als == {als.cells for als in enumerate_als(als_state, 8)}
    omitted = enumerate_als_steps(als_state, ALSXZ(), CertificationConfig(max_als_size=1))
    assert not omitted.complete and 'ALS_SIZE_LIMIT' in omitted.limit_reasons
    result['independent_als_counts_by_size'] = dict(sorted(Counter(map(len, independent_als)).items()))
    for technique in (ForcingChain(), Nishio()):
        limited = enumerate_forcing(states['XY-Chain'], technique,
            CertificationConfig(max_forcing_starts=729, max_forcing_nodes=1, max_forcing_depth=1))
        assert not limited.complete and 'FORCING_DEPTH_OR_NODE_LIMIT' in limited.limit_reasons
    result['both_forcing_families_report_omitted_propagation'] = True
    examples = []
    for technique in default_techniques():
        state = states[technique.name]
        if technique.name == 'Nishio':
            proof = proof_for(propagate(state, (36, 1, True)))
            step = technique.step(eliminations=((36, 1),), premises=((36, 1, True),),
                                  assumptions=(proof,), contradiction=proof.contradiction)
        else:
            step = technique.find_steps(state)[0]
        examples.append((state, step))

    def forbidden(*args, **kwargs):
        raise AssertionError('Exact solver invoked during logical inference')

    with ExitStack() as stack:
        exact_functions = {value for value in vars(exact).values()
                           if callable(value) and getattr(value, '__module__', None) == exact.__name__}
        aliases = 0
        for name, module in list(sys.modules.items()):
            if name.startswith('generator') and module:
                for attribute, value in list(vars(module).items()):
                    if callable(value) and any(value is fn for fn in exact_functions):
                        stack.enter_context(patch.object(module, attribute, forbidden))
                        aliases += 1
        result['exact_api_aliases_trapped'] = aliases
        # Supplied certificates must validate even if discovery is unavailable.
        with ExitStack() as detectors:
            for technique in default_techniques():
                detectors.enter_context(patch.object(type(technique), 'find_steps', forbidden))
            for state, step in examples:
                assert validate_step(state, step).valid, step.technique
            mutations = 0
            for state, step in examples:
                for path, value in atoms(step.premises):
                    if type(value) is int:
                        bad = replace(step, premises=replace_at(step.premises, path, 999))
                        assert not validate_step(state, bad).valid, (step.technique, path)
                        mutations += 1
        result['independent_families'] = len(examples)
        result['out_of_range_premise_mutations_rejected'] = mutations
        fixture = json.loads((ROOT / 'generator/tests/fixtures/phase3_puzzles.json').read_text())[0]
        grid = list(map(int, fixture['puzzle']))
        solved = HumanSolver().solve(grid)
        assert solved.solved and validate_path(grid, solved.steps).valid
        result['human_replay_steps_with_exact_trapped'] = len(solved.steps)
        config = CertificationConfig(time_budget=20, max_chain_search_nodes=500,
                                     max_als_search_nodes=500, max_forcing_starts=10)
        search = threshold_search(grid, 0, config)
        assert search.status.value == 'PROVEN_UNSOLVABLE_WITHIN_MODEL'
        result['threshold_search_with_exact_trapped'] = search.status.value
        enumeration = StepEnumerator(config).enumerate(states['XY-Chain'], 55)
        for step in enumeration.steps:
            checked = validate_step(states['XY-Chain'], step, config=config)
            assert checked.valid, (step.technique, checked.errors)
        assert not enumeration.complete and enumeration.limit_reasons
        result['enumerated_proofs_with_exact_trapped'] = len(enumeration.steps)
        result['enumeration_limit_reasons'] = enumeration.limit_reasons
    # Simulate expiration inside an enumerator, after the outer loop time check.
    clock = [0.0]
    class LateEnumerator:
        def enumerate(self, state, threshold, **kwargs):
            clock[0] = 2.0
            return EnumerationResult([])
    with patch('generator.certification.search.perf_counter', side_effect=lambda: clock[0]):
        expired = threshold_search(grid, 0, CertificationConfig(time_budget=1), enumerator=LateEnumerator())
    assert expired.status.value == 'INCONCLUSIVE_BUDGET' and 'TIME_LIMIT' in expired.limit_reasons
    result['late_empty_frontier_clock_check'] = expired.status.value
    return result


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
