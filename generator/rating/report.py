"""Text diagnostics for development; no production certification claims."""
def diagnostic_report(result,puzzle=None):
    lines=[]
    if puzzle is not None:
        lines.append("Puzzle: "+"".join(map(str,puzzle)))
    lines.extend([f"Mode: {result.mode}",f"Solved: {result.solved}",f"Clues: {result.clue_count}",
        f"Unique: {result.unique if result.unique is not None else 'unchecked'}"])
    lines.extend(f"{name} profile: {value}" for name,value in result.profile_statuses.items())
    lines.extend([f"Required level: {result.hardest_required_technique or 'unverified/none'}",
        f"Hardest required rating: {result.hardest_required_rating}",
        f"Minimum tier: {result.minimum_tier}",f"Required level verified: {result.required_level_verified}",
        f"Hardest observed: {result.hardest_technique}",f"Advanced steps: {result.advanced_steps}",
        f"Extreme steps: {result.extreme_steps}",f"True bottlenecks (grouped): {result.true_bottleneck_count}",
        f"Bottleneck states: {len(result.bottlenecks)}",f"Longest chain: {result.longest_chain}",
        f"ALS / forcing steps: {result.als_steps} / {result.forcing_steps}",
        f"Total logical score: {result.total_score:.3f}",f"Rating: {result.rating:.3f}",
        f"High peaks: {result.high_peak_count}; positions: {result.peak_positions}",
        f"Advanced distribution: {result.advanced_distribution}",
        f"Late bottlenecks: {result.late_bottleneck_count}",f"Difficulty: {result.difficulty_class}",
        f"Extreme candidate: {result.is_extreme_candidate}",
        f"Ultra Extreme candidate: {result.is_ultra_extreme_candidate}",
        "Certification: preliminary only",f"Scope: {result.scope}"])
    return "\n".join(lines)
