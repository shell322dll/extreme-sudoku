"""Explicit finite search budgets shared by advanced logical techniques."""

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class AdvancedConfig:
    # Chain lengths count inference links, including a loop's closing link.
    max_x_chain_length: int = 15
    max_xy_chain_length: int = 19
    max_aic_length: int = 19
    max_grouped_aic_length: int = 19
    # Total examined graph edges per detector call, across all starts.
    max_chain_search_nodes: int = 100000
    max_als_size: int = 4
    max_als_chain_length: int = 5
    max_als_search_nodes: int = 30000
    max_forcing_depth: int = 12
    max_forcing_nodes: int = 2000
    max_forcing_starts: int = 160

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{item.name} must be a positive integer")
        if self.max_als_size > 8:
            raise ValueError("max_als_size must be at most 8")


DEFAULT_ADVANCED_CONFIG = AdvancedConfig()
