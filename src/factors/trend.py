from __future__ import annotations

import pandas as pd


def add_trend_factors(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    grouped = result.groupby("ticker", sort=False)
    for window in (20, 60, 120, 250):
        ma_column = f"ma{window}"
        result[ma_column] = grouped["close"].transform(lambda values: values.rolling(window, min_periods=window).mean())
        result[f"price_ma{window}"] = result["close"].div(result[ma_column]).sub(1.0)
    result["ma60_slope"] = result.groupby("ticker", sort=False)["ma60"].pct_change(periods=20, fill_method=None)
    conditions = [
        result["close"] > result["ma20"],
        result["ma20"] > result["ma60"],
        result["ma60"] > result["ma120"],
        result["ma120"] > result["ma250"],
    ]
    available = [
        result[["close", "ma20"]].notna().all(axis=1),
        result[["ma20", "ma60"]].notna().all(axis=1),
        result[["ma60", "ma120"]].notna().all(axis=1),
        result[["ma120", "ma250"]].notna().all(axis=1),
    ]
    numerator = sum(condition.astype(float) for condition in conditions)
    denominator = sum(mask.astype(float) for mask in available)
    result["trend_consistency"] = numerator.div(denominator.where(denominator > 0))
    return result

