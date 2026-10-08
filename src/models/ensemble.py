from __future__ import annotations

import numpy as np
import pandas as pd


def cross_sectional_percentile(frame: pd.DataFrame, column: str, date_column: str = "trade_date") -> pd.Series:
    return frame.groupby(date_column, dropna=False)[column].rank(method="average", pct=True)


def ensemble_scores(
    frame: pd.DataFrame,
    *,
    factor_weight: float = 0.5,
    qlib_weight: float = 0.5,
    missing_qlib_policy: str = "factor_only",
) -> pd.DataFrame:
    if "factor_score" not in frame:
        raise ValueError("Ensemble 需要 factor_score")
    result = frame.copy()
    result["factor_percentile"] = result["factor_score"].div(100.0).clip(0, 1)
    if "qlib_score" in result:
        result["qlib_percentile"] = cross_sectional_percentile(result, "qlib_score")
    else:
        result["qlib_percentile"] = np.nan

    factor = result["factor_percentile"]
    qlib = result["qlib_percentile"]
    if missing_qlib_policy == "factor_only":
        numerator = factor.fillna(0) * factor_weight + qlib.fillna(0) * qlib_weight
        denominator = factor.notna().astype(float) * factor_weight + qlib.notna().astype(float) * qlib_weight
        result["final_score"] = numerator.div(denominator.where(denominator > 0)) * 100.0
    else:
        result["final_score"] = (factor * factor_weight + qlib * qlib_weight) * 100.0
    return result

