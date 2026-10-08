import numpy as np
import pandas as pd
import pytest

from src.factors.normalization import percentile_rank_series, winsorize_series, zscore_series
from src.factors.price_factors import calculate_price_factors


def make_prices(days: int = 320) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=days)
    close = 10.0 * np.power(1.001, np.arange(days))
    return pd.DataFrame(
        {
            "ticker": "SH600000", "trade_date": dates, "open": close * 0.999,
            "high": close * 1.01, "low": close * 0.99, "close": close,
            "volume": 1_000_000.0, "amount": close * 1_000_000.0,
        }
    )


def test_price_factor_math_uses_backward_windows():
    prices = make_prices()
    result = calculate_price_factors(prices)
    last = result.iloc[-1]
    expected_20 = prices.iloc[-1]["close"] / prices.iloc[-21]["close"] - 1.0
    expected_12_1 = prices.iloc[-21]["close"] / prices.iloc[-251]["close"] - 1.0
    assert last["momentum_20"] == pytest.approx(expected_20)
    assert last["momentum_12_1"] == pytest.approx(expected_12_1)
    assert last["ma20"] == pytest.approx(prices["close"].iloc[-20:].mean())
    assert last["volatility_20"] == pytest.approx(0.0, abs=1e-12)


def test_normalization_is_dimensionless_and_robust():
    values = pd.Series([1.0, 2.0, 3.0, 1000.0, np.nan])
    clipped = winsorize_series(values, 0.0, 0.75)
    assert clipped.iloc[3] <= values.dropna().quantile(0.75)
    assert percentile_rank_series(values).dropna().between(0, 1).all()
    assert zscore_series(pd.Series([2.0, 2.0])).tolist() == [0.0, 0.0]

