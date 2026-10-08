from __future__ import annotations

import pandas as pd


def rank_cross_section(frame: pd.DataFrame, score_column: str = "final_score") -> pd.DataFrame:
    if score_column not in frame:
        raise ValueError(f"缺少排名字段: {score_column}")
    result = frame.copy()
    result["rank"] = result.groupby("trade_date", dropna=False)[score_column].rank(method="first", ascending=False).astype("Int64")
    # pandas percentile rank is ascending: the highest score receives 1.0.
    result["percentile"] = result.groupby("trade_date", dropna=False)[score_column].rank(method="average", pct=True)
    return result.sort_values(["trade_date", "rank", "ticker"], kind="stable").reset_index(drop=True)


def top_n(frame: pd.DataFrame, n: int = 50, score_column: str = "final_score") -> pd.DataFrame:
    ranked = rank_cross_section(frame, score_column)
    return ranked.loc[ranked["rank"].le(n)].reset_index(drop=True)

