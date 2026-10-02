"""Single source of ratings; legacy scale retained (AIC=30, not SE ratings)."""
from dataclasses import dataclass
from enum import IntEnum
from math import isfinite

class Tier(IntEnum):
    TRIVIAL = 0
    BASIC = 1
    INTERMEDIATE = 2
    ADVANCED = 3
    EXTREME = 4

def nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")

@dataclass(frozen=True)
class TechniqueRating:
    name: str
    tier: Tier
    base_rating: float
    weight: float

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name or not isinstance(self.tier, Tier):
            raise ValueError("Invalid technique name/tier")
        nonnegative(self.base_rating, "base_rating")
        nonnegative(self.weight, "weight")

@dataclass(frozen=True)
class TechniqueRegistry:
    entries: tuple[TechniqueRating, ...]

    def __post_init__(self):
        entries = tuple(sorted(self.entries, key=lambda e: (e.base_rating, e.name)))
        if len({e.name for e in entries}) != len(entries):
            raise ValueError("Duplicate technique names")
        if any(a.tier > b.tier for a, b in zip(entries, entries[1:])):
            raise ValueError("Ratings must respect tier order")
        object.__setattr__(self, "entries", entries)

    def get(self, name):
        for entry in self.entries:
            if entry.name == name:
                return entry
        raise ValueError(f"Unknown technique: {name}")

    def rating_of(self, name):
        return self.get(name).base_rating

    def tier_of(self, name):
        return self.get(name).tier

    def weight_of(self, name):
        return self.get(name).weight

_ROWS = (
    ("Full House", 0, .5), ("Naked Single", 0, 1), ("Hidden Single", 0, 1.2),
    ("Locked Candidates", 1, 2), ("Naked Pair", 1, 3), ("Hidden Pair", 1, 3.2),
    ("Naked Triple", 1, 5), ("Hidden Triple", 1, 5.2),
    ("Naked Quad", 2, 7), ("Hidden Quad", 2, 7.2), ("X-Wing", 2, 8),
    ("Skyscraper", 2, 9), ("2-String Kite", 2, 9.2), ("Turbot Fish", 2, 10),
    ("Empty Rectangle", 2, 11), ("Swordfish", 3, 12), ("XY-Wing", 3, 14),
    ("XYZ-Wing", 3, 16), ("W-Wing", 3, 17), ("Jellyfish", 3, 18),
    ("X-Chain", 4, 22), ("XY-Chain", 4, 25), ("AIC", 4, 30),
    ("Nice Loop", 4, 32), ("Grouped AIC", 4, 35), ("ALS-XZ", 4, 36),
    ("ALS-XY-Wing", 4, 39), ("ALS Chain", 4, 42),
    ("Forcing Chain", 4, 50), ("Nishio", 4, 55),
)
DEFAULT_REGISTRY = TechniqueRegistry(tuple(TechniqueRating(n, Tier(t), float(r), float(r)) for n,t,r in _ROWS))
rating_of = DEFAULT_REGISTRY.rating_of
tier_of = DEFAULT_REGISTRY.tier_of
weight_of = DEFAULT_REGISTRY.weight_of
