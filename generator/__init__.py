"""Independent ordinary and evolutionary Sudoku generation APIs."""

from importlib import import_module

__all__ = ["GeneratorConfig", "GeneratedPuzzle", "BatchResult", "GenerationError",
           "GenerationStats", "RejectionReason", "PuzzleGenerator", "generate_puzzle",
           "generate_many", "remove_clues", "minimalize", "check_minimal",
           "validate_candidate", "UniquenessCache", "EvolutionConfig", "EvolutionIndividual",
           "EvolutionEngine", "EvolutionResult", "EvolutionStats", "FitnessConfig", "evolve"]

_MODULES = {
    **dict.fromkeys(("EvolutionConfig", "EvolutionIndividual", "EvolutionEngine", "EvolutionResult",
                     "EvolutionStats", "FitnessConfig", "evolve"), "evolution"),
    "GeneratorConfig": "config",
    **dict.fromkeys(("BatchResult", "GeneratedPuzzle", "GenerationError", "GenerationStats",
                     "GENERATOR_VERSION", "RejectionReason", "__version__"), "models"),
    **dict.fromkeys(("UniquenessCache", "check_minimal", "minimalize", "remove_clues",
                     "validate_candidate"), "construction"),
    **dict.fromkeys(("PuzzleGenerator", "generate_many", "generate_puzzle"), "pipeline"),
}


def __getattr__(name):
    """Keep human-only imports independent from exact generation dependencies."""
    if name not in _MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f".{_MODULES[name]}", __name__)
    value = getattr(module, "GENERATOR_VERSION" if name == "__version__" else name)
    globals()[name] = value
    return value
