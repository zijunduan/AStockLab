from __future__ import annotations

import pandas as pd


def add_momentum_factors(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    grouped_close = result.groupby("ticker", sort=False)["close"]
    for window in (20, 60, 120, 250):
        result[f"momentum_{window}"] = grouped_close.pct_change(periods=window, fill_method=None)
    shifted_20 = grouped_close.shift(20)
    shifted_250 = grouped_close.shift(250)
    result["momentum_12_1"] = shifted_20.div(shifted_250).sub(1.0)
    return result

