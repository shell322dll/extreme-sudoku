"""Deterministic registries, with frozen Phase 1/2 comparison repertoires."""

from .base import Technique
from .singles import FullHouse, NakedSingle, HiddenSingle
from .locked_candidates import LockedCandidates
from .subsets import NakedPair, HiddenPair, NakedTriple, HiddenTriple, NakedQuad, HiddenQuad
from .fish import XWing, Swordfish, Jellyfish
from .single_digit_patterns import Skyscraper, TwoStringKite, TurbotFish, EmptyRectangle
from .wings import XYWing, XYZWing, WWing
from .weights import TECHNIQUE_WEIGHTS
from .chains import XChain, XYChain, AIC, NiceLoop, GroupedAIC
from .als import ALSXZ, ALSXYWing, ALSChain
from .forcing import ForcingChain, Nishio

PHASE1_TECHNIQUE_TYPES = (FullHouse, NakedSingle, HiddenSingle, LockedCandidates,
                        NakedPair, HiddenPair, NakedTriple, HiddenTriple)
INTERMEDIATE_TECHNIQUE_TYPES = (NakedQuad, HiddenQuad, XWing, Skyscraper,
                                TwoStringKite, TurbotFish, EmptyRectangle, Swordfish,
                                XYWing, XYZWing, WWing, Jellyfish)
INTERMEDIATE_TECHNIQUE_NAMES = frozenset(cls.name for cls in INTERMEDIATE_TECHNIQUE_TYPES)
PHASE2_TECHNIQUE_TYPES = PHASE1_TECHNIQUE_TYPES + INTERMEDIATE_TECHNIQUE_TYPES
ADVANCED_TECHNIQUE_TYPES = (XChain, XYChain, AIC, NiceLoop, GroupedAIC,
                          ALSXZ, ALSXYWing, ALSChain, ForcingChain, Nishio)
ADVANCED_TECHNIQUE_NAMES = frozenset(cls.name for cls in ADVANCED_TECHNIQUE_TYPES)
TECHNIQUE_TYPES = PHASE2_TECHNIQUE_TYPES + ADVANCED_TECHNIQUE_TYPES
DEFAULT_WEIGHTS = dict(TECHNIQUE_WEIGHTS)


def default_techniques(weights=None, *, config=None):
    return _techniques(TECHNIQUE_TYPES, weights, config=config)


def phase2_techniques(weights=None):
    """Phase 1 plus all original intermediate techniques, without Phase 3."""
    return _techniques(PHASE2_TECHNIQUE_TYPES, weights)


def advanced_techniques(weights=None, *, config=None):
    """Only the Phase 3 extension; use default_techniques for the full solver."""
    return _techniques(ADVANCED_TECHNIQUE_TYPES, weights, config=config)


def phase1_techniques(weights=None):
    """The original, frozen Phase 1 repertoire for baseline comparisons."""
    return _techniques(PHASE1_TECHNIQUE_TYPES, weights)


def _techniques(classes, weights, config=None):
    weights = {} if weights is None else dict(weights)
    unknown = weights.keys() - {cls.name for cls in classes}
    if unknown:
        raise ValueError(f"Unknown technique weights: {sorted(unknown)}")
    return [cls(difficulty=weights.get(cls.name), **({"config": config}
                if cls in ADVANCED_TECHNIQUE_TYPES else {})) for cls in classes]
