from __future__ import annotations

import pandas as pd


def select_research_candidates(
    rankings: pd.DataFrame,
    *,
    top_n: int = 50,
    min_factor_coverage: float = 0.5,
    require_positive_trend: bool = True,
) -> pd.DataFrame:
    candidates = rankings.copy()
    if "factor_coverage" in candidates:
        candidates = candidates.loc[candidates["factor_coverage"].fillna(0).ge(min_factor_coverage)]
    if require_positive_trend and "trend_score" in candidates:
        candidates = candidates.loc[candidates["trend_score"].fillna(0).ge(50)]
    return candidates.sort_values("rank").head(top_n).reset_index(drop=True)

