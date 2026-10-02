"""State minima identify crises; adjacent high steps conservatively form one crisis."""
from dataclasses import replace
from .models import Bottleneck
from .state_analysis import StateAnalyzer
from ..solver.human_solver import apply_step
from ..sudoku.candidates import SudokuState

def pattern_key(step):
    """Proof identity excludes target eliminations and explanatory prose."""
    return (step.technique,repr(step.premises),repr(step.chain),repr(step.als),
            repr(tuple(p.assumption for p in step.assumptions)))

def bottleneck_at(state,step_index,analyzer):
    summary=analyzer.minimum_available_rating(state)
    if summary.minimum_rating is None or summary.minimum_rating < analyzer.config.bottleneck_threshold:
        return None
    return Bottleneck(step_index,state.signature(),summary.minimum_rating,summary.minimum_technique,
                      len(summary.minimum_steps))

def detect_bottlenecks(puzzle,steps,*,config=None,analyzer=None):
    analyzer=analyzer or StateAnalyzer(config)
    state=SudokuState(puzzle)
    events=[]
    known_patterns={}
    last_index=-2
    group=-1
    for index,step in enumerate(steps):
        # A valid cheap applied step is already a witness against a high minimum.
        event=None
        if analyzer.config.registry.rating_of(step.technique)>=analyzer.config.bottleneck_threshold:
            event=bottleneck_at(state,index,analyzer)
        if event is not None:
            minimum=analyzer.minimum_available_rating(state).minimum_steps[0]
            key=pattern_key(minimum)
            if index == last_index+1:
                chosen_group=events[-1].group_id
                if key in known_patterns and known_patterns[key] != chosen_group:
                    # A repeated pattern can bridge two previously separate
                    # episodes. Merge transitively rather than counting it twice.
                    old_group=known_patterns[key]
                    merged=min(chosen_group,old_group)
                    retired=max(chosen_group,old_group)
                    events=[replace(e,group_id=merged) if e.group_id==retired else e for e in events]
                    known_patterns={k:merged if v==retired else v for k,v in known_patterns.items()}
                    chosen_group=merged
            elif key in known_patterns:
                chosen_group=known_patterns[key]
            else:
                group+=1
                chosen_group=group
            known_patterns[key]=chosen_group
            events.append(replace(event,group_id=chosen_group))
            last_index=index
        state=apply_step(state,step)
    return events

def summarize_bottlenecks(result,config):
    groups={}
    for event in result.bottlenecks:
        if event.genuine:
            groups.setdefault(event.group_id,[]).append(event)
    result.true_bottleneck_count=len(groups)
    result.max_bottleneck_rating=max((e.required_rating for e in result.bottlenecks),default=0.)
    result.bottleneck_severity=sum(max(e.required_rating for e in events) for events in groups.values())
    result.late_bottleneck_count=sum(any(e.step_index>=result.step_count*config.late_fraction for e in events)
                                     for events in groups.values())
