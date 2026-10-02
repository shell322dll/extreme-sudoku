"""Bounded alternative deductions and immutable state/profile cache summaries."""
from collections import OrderedDict
from dataclasses import dataclass
from itertools import groupby
from .config import DifficultyConfig
from .profiles import EXTREME_PROFILE, solver_for_profile
from ..solver.human_solver import apply_step
from ..solver.techniques.base import step_key

@dataclass(frozen=True)
class StateAnalysis:
    state_signature: tuple
    techniques: tuple[str,...]
    minimum_rating: float | None
    maximum_rating: float | None
    minimum_technique: str | None
    minimum_steps: tuple
    steps: tuple
    number_of_alternatives: int
    enumeration_complete: bool
    scope: str = "representative deductions within configured detector budgets"

class StateAnalyzer:
    def __init__(self,config=None):
        self.config=config or DifficultyConfig()
        self._cache=OrderedDict()
        self.cache_hits=0
        self.cache_misses=0

    def clear_cache(self):
        self._cache.clear()
        self.cache_hits=self.cache_misses=0

    def _analyze(self,state,profile,minimum_only):
        state.validate()
        signature=state.signature()
        key=(signature,profile,self.config,minimum_only)
        if key in self._cache:
            self.cache_hits+=1
            self._cache.move_to_end(key)
            return self._cache[key]
        self.cache_misses+=1
        solver=solver_for_profile(profile,self.config)
        steps=[]
        for _,techniques in groupby(solver.techniques,key=lambda t:t.difficulty):
            for technique in techniques:
                for step in technique.find_steps(state):
                    # Reject a bad detector result, never reinterpret it as STUCK.
                    apply_step(state,step)
                    steps.append(step)
            if steps and minimum_only:
                break
        steps=tuple(sorted(steps,key=lambda s:(self.config.registry.rating_of(s.technique),step_key(s))))
        minimum=self.config.registry.rating_of(steps[0].technique) if steps else None
        minimum_steps=tuple(s for s in steps if self.config.registry.rating_of(s.technique)==minimum)
        summary=StateAnalysis(signature,tuple(dict.fromkeys(s.technique for s in steps)),minimum,
            self.config.registry.rating_of(steps[-1].technique) if steps else None,
            steps[0].technique if steps else None,minimum_steps,steps,len(steps),not minimum_only)
        if self.config.cache_size:
            self._cache[key]=summary
            while len(self._cache)>self.config.cache_size:
                self._cache.popitem(last=False)
        return summary

    def analyze_state(self,state,profile=EXTREME_PROFILE):
        """All implemented detectors; 'complete' is bounded, never unrestricted."""
        return self._analyze(state,profile,False)

    def minimum_available_rating(self,state,profile=EXTREME_PROFILE):
        """Visit all lower ratings and all detectors tied at the first available level.

        Higher levels cannot lower the minimum, so their enumeration is skipped.
        Counts and maximum_rating here describe only this minimum layer.
        """
        return self._analyze(state,profile,True)

def analyze_state(state,*,config=None,profile=EXTREME_PROFILE):
    return StateAnalyzer(config).analyze_state(state,profile)

def minimum_available_rating(state,*,config=None,profile=EXTREME_PROFILE):
    return StateAnalyzer(config).minimum_available_rating(state,profile)

def all_available_steps(state,*,config=None,profile=EXTREME_PROFILE):
    return list(analyze_state(state,config=config,profile=profile).steps)
