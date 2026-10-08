from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(values: np.ndarray) -> float:
    if len(values) == 0 or np.isnan(values).all():
        return np.nan
    series = pd.Series(values).dropna().to_numpy(dtype=float)
    if len(series) < 2:
        return np.nan
    peaks = np.maximum.accumulate(series)
    drawdowns = np.divide(series, peaks, out=np.ones_like(series), where=peaks != 0) - 1.0
    return float(drawdowns.min())


def add_risk_factors(frame: pd.DataFrame, *, calculate_rolling_drawdown: bool = True) -> pd.DataFrame:
    result = frame.copy()
    grouped = result.groupby("ticker", sort=False)
    result["return_1d"] = grouped["close"].pct_change(fill_method=None)
    for window in (20, 60):
        result[f"volatility_{window}"] = grouped["return_1d"].transform(
            lambda values: values.rolling(window, min_periods=window).std(ddof=0) * np.sqrt(252)
        )
    downside = result["return_1d"].where(result["return_1d"] < 0, 0.0)
    result["downside_volatility_60"] = downside.groupby(result["ticker"], sort=False).transform(
        lambda values: values.rolling(60, min_periods=60).std(ddof=0) * np.sqrt(252)
    )
    if calculate_rolling_drawdown:
        result["max_drawdown_120"] = grouped["close"].transform(
            lambda values: values.rolling(120, min_periods=120).apply(max_drawdown, raw=True)
        ).abs()
    else:
        result["max_drawdown_120"] = np.nan
    previous_close = grouped["close"].shift(1)
    true_range = pd.concat(
        [
            result["high"].sub(result["low"]).abs(),
            result["high"].sub(previous_close).abs(),
            result["low"].sub(previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result["atr_14"] = true_range.groupby(result["ticker"], sort=False).transform(
        lambda values: values.rolling(14, min_periods=14).mean()
    ).div(result["close"])
    result["extreme_move_20"] = result["return_1d"].abs().groupby(result["ticker"], sort=False).transform(
        lambda values: values.rolling(20, min_periods=20).max()
    )
    return result

