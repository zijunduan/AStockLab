from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def winsorize_series(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    valid = numeric.dropna()
    if valid.empty:
        return numeric
    low, high = valid.quantile([lower, upper])
    return numeric.clip(lower=low, upper=high)


def zscore_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    std = numeric.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(np.where(numeric.notna(), 0.0, np.nan), index=series.index, dtype=float)
    return (numeric - numeric.mean()) / std


def percentile_rank_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    return numeric.rank(method="average", pct=True)


def normalize_cross_section(
    frame: pd.DataFrame,
    columns: Iterable[str],
    *,
    date_column: str = "trade_date",
    group_columns: Iterable[str] | None = None,
    winsor_lower: float = 0.01,
    winsor_upper: float = 0.99,
) -> pd.DataFrame:
    """Append `<factor>_winsor`, `<factor>_zscore`, and `<factor>_percentile`.

    Normalization is always performed inside each date (and optional industry), so
    observations from a future date can never affect an earlier cross section.
    """
    result = frame.copy()
    groups = [date_column, *(group_columns or [])]
    generated: dict[str, pd.Series] = {}
    for column in columns:
        if column not in result:
            continue
        winsor_name = f"{column}_winsor"
        zscore_name = f"{column}_zscore"
        percentile_name = f"{column}_percentile"
        winsor = result.groupby(groups, dropna=False, group_keys=False)[column].transform(
            lambda values: winsorize_series(values, winsor_lower, winsor_upper)
        )
        generated[winsor_name] = winsor
        generated[zscore_name] = winsor.groupby([result[group] for group in groups], dropna=False).transform(zscore_series)
        generated[percentile_name] = winsor.groupby([result[group] for group in groups], dropna=False).transform(percentile_rank_series)
    return pd.concat([result, pd.DataFrame(generated, index=result.index)], axis=1)


def weighted_available_mean(frame: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted mean that renormalizes only across available inputs per row."""
    numerator = pd.Series(0.0, index=frame.index)
    denominator = pd.Series(0.0, index=frame.index)
    for column, weight in weights.items():
        if column not in frame or weight == 0:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        available = values.notna()
        numerator = numerator.add(values.fillna(0) * weight, fill_value=0)
        denominator = denominator.add(available.astype(float) * abs(weight), fill_value=0)
    return numerator.div(denominator.where(denominator > 0))

