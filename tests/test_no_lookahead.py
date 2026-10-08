import numpy as np
import pandas as pd

from src.factors.price_factors import calculate_price_factors
from src.models.factor_model import select_point_in_time_financials


def test_future_prices_do_not_change_past_factors():
    dates = pd.bdate_range("2024-01-01", periods=340)
    rng = np.random.default_rng(7)
    close = 20 * np.cumprod(1 + rng.normal(0.0003, 0.01, len(dates)))
    frame = pd.DataFrame(
        {
            "ticker": "SZ000001", "trade_date": dates, "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": 1e6, "amount": close * 1e6,
        }
    )
    cutoff = 300
    short = calculate_price_factors(frame.iloc[:cutoff].copy()).iloc[-1]
    full = calculate_price_factors(frame.copy()).iloc[cutoff - 1]
    columns = ["momentum_20", "momentum_120", "momentum_12_1", "ma60", "volatility_60", "max_drawdown_120"]
    pd.testing.assert_series_equal(short[columns], full[columns], check_names=False)


def test_financials_are_unavailable_before_announcement_date():
    financials = pd.DataFrame(
        [
            {"ticker": "SH600000", "report_period": "2025-03-31", "announcement_date": "2025-04-25", "roe": 0.12},
            {"ticker": "SH600000", "report_period": "2025-06-30", "announcement_date": "2025-08-30", "roe": 0.14},
        ]
    )
    assert select_point_in_time_financials(financials, "2025-04-01").empty
    april = select_point_in_time_financials(financials, "2025-04-25")
    assert april.iloc[0]["roe"] == 0.12
    assert select_point_in_time_financials(financials, "2025-08-01").iloc[0]["roe"] == 0.12

