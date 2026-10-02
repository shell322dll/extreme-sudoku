"""Exact solving is confined to this optional, separate uniqueness gate.

No exact solution or exact-search cost is supplied to human difficulty analysis.
"""
from .classification import classify

def check_uniqueness(puzzle,result,config):
    from ..solver.exact_solver import count_solutions
    result.unique=count_solutions(puzzle,limit=2)==1
    return classify(result,config)
