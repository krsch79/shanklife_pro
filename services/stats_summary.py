def round_score_summary(completed_rounds):
    to_par_values = [row["total"] - row["par"] for row in completed_rounds]

    def best_total(hole_count):
        return min(
            (row["total"] for row in completed_rounds if row["holes"] == hole_count),
            default=None,
        )

    return {
        "avg_round_vs_par": (
            round(sum(to_par_values) / len(to_par_values), 1)
            if to_par_values
            else None
        ),
        "best_round_18": best_total(18),
        "best_round_9": best_total(9),
        "best_round_vs_par": min(to_par_values, default=None),
    }
