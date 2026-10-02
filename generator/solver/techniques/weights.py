"""Compatibility: historical weights are detector base ratings."""
from ...rating.registry import DEFAULT_REGISTRY

TECHNIQUE_WEIGHTS = {e.name: e.base_rating for e in DEFAULT_REGISTRY.entries}
