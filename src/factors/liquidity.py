from __future__ import annotations

import numpy as np
import pandas as pd


def add_liquidity_factors(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "amount" not in result:
        result["amount"] = np.nan
    if "turnover_rate" not in result:
        result["turnover_rate"] = np.nan
    grouped = result.groupby("ticker", sort=False)
    result["average_amount_20"] = grouped["amount"].transform(lambda values: values.rolling(20, min_periods=10).mean())
    result["average_turnover_20"] = grouped["turnover_rate"].transform(lambda values: values.rolling(20, min_periods=10).mean())
    if "return_1d" not in result:
        result["return_1d"] = grouped["close"].pct_change(fill_method=None)
    daily_illiquidity = result["return_1d"].abs().div(result["amount"].where(result["amount"] > 0)) * 1e8
    result["amihud_20"] = daily_illiquidity.groupby(result["ticker"], sort=False).transform(
        lambda values: values.rolling(20, min_periods=10).mean()
    )
    return result

