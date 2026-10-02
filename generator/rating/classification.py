"""Explainable preliminary classes; high classes require verified unique inputs."""
def classify(result,config):
    result.is_extreme_candidate=False
    result.is_ultra_extreme_candidate=False
    if not result.solved or result.invalid:
        result.difficulty_class="Unrated"
        return result
    floor=result.hardest_rating if result.mode=="quick" else result.hardest_required_rating
    if floor is None or (result.mode=="deep" and not result.required_level_verified):
        result.difficulty_class="Unrated"
        return result
    result.difficulty_class=next(name for name,limit in reversed(config.classification_thresholds) if floor>=limit)
    eligible=(result.mode=="deep" and result.unique is True and result.required_level_verified
              and not result.used_backtracking and result.guesses==0
              and result.profile_statuses.get("Basic")=="STUCK"
              and result.profile_statuses.get("Intermediate")=="STUCK"
              and result.profile_statuses.get("Extreme")=="SOLVED")
    result.is_extreme_candidate=bool(eligible and floor>=config.extreme_threshold
        and result.advanced_steps>=config.minimum_advanced_steps
        and result.true_bottleneck_count>=config.minimum_bottlenecks)
    result.is_ultra_extreme_candidate=bool(result.is_extreme_candidate and floor>=config.ultra_threshold
        and result.advanced_steps>=config.ultra_minimum_advanced_steps
        and result.true_bottleneck_count>=config.ultra_minimum_bottlenecks
        and result.longest_chain>=config.ultra_minimum_chain
        and result.distributed_advanced_steps>=config.ultra_minimum_distributed_bins
        and (result.chain_steps or result.als_steps or result.forcing_steps))
    if result.is_ultra_extreme_candidate:
        result.difficulty_class="Ultra Extreme"
    elif result.is_extreme_candidate:
        result.difficulty_class="Extreme"
    return result
